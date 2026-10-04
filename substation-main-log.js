const STORAGE_KEY = 'substation-main-log-v1';
export const TIME_SLOTS = ['08:00', '11:00', '14:00', '16:00', '23:59'];
export const METER_LABELS = ['4', '5', '6', '7', '8', '9', '10'];
export const MONTH_CLOSE_LABELS = {
  substation: ['9', '10', '11', '12', '13', '14', '15'],
  industrial: ['4', '5', '6', '7', '8', '10', '11'],
};
export function calculateMonthlyDifference(current, previous) {
  const now = toNumber(current); const before = toNumber(previous);
  return now === null || before === null ? null : Math.round((now - before) * 1e6) / 1e6;
}
export const METRIC_GROUPS = {
  main: { title: '22.9kV MAIN / 변압기', fields: [['kv', '전압 KV', 'main'], ['a1', 'R상 A', 'main'], ['a2', 'S상 A', 'main'], ['a3', 'T상 A', 'main'], ['pf', 'PF', 'main'], ['kw', 'KW', 'main'], ['hz', 'HZ', 'main'], ['tr1', 'TR1 온도', 'trTemp'], ['tr2', 'TR2 온도', 'trTemp']] },
  vcb: { title: '3.3kV MAIN VCB / 동력', fields: [['kv', '전압 KV', 'vcb'], ['kw', 'KW', 'vcb'], ['pf', 'PF', 'vcb'], ['a', '전류 A', 'vcb'], ['upsKw', 'UPS.B KW', 'ups'], ['upsA', 'UPS.B A', 'ups'], ['emergencyKw', '비상동력 KW', 'emergency'], ['emergencyA', '비상동력 A', 'emergency'], ['hvacKw', '냉난방 KW', 'hvac'], ['hvacA', '냉난방 A', 'hvac'], ['generalKw', '일반동력 KW', 'general'], ['generalA', '일반동력 A', 'general'], ['lightingKw', '조명 KW', 'lighting'], ['lightingA', '조명 A', 'lighting']] },
  transformer: { title: '변압기', fields: [['trTemp', 'TR온도(℃)'], ['lighting', '전등/전열'], ['general', '일반동력'], ['hvac', '냉/난방'], ['emergency', '비상동력'], ['ups', 'UPS']] },
  chiller: { title: '냉동기', fields: [['chillerKw', '냉동기1 KW'], ['chillerA', '냉동기1 A'], ['chiller2Kw', '냉동기2 KW'], ['chiller2A', '냉동기2 A'], ['capacitorKw', '콘덴서 KW'], ['capacitorA', '콘덴서 A']] },
  secondary: { title: '저압·정류기반·축전지', fields: [['lowLightingV', '조명 V', 'lowLighting'], ['lowLightingKw', '조명 KW', 'lowLighting'], ['lowLightingA', '조명 A', 'lowLighting'], ['lowGeneralV', '일반동력 V', 'lowGeneral'], ['lowGeneralKw', '일반동력 KW', 'lowGeneral'], ['lowGeneralA', '일반동력 A', 'lowGeneral'], ['lowEmergencyV', '비상동력 V', 'lowEmergency'], ['lowEmergencyKw', '비상동력 KW', 'lowEmergency'], ['lowEmergencyA', '비상동력 A', 'lowEmergency'], ['rectifierV', '정류기 V', 'rectifierBattery'], ['rectifierA', '정류기 A', 'rectifierBattery'], ['batteryV', '축전지 V', 'rectifierBattery'], ['batteryA', '축전지 A', 'rectifierBattery']] },
};
export const LOCKABLE_GROUPS = ['main', 'vcb', 'transformer', 'secondary'];
export function isInspectionTimeComplete(observation) {
  return LOCKABLE_GROUPS.every((groupKey) => METRIC_GROUPS[groupKey].fields.every(([key]) => String(observation?.[groupKey]?.[key] ?? '').trim() !== ''));
}
export function isInspectionTimeLocked(record, time) {
  return isInspectionTimeComplete(record?.observations?.[time]) && !record?.timeEdit?.[time];
}

