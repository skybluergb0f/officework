const STORAGE_KEY = 'gangnam-annex-log-v1';
const DAY_COUNT = 31;

export function toNumber(value) {
  if (value === '' || value === null || value === undefined) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function calculateUsage(current, previous, multiplier = 1) {
  const now = toNumber(current);
  const before = toNumber(previous);
  if (now === null || before === null) return { status: 'pending', value: null, warning: '' };
  const value = (now - before) * multiplier;
  if (value < 0) return { status: 'warning', value, warning: '전일 지침보다 작습니다. 입력값을 확인하세요.' };
  return { status: 'ok', value, warning: '' };
}

export function createEmptyRecord(date) {
  return {
    date,
    weather: { condition: '맑음', min: '', max: '' },
    electric: {
      main: { current: ['', '', '', '', ''], previous: ['', '', '', '', ''], multipliers: [2400, 2400, 2400, 2400, 2400] },
      annex: { current: ['', '', '', '', ''], previous: ['', '', '', '', ''], multipliers: [1200, 1200, 1200, 1200, 1200] },
    },
    hvac: [
      { name: '냉동기 1호기', hours: '', usage: '' },
      { name: '냉동기 2호기', hours: '', usage: '' },
      { name: '냉동기 3호기', hours: '', usage: '' },
      { name: '보일러 1호기', hours: '', usage: '' },
      { name: '보일러 2호기', hours: '', usage: '' },
      { name: '냉온수기', hours: '', usage: '' },
    ],
    water: {
      main: [{ name: '보일러', current: '', previous: '', multiplier: 1 }, { name: '9F 식당', current: '', previous: '', multiplier: 1 }, { name: '시수', current: '', previous: '', multiplier: 1 }, { name: '본관', current: '', previous: '', multiplier: 1 }],
      annex: [{ name: '보일러', current: '', previous: '', multiplier: 1 }, { name: '냉온수기', current: '', previous: '', multiplier: 1 }],
    },
    staffing: { day: '', names: '', main: '', annex: '', off: '', leave: '', absent: '', emergency: '' },
    notes: '',
    checklist: { main: Array(7).fill(false), annex: Array(7).fill(false), memo: '' },
  };
}

function summarizeGroup(group) {
  const usages = group.current.map((value, index) => calculateUsage(value, group.previous[index], group.multipliers[index]));
  const values = usages.map((item) => item.value ?? 0);
  return {
    usages,
    total: usages.some((item) => item.status === 'pending') ? null : values.reduce((sum, value) => sum + value, 0),
    warnings: usages.filter((item) => item.warning).map((item) => item.warning),
  };
}

export function calculateDailySummary(record) {
  const main = summarizeGroup(record.electric.main);
  const annex = summarizeGroup(record.electric.annex);
  return { main, annex, grandTotal: main.total === null || annex.total === null ? null : main.total + annex.total };
}

export function serializeRecords(records) {
  return JSON.stringify({ version: 1, exportedAt: new Date().toISOString(), records });
}

export function parseRecords(json) {
  try {
    const parsed = JSON.parse(json);
    const records = parsed && parsed.records && typeof parsed.records === 'object' ? parsed.records : parsed;
    return records && typeof records === 'object' && !Array.isArray(records) ? records : {};
  } catch { return {}; }
}

function fmt(value) { return value === null || value === undefined ? '입력 대기' : Number(value).toLocaleString('ko-KR', { maximumFractionDigits: 2 }); }
function esc(value) { return String(value ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch])); }

