"""Read-only helpers for validating monthly source workbooks."""
from __future__ import annotations

import re
import zipfile
import calendar
import os
import tempfile
import threading
import shutil
from datetime import datetime
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

from openpyxl import load_workbook

from server.db import METER_LABELS, MONTH_CLOSE_LABELS, TIME_SLOTS, save_record


OBSERVATION_COLUMNS = {
    "main": {"kv": "F", "a1": "I", "a2": "L", "a3": "O", "pf": "R", "kw": "U", "hz": "Y", "tr1": "AB", "tr2": "AE"},
    "vcb": {"kv": "AH", "kw": "AK", "pf": "AN", "a": "AQ", "upsKw": "AT", "upsA": "AX", "emergencyKw": "BB", "emergencyA": "BF", "hvacKw": "BJ", "hvacA": "BN", "generalKw": "BR", "generalA": "BV", "lightingKw": "BZ", "lightingA": "CD"},
    "transformer": {"lighting": "AQ", "general": "AV", "hvac": "BA", "emergency": "BF", "ups": "BK"},
    "chiller": {"chillerKw": "R", "chillerA": "V", "chiller2Kw": "Z", "chiller2A": "AD", "capacitorKw": "AH", "capacitorA": "AL"},
    "secondary": {"lowLightingV": "F", "lowLightingKw": "J", "lowLightingA": "N", "lowGeneralV": "R", "lowGeneralKw": "V", "lowGeneralA": "Z", "lowEmergencyV": "AD", "lowEmergencyKw": "AH", "lowEmergencyA": "AL", "rectifierV": "BP", "rectifierA": "BT", "batteryV": "BY", "batteryA": "CC"},
}
DAILY_METER_COLUMNS = {"4": "N", "5": "W", "6": "AF", "7": "AO", "8": "AX"}
MONTHLY_CLOSE_COLUMNS = {"substation": {"current": "BK", "previous": "BM"}, "industrial": {"current": "BZ", "previous": "CB"}}

_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships", "pkg": "http://schemas.openxmlformats.org/package/2006/relationships"}
_WRITE_LOCKS: dict[str, threading.Lock] = {}
_LOCK_GUARD = threading.Lock()


def _cell_map(record_date: str, record: dict) -> dict[str, object]:
    cells: dict[str, object] = {}
    for index, slot in enumerate(TIME_SLOTS):
        row = 10 + index
        for group, fields in (record.get("observations") or {}).get(slot, {}).items():
            columns = OBSERVATION_COLUMNS.get(group)
            if columns is None:
                raise ValueError("unsupported observation group")
            for field, value in fields.items():
                if field not in columns:
                    if group == "transformer" and field == "trTemp":
                        continue
                    raise ValueError("unsupported observation field")
                source_row = row if group in ("main", "vcb") else row + (10 if group in ("transformer", "chiller") or (group == "secondary" and not field.startswith("low")) else 20)
                cells[f"{columns[field]}{source_row}"] = value
    meters = record.get("meters") or {}
    for kind, row in (("current", 38), ("previous", 39)):
        values = meters.get(kind) or []
        for idx, label in enumerate(METER_LABELS):
            col = DAILY_METER_COLUMNS.get(label)
            if col and idx < len(values):
                cells[f"{col}{row}"] = values[idx]
    for close_kind, labels in MONTH_CLOSE_LABELS.items():
        for reading_kind in ("current", "previous"):
            values = (((meters.get("monthlyClose") or {}).get(close_kind) or {}).get(reading_kind) or [])
            col = MONTHLY_CLOSE_COLUMNS[close_kind][reading_kind]
            for idx, value in enumerate(values[:len(labels)]):
                cells[f"{col}{28 + idx}"] = value
    if "notes" in record:
        cells["C44"] = str(record["notes"] or "")
    return cells


def _worksheet_part(archive: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rel_id = next((el.attrib.get(f"{{{_NS['rel']}}}id") for el in workbook.findall(".//main:sheet", _NS) if el.attrib.get("name") == sheet_name), None)
    if not rel_id:
        raise ValueError(f"missing day sheet: {sheet_name}")
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    target = next((el.attrib.get("Target") for el in rels.findall("pkg:Relationship", _NS) if el.attrib.get("Id") == rel_id), None)
    if not target:
        raise ValueError("invalid workbook sheet relationship")
    return target.lstrip("/") if target.startswith("/") else str(Path("xl") / target).replace("\\", "/")


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(node.itertext()) for node in root.findall("main:si", _NS)]


