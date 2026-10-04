import tempfile
import unittest
from pathlib import Path

from server.db import connect, initialize_database, load_record, save_record


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "records.sqlite3"
        initialize_database(self.path)
        self.db = connect(self.path)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_saves_and_reloads_each_inspection_field(self):
        record = {"date": "2026-10-01", "operator": "Kim", "notes": "ok",
                  "observations": {"08:00": {"main": {"kv": 22.9, "a1": 0}, "secondary": {"batteryA": 1.2}}},
                  "timeEdit": {"08:00": True}}
        save_record(self.db, record)
        loaded = load_record(self.db, record["date"])
        self.assertEqual(loaded["observations"]["08:00"]["main"]["kv"], 22.9)
        self.assertEqual(loaded["observations"]["08:00"]["main"]["a1"], 0)
        self.assertEqual(loaded["observations"]["08:00"]["secondary"]["batteryA"], 1.2)
        self.assertTrue(loaded["timeEdit"]["08:00"])
        self.assertEqual(loaded["operator"], "Kim")
        self.assertEqual(loaded["notes"], "ok")

    def test_blank_values_remain_null_while_zero_is_zero(self):
        save_record(self.db, {"date": "2026-10-02", "observations": {"08:00": {"main": {"kv": 0, "a1": None}}}})
        rows = self.db.execute("SELECT field_key, value FROM inspection_values ORDER BY field_key").fetchall()
        self.assertEqual([(row["field_key"], row["value"]) for row in rows], [("a1", None), ("kv", 0.0)])
        loaded = load_record(self.db, "2026-10-02")
        self.assertEqual(loaded["observations"]["08:00"]["main"]["kv"], 0)
        self.assertIsNone(loaded["observations"]["08:00"]["main"]["a1"])

    def test_monthly_meter_values_round_trip(self):
        record = {"date": "2026-10-03", "meters": {"current": [1, None, 0, None, None, 9, 10],
                  "previous": [0, None, None, None, None, None, None], "monthlyClose": {
                      "substation": {"current": [1, 2], "previous": [0, 1]},
                      "industrial": {"current": [4], "previous": [3]}}}}
        save_record(self.db, record)
        loaded = load_record(self.db, "2026-10-03")
        self.assertEqual(loaded["meters"]["current"], [1, None, 0, None, None, 9, 10])
        self.assertEqual(loaded["meters"]["monthlyClose"]["substation"]["current"][:2], [1, 2])
        self.assertEqual(loaded["meters"]["monthlyClose"]["industrial"]["previous"][0], 3)


if __name__ == "__main__":
    unittest.main()
