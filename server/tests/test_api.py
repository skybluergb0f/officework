import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from server.app import create_app
from server.db import connect, initialize_database, load_record, save_record


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data"


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.database = root / "api.sqlite3"
        self.workbooks = root / "workbooks"
        self.workbooks.mkdir()
        initialize_database(self.database)
        self.app = create_app(self.database, self.workbooks)
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def test_record_routes_are_available_without_authentication(self):
        with connect(self.database) as db:
            save_record(db, {"date": "2026-09-01", "observations": {}})
        read = self.client.get("/api/records?month=2026-09")
        self.assertEqual(read.status_code, 200, read.text)
        self.assertIn("2026-09-01", read.json()["records"])
        written = self.client.put("/api/records/2026-09-02", json={"date": "2026-09-02", "observations": {}})
        self.assertEqual(written.status_code, 200, written.text)

    def test_health_is_available_without_exposing_record_values(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

    def test_put_round_trips_typed_fields_and_marks_excel_pending(self):
        record = {"date": "2026-09-01", "operator": "Kim", "notes": "routine",
                  "observations": {"08:00": {"main": {"kv": 22.9, "a1": 0}, "secondary": {"batteryA": 0}}},
                  "timeEdit": {"08:00": True}, "meters": {"current": [1, None, 0, None, None, 9, 10],
                  "previous": [0, None, None, None, None, None, None], "monthlyClose": {
                      "substation": {"current": [1, 2], "previous": [0, 1]},
                      "industrial": {"current": [4], "previous": [3]}}}}
        response = self.client.put("/api/records/2026-09-01", json=record)
        self.assertEqual(response.status_code, 200, response.text)
        with connect(self.database) as db:
            saved = load_record(db, "2026-09-01")
            sync = db.execute("SELECT status FROM workbook_sync WHERE record_date=?", ("2026-09-01",)).fetchone()
        self.assertEqual(saved["observations"]["08:00"]["main"]["kv"], 22.9)
        self.assertEqual(saved["observations"]["08:00"]["main"]["a1"], 0)
        self.assertEqual(saved["meters"]["current"][-2:], [9, 10])
        self.assertTrue(saved["timeEdit"]["08:00"])
        self.assertEqual(sync["status"], "pending")

    def test_invalid_record_date_and_unknown_field_are_rejected(self):
        bad_date = {"date": "2026-02-30"}
        self.assertEqual(self.client.put("/api/records/2026-02-30", json=bad_date).status_code, 422)
        bad_field = {"date": "2026-09-01", "observations": {"08:00": {"main": {"notAField": 1}}}}
        self.assertEqual(self.client.put("/api/records/2026-09-01", json=bad_field).status_code, 422)

    def test_invalid_meter_and_time_edit_shapes_are_rejected(self):
        bad_meters = {"date": "2026-09-01", "observations": {}, "meters": ["bad"]}
        bad_time_edit = {"date": "2026-09-01", "observations": {}, "timeEdit": ["bad"]}
        self.assertEqual(self.client.put("/api/records/2026-09-01", json=bad_meters).status_code, 422)
        self.assertEqual(self.client.put("/api/records/2026-09-01", json=bad_time_edit).status_code, 422)

    def test_excel_sync_failure_is_not_print_ready(self):
        record = {"date": "2026-09-01", "observations": {}}
        self.client.put("/api/records/2026-09-01", json=record)
        response = self.client.post("/api/records/2026-09-01/sync-excel")
        self.assertEqual(response.status_code, 502)
        self.assertFalse(response.json()["printReady"])


class MonthLoadApiTests(unittest.TestCase):
    def test_month_read_imports_data_copy_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "records.sqlite3"
            initialize_database(database)
            client = TestClient(create_app(database, DATA_ROOT))
            first = client.get("/api/records?month=2026-10")
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(len(first.json()["records"]), 31)
            second = client.get("/api/records?month=2026-10")
            self.assertEqual(len(second.json()["records"]), 31)
            with connect(database) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM daily_records").fetchone()[0], 31)
            client.close()


if __name__ == "__main__":
    unittest.main()