export function toNumber(value) { if (value === '' || value === null || value === undefined) return null; const n = Number(value); return Number.isFinite(n) ? n : null; }
export function calculateUsage(current, previous, multiplier = 2400) {
  const now = toNumber(current); const before = toNumber(previous);
  if (now === null || before === null) return { status: 'pending', value: null, warning: '' };
  const value = Math.round((now - before) * multiplier * 1e6) / 1e6;
  return value < 0 ? { status: 'warning', value, warning: '전일보다 작은 검침량입니다.' } : { status: 'ok', value, warning: '' };
}
export function calculateMeterSummary(meter) {
  const usages = meter.current.map((value, i) => calculateUsage(value, meter.previous[i]));
  return { usages, total: usages.some((item) => item.status === 'pending') ? null : usages.reduce((sum, item) => sum + (item.value ?? 0), 0), warnings: usages.filter((item) => item.warning).map((item) => item.warning) };
}
export function createEmptyRecord(date) {
  const observations = Object.fromEntries(TIME_SLOTS.map((time) => [time, { main: {}, vcb: {}, transformer: {}, chiller: {}, secondary: {} }]));
  return { date, operator: '', observations, timeEdit: Object.fromEntries(TIME_SLOTS.map((time) => [time, false])), meters: { current: Array(7).fill(''), previous: Array(7).fill(''), monthlyClose: { substation: { current: Array(7).fill(''), previous: Array(7).fill('') }, industrial: { current: Array(7).fill(''), previous: Array(7).fill('') } } }, notes: '' };
}
export function serializeRecords(records) { return JSON.stringify({ version: 1, exportedAt: new Date().toISOString(), records }); }
export function parseRecords(json) { try { const parsed = JSON.parse(json); const records = parsed?.records && typeof parsed.records === 'object' ? parsed.records : parsed; return records && typeof records === 'object' && !Array.isArray(records) ? records : {}; } catch { return {}; } }
function fmt(value) { return value === null || value === undefined ? '입력 대기' : Number(value).toLocaleString('ko-KR', { maximumFractionDigits: 2 }); }
function esc(value) { return String(value ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch])); }

