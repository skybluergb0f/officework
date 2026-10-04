import test from 'node:test';
import assert from 'node:assert/strict';
import {
  TIME_SLOTS,
  MONTH_CLOSE_LABELS,
  METRIC_GROUPS,
  calculateUsage,
  calculateMonthlyDifference,
  isInspectionTimeComplete,
  isInspectionTimeLocked,
  calculateMeterSummary,
  createEmptyRecord,
  serializeRecords,
  parseRecords,
} from '../substation-main-log.js';

test('keeps chiller fields in a separate metric group', () => {
  assert.deepEqual(METRIC_GROUPS.chiller.fields.map((field) => field[0]), ['chillerKw', 'chillerA', 'chiller2Kw', 'chiller2A', 'capacitorKw', 'capacitorA']);
  assert.equal(METRIC_GROUPS.secondary.fields.some((field) => field[0] === 'capacitorKw'), false);
});

test('groups low-voltage and rectifier battery fields from the workbook', () => {
  assert.deepEqual(METRIC_GROUPS.secondary.fields.map((field) => field[2]), [
    'lowLighting', 'lowLighting', 'lowLighting',
    'lowGeneral', 'lowGeneral', 'lowGeneral',
    'lowEmergency', 'lowEmergency', 'lowEmergency',
    'rectifierBattery', 'rectifierBattery', 'rectifierBattery',
  ]);
});

test('includes the transformer auxiliary fields from the workbook', () => {
  assert.deepEqual(METRIC_GROUPS.transformer.fields.map((field) => field[0]), ['trTemp', 'lighting', 'general', 'hvac', 'emergency', 'ups']);
});

test('includes both monthly closing meter groups from the workbook', () => {
  assert.deepEqual(MONTH_CLOSE_LABELS.substation, ['9', '10', '11', '12', '13', '14', '15']);
  assert.deepEqual(MONTH_CLOSE_LABELS.industrial, ['4', '5', '6', '7', '8', '10', '11']);
});

test('compares monthly closing readings with the previous month', () => {
  assert.equal(calculateMonthlyDifference('1200', '1150'), 50);
  assert.equal(calculateMonthlyDifference('100', '125'), -25);
  assert.equal(calculateMonthlyDifference('', '125'), null);
  const record = createEmptyRecord('2026-10-01');
  assert.equal(record.meters.current.length, 7);
  assert.equal(record.meters.monthlyClose.substation.current.length, 7);
  assert.equal(record.meters.monthlyClose.substation.previous.length, 7);
});

test('locks a completed inspection time until its edit checkbox is enabled', () => {
  const completed = { main: {}, vcb: {}, transformer: {}, secondary: {}, chiller: { chillerKw: '', chillerA: '' } };
  ['main', 'vcb', 'transformer', 'secondary'].forEach((group) => METRIC_GROUPS[group].fields.forEach(([key]) => { completed[group][key] = '1'; }));
  assert.equal(isInspectionTimeComplete(completed), true);
  completed.secondary.batteryV = '';
  assert.equal(isInspectionTimeComplete(completed), false);
  completed.secondary.batteryV = '1';
  assert.equal(isInspectionTimeLocked({ observations: { '08:00': completed } }, '08:00'), true);
  assert.equal(isInspectionTimeLocked({ observations: { '08:00': completed }, timeEdit: { '08:00': true } }, '08:00'), false);
});

test('uses the five workbook inspection time slots', () => {
  assert.deepEqual(TIME_SLOTS, ['08:00', '11:00', '14:00', '16:00', '23:59']);
});

test('calculates electrical meter usage with the workbook multiplier', () => {
  assert.deepEqual(calculateUsage(2095.68, 2094.15), { status: 'ok', value: 3672, warning: '' });
  assert.equal(calculateUsage('', 100).status, 'pending');
  assert.equal(calculateUsage(99, 100).status, 'warning');
});

test('summarizes seven meter rows and flags incomplete rows', () => {
  const summary = calculateMeterSummary({ current: [2, 3, 4, 5, 6, 7, ''], previous: [1, 2, 3, 4, 5, 6, ''] });
  assert.equal(summary.total, null);
  assert.equal(summary.usages[0].value, 2400);
  assert.equal(summary.usages[6].status, 'pending');
});

test('records safely round-trip through backup JSON', () => {
  const records = { '2026-10-01': createEmptyRecord('2026-10-01') };
  assert.deepEqual(parseRecords(serializeRecords(records)), records);
  assert.deepEqual(parseRecords('{bad'), {});
});
