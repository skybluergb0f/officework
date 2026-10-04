# 강남별관 종합일지 HTML Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an offline, input-capable HTML daily operations log matching the workbook's daily workflow.

**Architecture:** A static HTML shell renders form sections and summary cards. A small ES module owns pure calculations and storage serialization so the same rules are testable in Node and in the browser. `localStorage` stores one record per date; JSON/CSV export keeps the data portable.

**Tech Stack:** HTML, CSS, vanilla JavaScript ES modules, Node's built-in test runner.

**Spec:** `docs/superpowers/specs/2026-10-02-gangnam-annex-log-design.md`

## Global Constraints

- Keep the source workbook unchanged.
- No external runtime dependencies or server required.
- Default month is October 2026 with dates 1 through 31.
- Blank meter inputs remain pending instead of being treated as zero.

## Review Focus

- Blank vs zero meter input: blank must show pending while zero remains a valid numeric value.
- Date switching: each date must retain its own record.
- Previous-day comparison: calculated usage must not become negative without a visible warning.
- Backup restore: malformed JSON must not erase existing records.
- CSV export: headers and Korean text must be UTF-8 compatible.

### Task 1: Calculation and persistence module

**Files:**
- Create: `gangnam-annex-log.js`
- Test: `test/gangnam-annex-log.test.mjs`

**Interfaces:**
- `calculateUsage(current, previous, multiplier)` returns `{ status, value, warning }`.
- `calculateDailySummary(record)` returns calculated usage groups and warnings.
- `createEmptyRecord(date)` returns a stable record shape.
- `serializeRecords(records)` / `parseRecords(json)` provide safe backup round-tripping.

- [ ] Write failing tests for numeric usage, blank input, negative usage warning, summary totals, and round-trip parsing.
- [ ] Run `node --test test/gangnam-annex-log.test.mjs` and confirm expected failures.
- [ ] Implement the pure functions and safe parser.
- [ ] Run the test file and confirm it passes.

### Task 2: Browser interface

**Files:**
- Create: `gangnam-annex-log.html`
- Modify: `gangnam-annex-log.js`

**Interfaces:**
- The page imports the module and binds form controls to one record keyed by `YYYY-MM-DD`.
- `renderRecord()` populates inputs and recalculated output; `saveCurrent()` persists the current date.

- [ ] Add semantic form sections for weather, electrical meters, HVAC/boiler, water meters, staffing, notes, and checklists.
- [ ] Add date navigation, save/reset, JSON backup/restore, and CSV export controls.
- [ ] Add responsive styling and visible pending/warning states.
- [ ] Run the Node tests after wiring the browser module.

### Task 3: Browser verification and cleanup

**Files:**
- Modify: `gangnam-annex-log.html` or `gangnam-annex-log.js` only if verification finds defects.

- [ ] Open the HTML in a browser and test date switching, local save, calculations, backup/restore, and CSV export.
- [ ] Confirm no console errors and that Korean labels render correctly.
- [ ] Remove temporary workbook-probe artifacts from the workspace.