function initApp() {
  const $ = (id) => document.getElementById(id);
  const state = { month: '2026-10', date: '2026-10-01', records: {} };
  const mainMeters = ['수전 4', '수전 5', '수전 6', '수전 7', '수전 8'];
  const annexMeters = ['수전 4', '수전 5', '수전 6', '수전 7', '수전 8'];
  const checklistMain = ['전층 공조실(좌/우) 시설순찰 (주/야간)', '전층 사무실 실내온도 및 조명 상태 확인', '6층·B1층 하론실 상태 점검', 'B1층 UPS실 시설순찰', 'B2층 수변전실·기계실 시설순찰', '발전기 연도 공사 확인', '정화조·수처리제 투입 확인'];
  const checklistAnnex = ['전층 EPS실 시설순찰 (주/야간)', 'RF층 공조기·고가수조 확인', '5~8층 조명·실내온도 확인', '1~4층 주차장 시설순찰', 'B1층 피아노보관실 항온항습기 확인', '정화조 점검', '수처리제 투입 확인'];

  function currentRecord() { return state.records[state.date] || (state.records[state.date] = createEmptyRecord(state.date)); }
  function input(label, id, value, type = 'number', step = 'any') { return `<label>${label}<input id="${id}" type="${type}" value="${esc(value)}" ${type === 'number' ? `step="${step}"` : ''}></label>`; }
  function meterTable(group, names) {
    return `<div class="meter-grid">${names.map((name, i) => `<div class="meter-row"><strong>${name}</strong>${input('금일', `${group}-c-${i}`, currentRecord().electric[group].current[i])}${input('전일', `${group}-p-${i}`, currentRecord().electric[group].previous[i])}<output id="${group}-u-${i}">입력 대기</output></div>`).join('')}</div>`;
  }
  function render() {
    const r = currentRecord();
    $('datePicker').value = state.date;
    $('weatherCondition').value = r.weather.condition;
    $('weatherMin').value = r.weather.min; $('weatherMax').value = r.weather.max;
    $('notes').value = r.notes;
    ['day', 'names', 'main', 'annex', 'off', 'leave', 'absent', 'emergency'].forEach((key) => { $(`staff-${key}`).value = r.staffing[key]; });
    $('electric-main').innerHTML = meterTable('main', mainMeters);
    $('electric-annex').innerHTML = meterTable('annex', annexMeters);
    $('hvacRows').innerHTML = r.hvac.map((item, i) => `<div class="hvac-row"><strong>${item.name}</strong>${input('운전시간', `hvac-h-${i}`, item.hours, 'text')}${input('사용량', `hvac-u-${i}`, item.usage)}</div>`).join('');
    ['main', 'annex'].forEach((group) => { $(`water-${group}`).innerHTML = r.water[group].map((item, i) => `<div class="water-row"><strong>${item.name}</strong>${input('금일', `water-c-${group}-${i}`, item.current)}${input('전일', `water-p-${group}-${i}`, item.previous)}<output id="water-u-${group}-${i}">입력 대기</output></div>`).join(''); });
    $('check-main').innerHTML = checklistMain.map((item, i) => `<label class="check"><input type="checkbox" data-check="main-${i}" ${r.checklist.main[i] ? 'checked' : ''}>${item}</label>`).join('');
    $('check-annex').innerHTML = checklistAnnex.map((item, i) => `<label class="check"><input type="checkbox" data-check="annex-${i}" ${r.checklist.annex[i] ? 'checked' : ''}>${item}</label>`).join('');
    $('checkMemo').value = r.checklist.memo;
    bindInputs(); calculateAndRender();
  }
  function readForm() {
    const r = currentRecord();
    r.weather = { condition: $('weatherCondition').value, min: $('weatherMin').value, max: $('weatherMax').value };
    r.notes = $('notes').value;
    ['day', 'names', 'main', 'annex', 'off', 'leave', 'absent', 'emergency'].forEach((key) => { r.staffing[key] = $(`staff-${key}`).value; });
    ['main', 'annex'].forEach((group) => { for (let i = 0; i < 5; i++) { r.electric[group].current[i] = $(`${group}-c-${i}`).value; r.electric[group].previous[i] = $(`${group}-p-${i}`).value; } });
    r.hvac.forEach((item, i) => { item.hours = $(`hvac-h-${i}`).value; item.usage = $(`hvac-u-${i}`).value; });
    ['main', 'annex'].forEach((group) => r.water[group].forEach((item, i) => { item.current = $(`water-c-${group}-${i}`).value; item.previous = $(`water-p-${group}-${i}`).value; }));
    document.querySelectorAll('[data-check]').forEach((el) => { const [group, i] = el.dataset.check.split('-'); r.checklist[group][Number(i)] = el.checked; });
    r.checklist.memo = $('checkMemo').value;
  }
  function calculateAndRender() {
    const r = currentRecord(); const summary = calculateDailySummary(r);
    ['main', 'annex'].forEach((group) => summary[group].usages.forEach((result, i) => { $(`${group}-u-${i}`).textContent = result.warning ? '확인 필요' : fmt(result.value); $(`${group}-u-${i}`).className = result.status; }));
    $('mainTotal').textContent = fmt(summary.main.total); $('annexTotal').textContent = fmt(summary.annex.total); $('grandTotal').textContent = fmt(summary.grandTotal);
    const waterTotals = { main: 0, annex: 0 }; let waterPending = false;
    ['main', 'annex'].forEach((group) => r.water[group].forEach((item, i) => { const result = calculateUsage(item.current, item.previous, item.multiplier); $(`water-u-${group}-${i}`).textContent = result.warning ? '확인 필요' : fmt(result.value); $(`water-u-${group}-${i}`).className = result.status; if (result.value !== null) waterTotals[group] += result.value; else waterPending = true; }));
    $('waterTotal').textContent = waterPending ? '입력 대기' : `${fmt(waterTotals.main + waterTotals.annex)} ㎥`;
    $('warning').textContent = [...summary.main.warnings, ...summary.annex.warnings].join(' ');
  }
  function bindInputs() { document.querySelectorAll('input, textarea, select').forEach((el) => { if (!el.dataset.bound) { el.addEventListener('input', () => { readForm(); calculateAndRender(); save(false); }); el.dataset.bound = '1'; } }); }
  function save(show = true) { readForm(); localStorage.setItem(STORAGE_KEY, serializeRecords(state.records)); $('saveStatus').textContent = show ? '저장됨' : '자동 저장됨'; }
  function load() { const saved = localStorage.getItem(STORAGE_KEY); if (saved) state.records = parseRecords(saved); render(); $('saveStatus').textContent = saved ? '저장 기록 불러옴' : '새 기록'; }
  $('datePicker').addEventListener('change', (e) => { readForm(); state.date = e.target.value; render(); });
  $('saveBtn').addEventListener('click', () => save(true));
  $('resetBtn').addEventListener('click', () => { state.records[state.date] = createEmptyRecord(state.date); render(); save(true); });
  $('backupBtn').addEventListener('click', () => { readForm(); const blob = new Blob([serializeRecords(state.records)], { type: 'application/json;charset=utf-8' }); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `강남별관-종합일지-${state.month}.json`; a.click(); URL.revokeObjectURL(a.href); });
  $('restoreInput').addEventListener('change', async (e) => { const file = e.target.files[0]; if (!file) return; const imported = parseRecords(await file.text()); if (Object.keys(imported).length) { state.records = { ...state.records, ...imported }; save(true); render(); } else $('saveStatus').textContent = '복원 실패'; e.target.value = ''; });
  $('csvBtn').addEventListener('click', () => { readForm(); const rows = [['날짜', '날씨', '최저', '최고', '본관 사용량', '신관 사용량', '합계', '특이사항']]; for (let day = 1; day <= DAY_COUNT; day++) { const date = `${state.month}-${String(day).padStart(2, '0')}`; const r = state.records[date] || createEmptyRecord(date); const s = calculateDailySummary(r); rows.push([date, r.weather.condition, r.weather.min, r.weather.max, s.main.total ?? '', s.annex.total ?? '', s.grandTotal ?? '', r.notes]); } const csv = '\ufeff' + rows.map((row) => row.map((v) => `"${String(v).replaceAll('"', '""')}"`).join(',')).join('\r\n'); const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' }); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `강남별관-종합일지-${state.month}.csv`; a.click(); URL.revokeObjectURL(a.href); });
  load();
}

if (typeof document !== 'undefined') initApp();