def _cell_matches(cell, value, shared_strings: list[str]) -> bool:
    inline = cell.find("main:is", _NS)
    raw = cell.find("main:v", _NS)
    kind = cell.attrib.get("t")
    if kind == "inlineStr":
        current = "".join(inline.itertext()) if inline is not None else ""
        return isinstance(value, str) and current == value
    if kind == "s" and raw is not None:
        try:
            current = shared_strings[int(raw.text)]
        except (ValueError, IndexError, TypeError):
            return False
        return isinstance(value, str) and current == value
    if value in (None, ""):
        return raw is None and inline is None
    if isinstance(value, str):
        return raw is not None and raw.text == value
    if raw is None:
        return False
    try:
        return float(raw.text) == float(value)
    except (TypeError, ValueError):
        return False


def write_workbook_record(path: str | Path, record_date: str, record: dict, backup_dir: str | Path) -> dict:
    """Patch mapped daily and month-summary cells, preserving every other package part."""
    resolved = Path(path).resolve(strict=True)
    try:
        parsed_date = date.fromisoformat(record_date)
    except (TypeError, ValueError) as exc:
        raise ValueError("date must be YYYY-MM-DD") from exc
    if parsed_date.isoformat() != record_date or record.get("date") != record_date:
        raise ValueError("date mismatch")
    cells = _cell_map(record_date, record)
    with _LOCK_GUARD:
        lock = _WRITE_LOCKS.setdefault(str(resolved), threading.Lock())
    with lock:
        with zipfile.ZipFile(resolved, "r") as source:
            names = source.namelist()
            shared_strings = _shared_strings(source)
            sheet_part = _worksheet_part(source, f"{parsed_date.day:02d}일")
            if sheet_part not in names:
                raise ValueError("missing day sheet part")
            patches = {sheet_part: cells}
            summary_part = None
            if "operator" in record:
                summary_part = _worksheet_part(source, "수식(월변경)")
                if summary_part not in names:
                    raise ValueError("missing month summary sheet part")
                patches[summary_part] = {f"J{parsed_date.day + 1}": str(record.get("operator") or "")}
            preserved = []
            replacements = {}
            changed = False
            for part, updates in patches.items():
                root = ET.fromstring(source.read(part))
                sheet_data = root.find("main:sheetData", _NS)
                rows = {int(row.attrib["r"]): row for row in sheet_data.findall("main:row", _NS)}
                for address, value in updates.items():
                    row_number = int(re.search(r"\d+$", address).group())
                    row_el = rows.get(row_number)
                    cell = next((el for el in row_el.findall("main:c", _NS) if el.attrib.get("r") == address), None) if row_el is not None else None
                    if cell is None:
                        raise ValueError(f"target cell missing: {address}")
                    if cell.find("main:f", _NS) is not None:
                        if not _cell_matches(cell, value, shared_strings):
                            raise ValueError("formula-protected cell value mismatch")
                        preserved.append(address)
                        continue
                    if _cell_matches(cell, value, shared_strings):
                        continue
                    changed = True
                    for child in list(cell):
                        if child.tag.rsplit("}", 1)[-1] in {"v", "is"}:
                            cell.remove(child)
                    if value in (None, ""):
                        cell.attrib.pop("t", None)
                        continue
                    if isinstance(value, str):
                        cell.attrib["t"] = "inlineStr"
                        inline = ET.SubElement(cell, f"{{{_NS['main']}}}is")
                        ET.SubElement(inline, f"{{{_NS['main']}}}t").text = value
                    else:
                        try:
                            number = float(value)
                        except (TypeError, ValueError) as exc:
                            raise ValueError("workbook values must be numeric or text") from exc
                        if number != number or abs(number) == float("inf"):
                            raise ValueError("workbook values must be finite")
                        cell.attrib.pop("t", None)
                        ET.SubElement(cell, f"{{{_NS['main']}}}v").text = str(value)
                replacements[part] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            if not changed:
                return {"worksheet_part": sheet_part, "summary_part": summary_part, "worksheet_parts": [], "backup": None, "preserved_formula_cells": sorted(preserved), "unchanged": True}
            with tempfile.NamedTemporaryFile(prefix=f".{resolved.name}.", suffix=".tmp", dir=resolved.parent, delete=False) as tmp:
                temp_path = Path(tmp.name)
            with zipfile.ZipFile(temp_path, "w") as output:
                for info in source.infolist():
                    output.writestr(info, replacements.get(info.filename, source.read(info.filename)))
        with zipfile.ZipFile(temp_path, "r") as check:
            if check.namelist() != names:
                raise ValueError("workbook package validation failed")
            for part in replacements:
                ET.fromstring(check.read(part))
        backup_root = Path(backup_dir)
        backup_root.mkdir(parents=True, exist_ok=True)
        backup = backup_root / f"{resolved.stem}-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}{resolved.suffix}"
        shutil.copy2(resolved, backup)
        os.replace(temp_path, resolved)
        return {"worksheet_part": sheet_part, "summary_part": summary_part, "worksheet_parts": list(replacements), "backup": backup, "preserved_formula_cells": sorted(preserved), "unchanged": False}


