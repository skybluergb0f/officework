"""Read-only helpers for validating monthly source workbooks."""
from __future__ import annotations

import re
import zipfile
from datetime import date
from pathlib import Path

from openpyxl import load_workbook


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
