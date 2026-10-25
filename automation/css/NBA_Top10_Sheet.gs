/**
 * NBA Today Top10: sheet-native completion and immediate refill.
 * Paste into Extensions > Apps Script of SFDC_Automation_Followup_2026.
 * This script acts ONLY on these named sheets in the bound spreadsheet.
 * The pool is a snapshot; refresh its source rows via the existing ETL separately.
 */
const NBA = {
  top: 'NBA Today Top10',
  pool: 'NBA Action Pool',
  log: 'NBA Decision Log',
  firstRow: 2,
  slots: 10,
  caps: {SFDC: 3, CSS: 3, LEAD: 2, QQ_MAIL: 2, SFDC_QUOTE: 2},
};

function onEdit(e) {
  if (!e || !e.range || !e.source) return;
  const sh = e.range.getSheet();
  if (sh.getName() !== NBA.top || e.range.getColumn() !== 15 ||
      e.range.getNumRows() !== 1 || e.range.getNumColumns() !== 1 ||
      e.range.getRow() < 2 || e.range.getRow() > 11 ||
      e.value !== 'TRUE') return;
  const lock = LockService.getDocumentLock();
  if (!lock || !lock.tryLock(10000)) {
    e.range.setValue(false);
    return;
  }
  try {
    const ss = e.source;
    const rowNum = e.range.getRow();
    const topRow = sh.getRange(rowNum, 1, 1, 17).getValues()[0];
    const source = String(topRow[3] || '').trim();
    const recordId = String(topRow[4] || '').trim();
    if (!source || !recordId) {
      e.range.setValue(false);
      return;
    }
    const pool = ss.getSheetByName(NBA.pool);
    if (!pool) throw new Error('NBA Action Pool not found');
    const poolValues = pool.getDataRange().getValues();
    let matched = -1;
    for (let i = 1; i < poolValues.length; i++) {
      if (String(poolValues[i][3]).trim() === source &&
          String(poolValues[i][4]).trim() === recordId) {
        matched = i + 1;
        break;
      }
    }
    if (matched < 0) throw new Error('Pool record not found: ' + source + '|' + recordId);
    if (String(pool.getRange(matched, 15).getValue()).trim().toUpperCase() !== 'DONE') {
      const log = ensureNbaLog_(ss);
      // Append audit BEFORE changing pool state; double check against existing IDs.
      const key = source + '|' + recordId;
      const last = log.getLastRow();
      const recorded = last > 1 ? log.getRange(2, 2, last - 1, 1).getValues().flat() : [];
      if (!recorded.includes(key)) {
        log.appendRow([new Date(), key, source, recordId,
          String(topRow[16] || ''), String(topRow[9] || ''), 'DONE']);
      }
      pool.getRange(matched, 15).setValue('DONE');
    }
    refreshNbaTop10_();
  } catch (err) {
    // Keep the action visible if completion was not recorded.
    e.range.setValue(false);
    e.range.setNote('NBA 처리 오류: ' + String(err.message || err));
    throw err;
  } finally {
    lock.releaseLock();
  }
}

function ensureNbaLog_(ss) {
  let log = ss.getSheetByName(NBA.log);
  if (!log) {
    log = ss.insertSheet(NBA.log);
    log.appendRow(['Completed At', 'Record Key', 'Source', 'Record ID',
      'Memo', 'Recommended Action', 'Decision']);
    log.setFrozenRows(1);
  }
  return log;
}

function refreshNbaTop10_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = ss.getSheetByName(NBA.top);
  const pool = ss.getSheetByName(NBA.pool);
  if (!sh || !pool) throw new Error('NBA sheets not found');
  const values = pool.getDataRange().getValues().slice(1);
  const decisions = new Set();
  const log = ss.getSheetByName(NBA.log);
  if (log && log.getLastRow() > 1) {
    log.getRange(2, 2, log.getLastRow()-1, 1).getValues().forEach(r=>decisions.add(String(r[0])));
  }
  const seen = new Set(), counts = {};
  const ranked = values.filter(r => r[3] && r[4])
    .sort((a,b)=>Number(b[2]||0)-Number(a[2]||0) ||
      String(a[4]).localeCompare(String(b[4])));
  const selected = [];
  for (const r of ranked) {
    const src = String(r[3]).trim(), id = String(r[4]).trim(), key = src+'|'+id;
    if (String(r[14]).trim().toUpperCase()==='DONE' || decisions.has(key) || seen.has(key)) continue;
    if ((counts[src]||0) >= (NBA.caps[src] || 2)) continue;
    seen.add(key); counts[src]=(counts[src]||0)+1;
    selected.push([...r.slice(0,14),false,'대기','']);
    if (selected.length === NBA.slots) break;
  }
  selected.forEach((r,i)=>r[0]=i+1);
  const blank = Array(17).fill('');
  const output=Array.from({length:NBA.slots},(_,i)=>selected[i]||[...blank]);
  sh.getRange(2,1,NBA.slots,17).setValues(output);
  sh.getRange(2,15,NBA.slots,1).insertCheckboxes();
  sh.getRange(2,15,NBA.slots,1).setValues(output.map(r=>[r[4] ? false : '']));
}

/** Run manually once after pasting, to populate/validate the 10 slots. */
function setupNbaQueue() {
  const ss=SpreadsheetApp.getActiveSpreadsheet();
  ensureNbaLog_(ss);
  refreshNbaTop10_();
}