def workbook_path_for_date(value: str, workbook_root: str | Path) -> Path:
    """Resolve a month workbook below the explicitly supplied root only."""
    try:
        day = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("date must be a real YYYY-MM-DD calendar date") from exc
    if day.isoformat() != value:
        raise ValueError("date must be YYYY-MM-DD")
    root = Path(workbook_root).expanduser().resolve(strict=True)
    filename = f"{day.year}년 {day.month}월 수변전 일지 - 본관.xlsx"
    nested = (root / f"{day.year}년" / filename).resolve()
    candidate = nested if nested.is_file() else (root / filename).resolve()
    if candidate.parent not in (root, (root / f"{day.year}년").resolve()):
        raise ValueError("workbook must be directly inside the configured workbook root")
    return candidate


def inspect_workbook(path: str | Path) -> dict:
    """Inspect workbook structure without saving or otherwise modifying it."""
    source = Path(path).resolve(strict=True)
    with zipfile.ZipFile(source, "r") as archive:
        printer_settings_count = sum(
            name.startswith("xl/printerSettings/") and name.endswith(".bin")
            for name in archive.namelist()
        )
    book = load_workbook(source, read_only=True, data_only=False)
    try:
        sheet_names = list(book.sheetnames)
        day_sheet_count = sum(bool(re.fullmatch(r"\d{2}일", name)) for name in sheet_names)
        return {
            "path": str(source),
            "sheet_names": sheet_names,
            "day_sheet_count": day_sheet_count,
            "printer_settings_count": printer_settings_count,
        }
    finally:
        book.close()


def _literal(sheet, address, cached_sheet=None):
    value = sheet[address].value
    if isinstance(value, str) and value.startswith("="):
        return cached_sheet[address].value if cached_sheet is not None else None
    return value


