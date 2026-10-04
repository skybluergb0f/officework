import test from 'node:test';
import assert from 'node:assert/strict';
import {
  calculateUsage,
  calculateDailySummary,
  createEmptyRecord,
  serializeRecords,
  parseRecords,
} from '../gangnam-annex-log.js';

test('calculateUsage computes a scaled difference', () => {
  assert.deepEqual(calculateUsage(101, 100, 2400), { status: 'ok', value: 2400, warning: '' });
});

test('calculateUsage keeps blank input pending and accepts zero', () => {
  assert.equal(calculateUsage('', 100, 2400).status, 'pending');
  assert.equal(calculateUsage(0, 0, 2400).value, 0);
});

test('calculateUsage exposes a warning for negative usage', () => {
  const result = calculateUsage(99, 100, 1);
  assert.equal(result.status, 'warning');
  assert.match(result.warning, /전일/);
});

test('calculateDailySummary combines main and annex electrical groups', () => {
  const record = createEmptyRecord('2026-10-01');
  record.electric.main = { current: [10, 20, 30], previous: [9, 18, 29], multipliers: [1, 1, 1] };
  record.electric.annex = { current: [4, 5, 6], previous: [3, 4, 5], multipliers: [1, 1, 1] };
  const summary = calculateDailySummary(record);
  assert.equal(summary.main.total, 4);
  assert.equal(summary.annex.total, 3);
  assert.equal(summary.grandTotal, 7);
});

test('records round-trip through safe JSON backup', () => {
  const records = { '2026-10-01': createEmptyRecord('2026-10-01') };
  const parsed = parseRecords(serializeRecords(records));
  assert.deepEqual(parsed, records);
  assert.deepEqual(parseRecords('{not-json'), {});
});
