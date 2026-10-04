"""Authenticated FastAPI service for the substation daily log."""
from __future__ import annotations

import os
import sqlite3
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from server.db import METER_LABELS, MONTH_CLOSE_LABELS, TIME_SLOTS, connect, initialize_database, load_record, mark_excel_sync, save_record
from server.workbook import import_workbook_month, workbook_path_for_date, write_workbook_record

PROJECT_ROOT = Path(__file__).resolve().parents[1]
UI_HTML = PROJECT_ROOT / "substation-main-log.html"
UI_JS = PROJECT_ROOT / "substation-main-log.js"


def _validate_record(record: dict, record_date: str) -> dict:
    if not isinstance(record, dict):
        raise ValueError("record must be an object")
    try:
        parsed = date.fromisoformat(record_date)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid date") from exc
    if parsed.isoformat() != record_date or record.get("date") != record_date:
        raise ValueError("date mismatch")
    allowed_groups = {"main", "vcb", "transformer", "chiller", "secondary"}
    time_edit = record.get("timeEdit", {})
    if not isinstance(time_edit, dict) or set(time_edit) - set(TIME_SLOTS):
        raise ValueError("timeEdit must map supported time slots")
    if any(not isinstance(allowed, bool) for allowed in time_edit.values()):
        raise ValueError("timeEdit values must be booleans")
    from server.workbook import OBSERVATION_COLUMNS
    observations = record.get("observations", {})
    if not isinstance(observations, dict):
        raise ValueError("observations must be an object")
    for slot, groups in observations.items():
        if slot not in {"08:00", "11:00", "14:00", "16:00", "23:59"} or not isinstance(groups, dict):
            raise ValueError("unsupported time slot")
        for group, fields in groups.items():
            if group not in allowed_groups or not isinstance(fields, dict):
                raise ValueError("unsupported observation group")
            allowed_fields = set(OBSERVATION_COLUMNS[group]) | ({"trTemp"} if group == "transformer" else set())
            if set(fields) - allowed_fields:
                raise ValueError("unsupported observation field")
    meters = record.get("meters", {})
    if not isinstance(meters, dict):
        raise ValueError("meters must be an object")
    for kind in ("current", "previous"):
        values = meters.get(kind, [])
        if not isinstance(values, list) or len(values) > len(METER_LABELS):
            raise ValueError("meter readings must be arrays")
    monthly = meters.get("monthlyClose", {})
    if not isinstance(monthly, dict) or set(monthly) - set(MONTH_CLOSE_LABELS):
        raise ValueError("monthlyClose must map supported groups")
    for close_kind in MONTH_CLOSE_LABELS:
        section = monthly.get(close_kind, {})
        if not isinstance(section, dict) or set(section) - {"current", "previous"}:
            raise ValueError("monthly-close group must contain reading arrays")
        for reading_kind, labels in (("current", MONTH_CLOSE_LABELS[close_kind]), ("previous", MONTH_CLOSE_LABELS[close_kind])):
            values = section.get(reading_kind, [])
            if not isinstance(values, list) or len(values) > len(labels):
                raise ValueError("monthly-close readings must be arrays")
    if not isinstance(record.get("operator", ""), str) or not isinstance(record.get("notes", ""), str):
        raise ValueError("operator and notes must be text")
    return record


def create_app(database_path: str | Path | None = None, workbook_root: str | Path | None = None,
               ) -> FastAPI:
    database = Path(database_path or os.getenv("SUBSTATION_DB", PROJECT_ROOT / "data/substation-log.sqlite3"))
    workbook_dir = Path(workbook_root or os.getenv("SUBSTATION_WORKBOOK_ROOT", PROJECT_ROOT / "data"))
    initialize_database(database)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.database = database
    app.state.workbook_root = workbook_dir

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/")
    def index():
        return FileResponse(UI_HTML, media_type="text/html; charset=utf-8")

    @app.get("/substation-main-log.js")
    def javascript():
        return FileResponse(UI_JS, media_type="text/javascript; charset=utf-8")

    @app.get("/api/records")
    def get_records(month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")):
        with connect(database) as db:
            if not db.execute("SELECT 1 FROM daily_records WHERE record_date LIKE ? LIMIT 1", (month + "%",)).fetchone():
                try:
                    import_workbook_month(db, workbook_dir, month)
                except (ValueError, OSError, KeyError) as exc:
                    raise HTTPException(status_code=404, detail="Month workbook unavailable") from exc
            rows = db.execute("SELECT record_date FROM daily_records WHERE record_date LIKE ? ORDER BY record_date", (month + "%",)).fetchall()
            records = {row["record_date"]: load_record(db, row["record_date"]) for row in rows}
        return {"month": month, "records": records}

    @app.put("/api/records/{record_date}")
    async def put_record(record_date: str, request: Request):
        try:
            record = _validate_record(await request.json(), record_date)
            with connect(database) as db:
                save_record(db, record)
                mark_excel_sync(db, record_date, "pending")
        except (ValueError, sqlite3.Error) as exc:
            raise HTTPException(status_code=422, detail="Invalid record") from exc
        return {"ok": True, "date": record_date}

    @app.post("/api/records/{record_date}/sync-excel")
    def sync_excel(record_date: str):
        try:
            with connect(database) as db:
                record = load_record(db, record_date)
                if record is None:
                    raise ValueError("record not found")
                path = workbook_path_for_date(record_date, workbook_dir)
                result = write_workbook_record(path, record_date, record, PROJECT_ROOT / "backups")
                mark_excel_sync(db, record_date, "synced")
        except (ValueError, OSError, KeyError, sqlite3.Error) as exc:
            try:
                with connect(database) as db:
                    mark_excel_sync(db, record_date, "failed", type(exc).__name__)
            except (ValueError, sqlite3.Error):
                pass
            return JSONResponse(status_code=502, content={"ok": False, "printReady": False, "detail": "Excel synchronization failed"})
        return {"ok": True, "date": record_date, "printReady": True, "worksheet": result["worksheet_part"]}

    return app


app = create_app()