def _read_day_record(book, cached_book, summary, cached_summary, year: int, month: int, day: int) -> dict:
    sheet_name = f"{day:02d}일"
    if sheet_name not in book.sheetnames:
        raise ValueError(f"missing day sheet: {sheet_name}")
    sheet = book[sheet_name]
    cached_sheet = cached_book[sheet_name]
    observations = {slot: {group: {} for group in (*OBSERVATION_COLUMNS,)} for slot in TIME_SLOTS}
    for index, slot in enumerate(TIME_SLOTS):
        row = 10 + index
        for group, fields in OBSERVATION_COLUMNS.items():
            for field, column in fields.items():
                if group in ("main", "vcb"):
                    source_row = row
                elif group in ("transformer", "chiller") or (group == "secondary" and not field.startswith("low")):
                    source_row = row + 10
                else:
                    source_row = row + 20
                address = f"{column}{source_row}"
                observations[slot][group][field] = _literal(sheet, address, cached_sheet)
    meter_values = {kind: [None] * len(METER_LABELS) for kind in ("current", "previous")}
    for kind, row in (("current", 38), ("previous", 39)):
        for index, label in enumerate(METER_LABELS):
            if label in DAILY_METER_COLUMNS:
                address = f"{DAILY_METER_COLUMNS[label]}{row}"
                meter_values[kind][index] = _literal(sheet, address, cached_sheet)

    monthly_close = {}
    for close_kind, labels in MONTH_CLOSE_LABELS.items():
        monthly_close[close_kind] = {reading_kind: [] for reading_kind in ("current", "previous")}
        columns = MONTHLY_CLOSE_COLUMNS[close_kind]
        for reading_kind in ("current", "previous"):
            monthly_close[close_kind][reading_kind] = [
                _literal(sheet, f"{columns[reading_kind]}{28 + index}", cached_sheet) for index, _ in enumerate(labels)
            ]

    summary_row = day + 1
    return {
        "date": f"{year:04d}-{month:02d}-{day:02d}",
        "operator": _literal(summary, f"J{summary_row}", cached_summary) or "",
        "notes": _literal(sheet, "C44", cached_sheet) or "",
        "observations": observations,
        "timeEdit": {slot: False for slot in TIME_SLOTS},
        "meters": {"current": meter_values["current"], "previous": meter_values["previous"], "monthlyClose": monthly_close},
    }


def import_workbook_month(db, workbook_root: str | Path, month: str, *, overwrite: bool = False) -> dict:
    """Import one month from the workbook located strictly under workbook_root.

    The complete source month is parsed before opening the DB transaction. By
    default, any existing date in the month blocks the import to prevent silent
    replacement of manually entered records.
    """
    try:
        year, month_number = (int(part) for part in month.split("-", 1))
        first = date(year, month_number, 1)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("month must be YYYY-MM") from exc
    if first.strftime("%Y-%m") != month:
        raise ValueError("month must be YYYY-MM")
    source_path = workbook_path_for_date(first.isoformat(), workbook_root)
    days = calendar.monthrange(year, month_number)[1]
    if not overwrite and db.execute("SELECT 1 FROM daily_records WHERE record_date LIKE ? LIMIT 1", (f"{month}%",)).fetchone():
        raise ValueError(f"records for {month} already exist; refusing to overwrite")
    # The month importer seeks hundreds of known cells. Normal in-memory
    # loading avoids the repeated XML rescans incurred by random access in
    # ReadOnlyWorksheet; neither workbook object is ever saved.
    source = load_workbook(source_path, read_only=False, data_only=True)
    try:
        if "수식(월변경)" not in source.sheetnames:
            raise ValueError("missing month summary sheet")
        summary = source["수식(월변경)"]
        records = [_read_day_record(source, source, summary, summary, year, month_number, day) for day in range(1, days + 1)]
    finally:
        source.close()

    with db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT record_date FROM daily_records WHERE record_date LIKE ? ORDER BY record_date", (f"{month}%",)).fetchall()
        if existing and not overwrite:
            raise ValueError(f"records for {month} already exist; refusing to overwrite")
        for record in records:
            save_record(db, record, commit=False, preserve_invalid_as_text=True)
    warnings = []
    for row in db.execute("SELECT record_date,time_slot,group_key,field_key,source_text FROM inspection_values WHERE record_date LIKE ? AND source_text IS NOT NULL ORDER BY record_date,time_slot,group_key,field_key", (f"{month}%",)):
        warnings.append({"date": row["record_date"], "time": row["time_slot"], "group": row["group_key"], "field": row["field_key"], "source_text": row["source_text"]})
    for table, key_fields in (("meter_values", ("meter_label", "reading_kind")), ("monthly_close_values", ("close_kind", "meter_label", "reading_kind"))):
        rows = db.execute(f"SELECT * FROM {table} WHERE record_date LIKE ? AND source_text IS NOT NULL", (f"{month}%",))
        warnings.extend({"date": row["record_date"], **{key: row[key] for key in key_fields}, "source_text": row["source_text"]} for row in rows)
    return {"source": str(source_path), "month": month, "imported_days": len(records), "overwritten": bool(existing), "warning_count": len(warnings), "warnings": warnings}
