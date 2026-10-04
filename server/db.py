"""Field-level SQLite persistence for the substation daily log."""
from __future__ import annotations

import sqlite3
from contextlib import nullcontext
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

TIME_SLOTS = ("08:00", "11:00", "14:00", "16:00", "23:59")
METER_LABELS = ("4", "5", "6", "7", "8", "9", "10")
MONTH_CLOSE_LABELS = {"substation": ("9", "10", "11", "12", "13", "14", "15"),
                      "industrial": ("4", "5", "6", "7", "8", "10", "11")}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _valid_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("date must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ValueError("date must be YYYY-MM-DD")
    return value


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("boolean is not a numeric reading")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("reading must be numeric or blank") from exc
    if result != result or result in (float("inf"), float("-inf")):
        raise ValueError("reading must be finite")
    return result


def connect(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(path), timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 30000")
    return db


def initialize_database(path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with connect(target) as db:
        db.executescript((Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8"))
        for table in ("inspection_values", "meter_values", "monthly_close_values"):
            columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
            if "source_text" not in columns:
                db.execute(f"ALTER TABLE {table} ADD COLUMN source_text TEXT")


def save_record(db: sqlite3.Connection, record: dict[str, Any], *, commit: bool = True, preserve_invalid_as_text: bool = False) -> None:
    record_date = _valid_date(record.get("date"))
    observations = record.get("observations") or {}
    meters = record.get("meters") or {}
    now = _now()
    with (db if commit else nullcontext()):
        db.execute("INSERT INTO daily_records(record_date,operator,notes,updated_at) VALUES(?,?,?,?) "
                   "ON CONFLICT(record_date) DO UPDATE SET operator=excluded.operator,notes=excluded.notes,updated_at=excluded.updated_at",
                   (record_date, str(record.get("operator") or ""), str(record.get("notes") or ""), now))
        for table in ("inspection_values", "record_time_controls", "meter_values", "monthly_close_values"):
            db.execute(f"DELETE FROM {table} WHERE record_date=?", (record_date,))
        for time_slot in TIME_SLOTS:
            if time_slot not in observations and time_slot not in (record.get("timeEdit") or {}):
                continue
            if time_slot not in TIME_SLOTS:
                raise ValueError("unsupported time slot")
            db.execute("INSERT INTO record_time_controls VALUES(?,?,?)", (record_date, time_slot, int(bool((record.get("timeEdit") or {}).get(time_slot, False)))))
            groups = observations.get(time_slot) or {}
            for group_key, fields in groups.items():
                if not isinstance(fields, dict):
                    raise ValueError("observation group must be an object")
                for field_key, value in fields.items():
                    try:
                        numeric_value = _number(value)
                    except ValueError as exc:
                        if not preserve_invalid_as_text or value is None:
                            raise ValueError(f"invalid reading {record_date} {time_slot} {group_key}.{field_key}: {value!r}") from exc
                        numeric_value, source_text = None, str(value)
                    else:
                        source_text = None
                    db.execute("INSERT INTO inspection_values(record_date,time_slot,group_key,field_key,value,source_text) VALUES(?,?,?,?,?,?)", (record_date, time_slot, str(group_key), str(field_key), numeric_value, source_text))
        for kind in ("current", "previous"):
            values = meters.get(kind) or []
            for index, label in enumerate(METER_LABELS):
                val = values[index] if index < len(values) else None
                try:
                    numeric_value, source_text = _number(val), None
                except ValueError as exc:
                    if not preserve_invalid_as_text or val is None:
                        raise ValueError(f"invalid meter reading {record_date} meter {label} {kind}: {val!r}") from exc
                    numeric_value, source_text = None, str(val)
                db.execute("INSERT INTO meter_values(record_date,meter_label,reading_kind,value,source_text) VALUES(?,?,?,?,?)", (record_date, label, kind, numeric_value, source_text))
        for close_kind, labels in MONTH_CLOSE_LABELS.items():
            section = (meters.get("monthlyClose") or {}).get(close_kind) or {}
            for kind in ("current", "previous"):
                values = section.get(kind) or []
                for index, label in enumerate(labels):
                    val = values[index] if index < len(values) else None
                    try:
                        numeric_value, source_text = _number(val), None
                    except ValueError as exc:
                        if not preserve_invalid_as_text or val is None:
                            raise ValueError(f"invalid monthly-close reading {record_date} {close_kind} meter {label} {kind}: {val!r}") from exc
                        numeric_value, source_text = None, str(val)
                    db.execute("INSERT INTO monthly_close_values(record_date,close_kind,meter_label,reading_kind,value,source_text) VALUES(?,?,?,?,?,?)", (record_date, close_kind, label, kind, numeric_value, source_text))


def load_record(db: sqlite3.Connection, record_date: str) -> dict[str, Any] | None:
    record_date = _valid_date(record_date)
    header = db.execute("SELECT * FROM daily_records WHERE record_date=?", (record_date,)).fetchone()
    if not header:
        return None
    result: dict[str, Any] = {"date": record_date, "operator": header["operator"], "notes": header["notes"],
                              "observations": {slot: {} for slot in TIME_SLOTS},
                              "timeEdit": {slot: False for slot in TIME_SLOTS},
                              "meters": {"current": [], "previous": [], "monthlyClose": {}}}
    for row in db.execute("SELECT * FROM inspection_values WHERE record_date=?", (record_date,)):
        result["observations"].setdefault(row["time_slot"], {}).setdefault(row["group_key"], {})[row["field_key"]] = row["value"] if row["value"] is not None else row["source_text"]
    for row in db.execute("SELECT * FROM record_time_controls WHERE record_date=?", (record_date,)):
        result["timeEdit"][row["time_slot"]] = bool(row["allow_edit"])
    for kind in ("current", "previous"):
        rows = {r["meter_label"]: r["value"] if r["value"] is not None else r["source_text"] for r in db.execute("SELECT * FROM meter_values WHERE record_date=? AND reading_kind=?", (record_date, kind))}
        result["meters"][kind] = [rows.get(label) for label in METER_LABELS]
    for close_kind, labels in MONTH_CLOSE_LABELS.items():
        section = {kind: [] for kind in ("current", "previous")}
        for kind in section:
            rows = {r["meter_label"]: r["value"] if r["value"] is not None else r["source_text"] for r in db.execute("SELECT * FROM monthly_close_values WHERE record_date=? AND close_kind=? AND reading_kind=?", (record_date, close_kind, kind))}
            section[kind] = [rows.get(label) for label in labels]
        result["meters"]["monthlyClose"][close_kind] = section
    return result


def mark_excel_sync(db: sqlite3.Connection, record_date: str, status: str, error: str | None = None) -> None:
    record_date = _valid_date(record_date)
    if status not in {"pending", "synced", "failed"}:
        raise ValueError("unsupported sync status")
    db.execute("INSERT INTO workbook_sync VALUES(?,?,?,?) ON CONFLICT(record_date) DO UPDATE SET "
               "status=excluded.status,error=excluded.error,updated_at=excluded.updated_at",
               (record_date, status, error, _now()))
