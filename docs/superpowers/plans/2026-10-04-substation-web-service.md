# Substation Web Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the existing substation log as a Windows-accessible HTTPS service with per-field SQLite persistence and synchronized writes to the NAS Excel original before print.

**Architecture:** FastAPI serves the existing same-origin UI and JSON API on `127.0.0.1:18790`, behind HTTPS Nginx at `/substation-log/`. SQLite on the server's local disk stores each observation, meter and monthly-close field separately. The existing monthly workbook on the Synology NFS share is imported into SQLite on first read and remains the Excel output projection for the explicit “원본 엑셀 저장 후 인쇄” action.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Python `sqlite3`, read-only openpyxl, ZIP/XML package editing, systemd, Nginx, existing HTML/CSS/JavaScript.

**Spec:** `docs/superpowers/specs/2026-10-04-substation-web-service-design.md`

## Global Constraints

- Bind FastAPI only to `127.0.0.1:18790`; serve Windows users through existing HTTPS Nginx at `/substation-log/`.
- Keep SQLite at `data/substation-log.sqlite3` on local server storage, not on NFS; use environment settings for paths and authentication.
- Use the NAS monthly original at `/home/nuri/ftp_hdd/syn_nuri_work/02. 일지/[01 매일] 본관 - 수변전 일지/{year}년/{year}년 {month}월 수변전 일지 - 본관.xlsx`.
- Store each UI data field as a distinct typed SQLite value; do not store the complete record as one JSON blob.
- Keep the existing workbook field mapping, print formatting, and manual-print behavior; Excel synchronization failure must prevent browser printing.
- Update only target worksheet cell values in the OOXML ZIP; preserve all other package parts byte-for-byte, including the workbook's 31 `printerSettings` parts.
- Back up and validate workbooks before atomic replacement; never write the original during read/import.
- Do not commit workbooks, SQLite database files, backups, or credentials.
- Do not log credentials or measurement values.

## Review Focus

- Empty input and numeric zero must remain distinct (`NULL` versus `0`) across SQLite save/reload.
- An invalid date, missing workbook, or missing day sheet must not create a workbook/sheet or partially write a record.
- Repeated or concurrent writes to one date must not lose fields; Excel sync must remain retryable after failure.
- Formula cells and unrelated styles/values in the original workbook must survive projection writes.
- Missing/incorrect auth must block record reads/writes; manual print must not write, and Excel-sync failure must not print.

---

### Task 1: Add Field-Level SQLite Schema and Repository

**Files:**
- Create: `server/db.py`
- Create: `server/schema.sql`
- Create: `server/tests/test_db.py`
- Modify: `.gitignore`

**Interfaces:**
- `initialize_database(path)` creates schema and indexes idempotently.
- `save_record(connection, record)` stores record header, time-edit flags, each time/group/field value, meter readings, monthly-close readings, and pending Excel-sync status in one SQLite transaction.
- `load_record(connection, date)` reconstructs the existing browser record shape from typed database rows.
- `mark_excel_sync(connection, date, status, error=None)` records pending/synced/failed projection state without measurement values in logs.

- [x] Write `test_saves_and_reloads_each_inspection_field`, `test_blank_values_remain_null_while_zero_is_zero`, and `test_monthly_meter_values_round_trip`; run `python3 -m unittest server.tests.test_db` and confirm failures because `server.db` does not exist.
- [x] Implement normalized tables: `daily_records`, `inspection_values`, `record_time_controls`, `meter_values`, `monthly_close_values`, and `workbook_sync`; map every UI key to a stable `(group_key, field_key)` pair.
- [x] Run `python3 -m unittest server.tests.test_db`; expected: all named tests pass and database initialization is repeatable.
- [x] Ignore `*.sqlite3`, SQLite WAL/SHM files, and `data/`; verify `git check-ignore data/substation-log.sqlite3`.
- [x] Initialize the production-path SQLite file at `data/substation-log.sqlite3` on the Ubuntu host; it is schema-only and contains no workbook data yet.

### Task 2: Import and Project SQLite Records to Monthly Excel Workbooks

**Files:**
- Create: `server/workbook.py`
- Create: `server/tests/test_workbook.py`
- Runtime input: NAS September and October 2026 original workbooks (read-only for initial import)

**Interfaces:**
- `workbook_path_for_date(date, workbook_root)` resolves the monthly NAS workbook using the configured `{year}년` layout.
- `read_workbook_record(path, date)` returns a browser-shaped record without creating or modifying workbook content.
- `write_workbook_record(path, date, record, backup_dir)` writes mapped values only, with per-file serialization, timestamped backup, temporary output, reopen verification, and atomic replacement.
- `WORKBOOK_FIELD_MAP` maps every supported observation, operator, note, meter and monthly-close field to a concrete worksheet cell.

