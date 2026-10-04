"""Read-only helpers for validating monthly source workbooks."""
from __future__ import annotations

import re
import zipfile
import calendar
from datetime import date
from pathlib import Path

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


def workbook_path_for_date(value: str, workbook_root: str | Path) -> Path:
    """Resolve a month workbook below the explicitly supplied root only."""
    try:
        day = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("date must be a real YYYY-MM-DD calendar date") from exc
    if day.isoformat() != value:
        raise ValueError("date must be YYYY-MM-DD")
    root = Path(workbook_root).expanduser().resolve(strict=True)
    candidate = (root / f"{day.year}년 {day.month}월 수변전 일지 - 본관.xlsx").resolve()
    if candidate.parent != root:
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
        # TR1/TR2 are the source's two transformer temperature readings. The
        # separate transformer auxiliary block has five columns, named below.
        observations[slot]["transformer"]["trTemp"] = None

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
