PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS daily_records (
  record_date TEXT PRIMARY KEY,
  operator TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inspection_values (
  record_date TEXT NOT NULL REFERENCES daily_records(record_date) ON DELETE CASCADE,
  time_slot TEXT NOT NULL,
  group_key TEXT NOT NULL,
  field_key TEXT NOT NULL,
  value REAL,
  PRIMARY KEY(record_date, time_slot, group_key, field_key)
);
CREATE TABLE IF NOT EXISTS record_time_controls (
  record_date TEXT NOT NULL REFERENCES daily_records(record_date) ON DELETE CASCADE,
  time_slot TEXT NOT NULL,
  allow_edit INTEGER NOT NULL DEFAULT 0 CHECK(allow_edit IN (0,1)),
  PRIMARY KEY(record_date, time_slot)
);
CREATE TABLE IF NOT EXISTS meter_values (
  record_date TEXT NOT NULL REFERENCES daily_records(record_date) ON DELETE CASCADE,
  meter_label TEXT NOT NULL,
  reading_kind TEXT NOT NULL CHECK(reading_kind IN ('current','previous')),
  value REAL,
  PRIMARY KEY(record_date, meter_label, reading_kind)
);
CREATE TABLE IF NOT EXISTS monthly_close_values (
  record_date TEXT NOT NULL REFERENCES daily_records(record_date) ON DELETE CASCADE,
  close_kind TEXT NOT NULL CHECK(close_kind IN ('substation','industrial')),
  meter_label TEXT NOT NULL,
  reading_kind TEXT NOT NULL CHECK(reading_kind IN ('current','previous')),
  value REAL,
  PRIMARY KEY(record_date, close_kind, meter_label, reading_kind)
);
CREATE TABLE IF NOT EXISTS workbook_sync (
  record_date TEXT PRIMARY KEY REFERENCES daily_records(record_date) ON DELETE CASCADE,
  status TEXT NOT NULL CHECK(status IN ('pending','synced','failed')),
  error TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS inspection_values_date_idx ON inspection_values(record_date);