- [x] Begin workbook tests using only the September and October files inside project `data/`; verify month-path resolution, 31 daily sheets, retained printer-settings parts, invalid-date rejection, and unchanged SHA-256 after inspection. No NAS original is an input to these tests.
- [ ] Add write tests that copy the `data/` workbook into a temporary test directory, then verify `test_read_import_does_not_modify_source` and `test_projection_preserves_unmapped_cells_and_formulas` against the temporary copy.
- [ ] Inspect the `data/` copies read-only to finalize cell coordinates and identify formulas, merged cells, styles, and unsupported workbook features. Implement explicit date-to-sheet and UI-field-to-cell mappings; daily meter 9/10 have no matching source cells and must be reported as SQLite-only values.
- [ ] Implement reads with openpyxl in read-only mode and writes by patching only the target cells in their worksheet XML inside the OOXML ZIP. Add backup/temporary/reopen validation/atomic replace. Never open/save the live source as part of a GET/import.
- [ ] Run `python3 -m unittest server.tests.test_workbook`; expected: tests pass on generated workbooks, all non-target ZIP parts remain byte-identical, and all printer-setting binaries survive. Separately compare a disposable copy of each 2026 source month before using live paths.

### Task 3: Add Authenticated API, SQLite Import-on-Read, and UI Binding

**Files:**
- Create: `server/app.py`
- Create: `server/tests/test_api.py`
- Create: `server/requirements.txt`
- Modify: `substation-main-log.html`
- Modify: `README.md`

**Interfaces:**
- `GET /api/health` returns readiness without workbook values.
- `GET /api/records?month=YYYY-MM` returns the month's record map from SQLite and imports missing day sheets from that month's workbook once.
- `PUT /api/records/{date}` commits validated field-level values to SQLite and records Excel sync state.
- `POST /api/records/{date}/sync-excel` projects the stored record into its NAS workbook and marks sync success/failure.
- All record routes require HTTP Basic auth. The browser print action runs only after SQLite save and Excel projection both succeed.

- [ ] Write tests `test_record_routes_require_auth`, `test_month_read_imports_unseen_workbook_days_once`, `test_put_round_trips_sqlite_fields`, and `test_excel_sync_error_prevents_print_ready_response`; run `python3 -m unittest server.tests.test_api` and confirm the expected failures before implementation.
- [ ] Implement FastAPI routes, request validation, environment-based SQLite/workbook paths, authentication, retryable outbox processing, and safe errors.
- [ ] Replace the UI's `127.0.0.1:8766` bridge call with same-origin API requests. Bind all visible form paths to field-level persistence; report meter 9/10 as SQLite-only because the source workbook has no daily meter cells; keep manual print local-only, and print only after successful Excel sync.
- [ ] Run `python3 -m unittest discover -s server/tests` and existing `node --test test/*.test.mjs`; expected: all server and existing UI tests pass.

### Task 4: Deploy on the Existing Ubuntu Host

**Files:**
- Create: `deploy/substation-log-web.service`
- Create: `deploy/nginx-substation-log.conf`
- Create: `.env.example`
- Modify: `README.md`

- [ ] Add a systemd service running as `nuri` on loopback port `18790`, with local SQLite path and NAS workbook root configured outside Git.
- [ ] Add the verified NFS export to `/etc/fstab` with `_netdev,nofail,x-systemd.automount` so the configured NAS workbook path is available after reboot; retain the confirmed NFSv3 mount options.
- [ ] Add an HTTPS Nginx route for `/substation-log/` without changing existing `/`, `/qrfire/`, or other handlers; run `nginx -t` before reload.
- [ ] Configure authentication from a root-protected environment file; if credentials are unset, fail closed and do not expose record routes.
- [ ] Install pinned Python dependencies in a project venv; start the service, verify loopback health, HTTPS routing, correct auth behavior, and existing Nginx routes.
- [ ] Verify the SQLite DB is on local storage, the month workbook path resolves to the NAS file, the source hash is unchanged after GET/import, and no data/secrets are Git-tracked.

### Task 5: Activate and Publish the Service

- [ ] Verify SQLite round trips for every UI field using a temporary database and verify Excel mapping against disposable September/October workbook copies.
- [ ] Enable the configured live NAS workbook paths only after copy-based verification; create the first backup before any live write.
- [ ] Verify manual print is write-free, SQLite save/reload persists, successful Excel sync enables print, and failed sync leaves print disabled.
- [ ] Commit application code, schema, tests, deployment templates, and docs; push only source/config templates to `skybluergb0f/officework`.
- [ ] Confirm `data/substation-log.sqlite3`, `.xlsx`, backups, and `.env` remain ignored and the deployed service is active at `https://nuri001.duckdns.org/substation-log/`.