function initApp() {
  const $ = (id) => document.getElementById(id); const state = { month: '2026-10', date: '2026-10-01', records: {} };
  const current = () => {
    const record = state.records[state.date] || (state.records[state.date] = createEmptyRecord(state.date));
    TIME_SLOTS.forEach((time) => { record.observations[time] ||= {}; record.observations[time].main ||= {}; record.observations[time].vcb ||= {}; record.observations[time].transformer ||= {}; record.observations[time].chiller ||= {}; record.observations[time].secondary ||= {}; });
    record.timeEdit ||= {}; TIME_SLOTS.forEach((time) => { record.timeEdit[time] ||= false; });
    record.meters ||= {}; record.meters.current ||= Array(7).fill(''); record.meters.previous ||= Array(7).fill(''); while (record.meters.current.length < METER_LABELS.length) record.meters.current.push(''); while (record.meters.previous.length < METER_LABELS.length) record.meters.previous.push('');
    record.meters.monthlyClose ||= {};
    ['substation', 'industrial'].forEach((key) => { const old = record.meters.monthlyClose[key]; if (Array.isArray(old)) record.meters.monthlyClose[key] = { current: [...old, ...Array(Math.max(0, MONTH_CLOSE_LABELS[key].length - old.length)).fill('')].slice(0, MONTH_CLOSE_LABELS[key].length), previous: Array(MONTH_CLOSE_LABELS[key].length).fill('') }; record.meters.monthlyClose[key] ||= {}; record.meters.monthlyClose[key].current ||= Array(MONTH_CLOSE_LABELS[key].length).fill(''); record.meters.monthlyClose[key].previous ||= Array(MONTH_CLOSE_LABELS[key].length).fill(''); });
    return record;
  };
  const fieldInput = (path, value, disabled = false) => `<input class="compact nav-input" type="number" step="any" data-path="${path}" value="${esc(value)}"${disabled ? ' disabled' : ''}>`;
  function setupKeyboardNavigation() {
    document.addEventListener('keydown', (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement) || !target.classList.contains('nav-input') || target.disabled) return;
      const groupOrder = { main: 0, vcb: 1, transformer: 2, chiller: 3, secondary: 4 };
      const all = [...document.querySelectorAll('input.nav-input:not(:disabled)')];
      const ordered = [...all].sort((a, b) => {
        const pa = a.dataset.path.split('|'); const pb = b.dataset.path.split('|');
        if (pa[0] === 'obs' && pb[0] === 'obs') return (TIME_SLOTS.indexOf(pa[1]) - TIME_SLOTS.indexOf(pb[1])) || ((groupOrder[pa[2]] ?? 99) - (groupOrder[pb[2]] ?? 99));
        if (pa[0] === 'obs' && pb[0] !== 'obs') return -1;
        if (pa[0] !== 'obs' && pb[0] === 'obs') return 1;
        return all.indexOf(a) - all.indexOf(b);
      });
      const moveTo = (element) => { if (element) { event.preventDefault(); element.focus(); element.select?.(); } };
      if (event.key === 'Enter') { moveTo(ordered[ordered.indexOf(target) + 1]); return; }
      if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
      const row = target.closest('tr'); const table = target.closest('table');
      const rowInputs = row ? [...row.querySelectorAll('input.nav-input')] : [];
      const column = rowInputs.indexOf(target);
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { moveTo(rowInputs[column + (event.key === 'ArrowRight' ? 1 : -1)]); return; }
      const rows = table ? [...table.querySelectorAll('tbody tr')] : [];
      const rowIndex = rows.indexOf(row); const nextRow = rows[rowIndex + (event.key === 'ArrowDown' ? 1 : -1)];
      moveTo(nextRow?.querySelectorAll('input.nav-input')[column]);
    });
  }
  function renderObservationTable(groupKey) {
    const group = METRIC_GROUPS[groupKey];
    const groups = []; group.fields.forEach((field) => { const key = field[2] || groupKey; const last = groups[groups.length - 1]; if (last?.key === key) last.count += 1; else groups.push({ key, count: 1 }); });
    const groupNames = { main: '22.9 KV (MAIN)', trTemp: 'TR온도(℃)', vcb: '3.3 KV MAIN VCB(일반)', ups: 'UPS.B', emergency: '비상동력', hvac: '냉난방', general: '일반동력', lighting: '조명 (VCB반)', transformer: '변압기', chiller: '냉동기', secondary: '저압·정류기반·축전지', lowLighting: '조명', lowGeneral: '일반동력', lowEmergency: '비상동력', rectifierBattery: '정류기(축전지)' };
    return `<div class="table-scroll"><table><thead><tr class="group-row"><th>분류</th>${groups.map((item) => `<th class="band-${item.key}" colspan="${item.count}">${groupNames[item.key] || item.key}</th>`).join('')}</tr><tr><th>시각</th>${group.fields.map(([, label, fieldGroup]) => `<th class="band-${fieldGroup || groupKey}">${label}</th>`).join('')}</tr></thead><tbody>${TIME_SLOTS.map((time) => { const record = current(); const locked = groupKey !== 'chiller' && isInspectionTimeLocked(record, time); const timeCell = groupKey === 'main' ? `<label class="time-edit"><input type="checkbox" data-time-edit="${time}" ${record.timeEdit?.[time] ? 'checked' : ''}> 수정</label><span>${time}</span>` : time; return `<tr class="${locked ? 'time-locked' : ''}"><th>${timeCell}</th>${group.fields.map(([key, , fieldGroup]) => `<td class="band-${fieldGroup || groupKey}">${fieldInput(`obs|${time}|${groupKey}|${key}`, record.observations[time][groupKey][key], locked)}</td>`).join('')}</tr>`; }).join('')}</tbody></table></div>`;
  }
  function renderPrintSheet() {
    const r = current();
    const matrix = (groupKey) => { const group = METRIC_GROUPS[groupKey]; return `<section class="print-section"><h2>${group.title}</h2><table class="print-matrix"><thead><tr><th>항목</th>${TIME_SLOTS.map((time) => `<th>${time}</th>`).join('')}</tr></thead><tbody>${group.fields.map(([key, label, fieldGroup]) => `<tr><th class="band-${fieldGroup || groupKey}">${label}</th>${TIME_SLOTS.map((time) => `<td class="band-${fieldGroup || groupKey}">${esc(r.observations[time][groupKey]?.[key] || '')}</td>`).join('')}</tr>`).join('')}</tbody></table></section>`; };
    const meter = calculateMeterSummary(r.meters);
    const monthly = (key, title) => `<div><h2>${title}</h2><table class="print-matrix print-monthly"><thead><tr><th>계량기</th><th>이번 달</th><th>전월</th><th>증감</th></tr></thead><tbody>${MONTH_CLOSE_LABELS[key].map((label, i) => `<tr><th>${label}</th><td>${esc(r.meters.monthlyClose[key].current[i])}</td><td>${esc(r.meters.monthlyClose[key].previous[i])}</td><td>${fmt(calculateMonthlyDifference(r.meters.monthlyClose[key].current[i], r.meters.monthlyClose[key].previous[i])) === '입력 대기' ? '' : fmt(calculateMonthlyDifference(r.meters.monthlyClose[key].current[i], r.meters.monthlyClose[key].previous[i]))}</td></tr>`).join('')}</tbody></table></div>`;
    $('printSheet').innerHTML = `<div class="print-title">수변전 일지 · 본관</div><div class="print-meta"><div>기록 일자: ${esc(state.date)}</div><div>작업자: ${esc(r.operator)}</div><div>검침 계수: 2,400</div></div><div class="print-pair">${matrix('main')}${matrix('vcb')}</div><div class="print-pair">${matrix('transformer')}${matrix('chiller')}</div><div class="single-print">${matrix('secondary')}</div><section class="print-section"><h2>계량기 검침</h2><table class="print-matrix print-meter"><thead><tr><th>구분</th><th>금일</th><th>전일</th><th>사용량</th></tr></thead><tbody>${METER_LABELS.map((label, i) => `<tr><th>계량기 ${label}</th><td>${esc(r.meters.current[i])}</td><td>${esc(r.meters.previous[i])}</td><td>${meter.usages[i].value === null ? '' : fmt(meter.usages[i].value)}</td></tr>`).join('')}</tbody></table><div class="print-pair monthly-print">${monthly('substation', '* 월 마감 (수변전)')}${monthly('industrial', '* 월 마감 (산업용)')}</div></section><section class="print-notes"><strong>특이사항</strong><div>${esc(r.notes)}</div><div class="line"></div></section>`;
  }
  function render() {
    const r = current(); $('datePicker').value = state.date; $('operator').value = r.operator; $('notes').value = r.notes;
    Object.keys(METRIC_GROUPS).forEach((key) => { $(`group-${key}`).innerHTML = renderObservationTable(key); });
    $('meterRows').innerHTML = METER_LABELS.map((label, i) => `<tr><th>계량기 ${label}</th><td>${fieldInput(`meter|current|${i}`, r.meters.current[i])}</td><td>${fieldInput(`meter|previous|${i}`, r.meters.previous[i])}</td><td><output id="meter-u-${i}">입력 대기</output></td></tr>`).join('');
    const monthlyTable = (key) => `<table class="monthly-close-table"><thead><tr><th>계량기</th><th>이번 달 검침량</th><th>전월 검침량</th><th>증감</th></tr></thead><tbody>${MONTH_CLOSE_LABELS[key].map((label, i) => `<tr><th>${label}</th><td>${fieldInput(`monthly|${key}|current|${i}`, r.meters.monthlyClose[key].current[i])}</td><td>${fieldInput(`monthly|${key}|previous|${i}`, r.meters.monthlyClose[key].previous[i])}</td><td><output id="monthly-u-${key}-${i}">입력 대기</output></td></tr>`).join('')}</tbody></table>`;
    $('monthlyCloseSubstation').innerHTML = monthlyTable('substation'); $('monthlyCloseIndustrial').innerHTML = monthlyTable('industrial');
    ['substation', 'industrial'].forEach((key) => MONTH_CLOSE_LABELS[key].forEach((label, i) => { const value = calculateMonthlyDifference(r.meters.monthlyClose[key].current[i], r.meters.monthlyClose[key].previous[i]); const out = $(`monthly-u-${key}-${i}`); out.textContent = value === null ? '입력 대기' : fmt(value); out.className = value === null ? 'pending' : value < 0 ? 'warning' : 'ok'; }));
    bindInputs(); calculateAndRender();
  }
  function readForm() {
    const r = current(); r.operator = $('operator').value; r.notes = $('notes').value;
    document.querySelectorAll('[data-path]').forEach((el) => { const parts = el.dataset.path.split('|'); if (parts[0] === 'meter') r.meters[parts[1]][Number(parts[2])] = el.value; else if (parts[0] === 'monthly') r.meters.monthlyClose[parts[1]][parts[2]][Number(parts[3])] = el.value; else if (parts[0] === 'obs') r.observations[parts[1]][parts[2]][parts[3]] = el.value; });
  }
  function updateTimeLocks() {
    const record = current();
    document.querySelectorAll('input[data-path^="obs|"]').forEach((el) => { const parts = el.dataset.path.split('|'); const locked = parts[2] !== 'chiller' && isInspectionTimeLocked(record, parts[1]); el.disabled = locked; el.closest('tr')?.classList.toggle('time-locked', locked); });
  }
  function calculateAndRender() { const summary = calculateMeterSummary(current().meters); summary.usages.forEach((item, i) => { const out = $(`meter-u-${i}`); out.textContent = item.warning ? '확인 필요' : fmt(item.value); out.className = item.status; }); $('meterTotal').textContent = fmt(summary.total); $('warning').textContent = summary.warnings.join(' '); }
  function save(show = true) { readForm(); localStorage.setItem(STORAGE_KEY, serializeRecords(state.records)); $('saveStatus').textContent = show ? '저장됨' : '자동 저장됨'; }
  function bindInputs() { document.querySelectorAll('input,textarea').forEach((el) => { if (!el.dataset.bound) { el.addEventListener('input', () => { if (el.dataset.timeEdit) return; readForm(); calculateAndRender(); updateTimeLocks(); save(false); }); if (el.dataset.timeEdit) el.addEventListener('change', () => { current().timeEdit[el.dataset.timeEdit] = el.checked; updateTimeLocks(); save(false); }); el.dataset.bound = '1'; } }); }
  function load() { const saved = localStorage.getItem(STORAGE_KEY); if (saved) state.records = parseRecords(saved); render(); $('saveStatus').textContent = saved ? '저장 기록 불러옴' : '새 기록'; }
  async function saveWorkbookAndPrint() {
    readForm(); $('saveStatus').textContent = '원본 엑셀 저장 중…';
    try {
      const response = await fetch('http://127.0.0.1:8766/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ date: state.date, record: current() }) });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || '엑셀 저장에 실패했습니다.');
      $('saveStatus').textContent = `엑셀 저장 완료 · ${result.sheet}`;
      if (result.warnings?.length) alert(`엑셀 저장은 완료했습니다.\n\n원본 셀에 입력 위치가 없어 저장되지 않은 값:\n${result.warnings.join('\n')}`);
      renderPrintSheet(); window.print();
    } catch (error) {
      $('saveStatus').textContent = '엑셀 저장 실패';
      alert(`원본 엑셀을 저장하지 못해 인쇄를 중단했습니다.\n${error.message}\n\n엑셀 입력 도우미 실행 파일을 먼저 실행해 주세요: start-excel-workbook-bridge.bat`);
    }
  }
  $('datePicker').addEventListener('change', (e) => { readForm(); state.date = e.target.value; render(); }); $('saveBtn').addEventListener('click', () => save(true)); $('resetBtn').addEventListener('click', () => { state.records[state.date] = createEmptyRecord(state.date); render(); save(true); }); $('manualPrintBtn').addEventListener('click', () => { readForm(); renderPrintSheet(); window.print(); }); $('printBtn').addEventListener('click', saveWorkbookAndPrint);
  $('backupBtn').addEventListener('click', () => { readForm(); const blob = new Blob([serializeRecords(state.records)], { type: 'application/json;charset=utf-8' }); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `수변전-본관-일지-${state.month}.json`; a.click(); URL.revokeObjectURL(a.href); });
  $('restoreInput').addEventListener('change', async (e) => { const file = e.target.files[0]; if (!file) return; const imported = parseRecords(await file.text()); if (Object.keys(imported).length) { state.records = { ...state.records, ...imported }; save(true); render(); } else $('saveStatus').textContent = '복원 실패'; e.target.value = ''; });
  $('csvBtn').addEventListener('click', () => { readForm(); const rows = [['날짜', '작업자', '계량기 사용량 합계', '특이사항']]; for (let day = 1; day <= 31; day++) { const date = `${state.month}-${String(day).padStart(2, '0')}`; const r = state.records[date] || createEmptyRecord(date); rows.push([date, r.operator, calculateMeterSummary(r.meters).total ?? '', r.notes]); } const csv = '\ufeff' + rows.map((row) => row.map((v) => `"${String(v).replaceAll('"', '""')}"`).join(',')).join('\r\n'); const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' }); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `수변전-본관-일지-${state.month}.csv`; a.click(); URL.revokeObjectURL(a.href); });
  setupKeyboardNavigation(); load();
}
if (typeof document !== 'undefined') initApp();
