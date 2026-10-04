import hashlib
import unittest
from pathlib import Path

from server.workbook import inspect_workbook, workbook_path_for_date


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA = PROJECT_ROOT / "data"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class DataWorkbookTests(unittest.TestCase):
    def test_resolves_only_the_supplied_data_month_copy(self):
        path = workbook_path_for_date("2026-10-01", DATA)
        self.assertEqual(path, DATA / "2026년 10월 수변전 일지 - 본관.xlsx")
        self.assertTrue(path.is_file())

    def test_data_month_copies_have_daily_sheets_and_print_parts(self):
        for month in ("09", "10"):
            with self.subTest(month=month):
                path = workbook_path_for_date(f"2026-{month}-01", DATA)
                before = sha256(path)
                report = inspect_workbook(path)
                self.assertIn("수식(월변경)", report["sheet_names"])
                self.assertIn("01일", report["sheet_names"])
                self.assertEqual(report["day_sheet_count"], 31)
                self.assertGreaterEqual(report["printer_settings_count"], 31)
                self.assertEqual(sha256(path), before, "inspection must not modify the data copy")

    def test_day_must_be_a_real_calendar_date(self):
        with self.assertRaises(ValueError):
            workbook_path_for_date("2026-02-30", DATA)


if __name__ == "__main__":
    unittest.main()
