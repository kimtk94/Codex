'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {projectMonthlyRevenue, amount, monthNumber} = require('../lib/monthly-revenue');

const y25header = [
  'Month', 'Korea Revenue USD', 'Korea Reporting KRW @1500',
  'Korea Rows', 'Kim Taehoon Revenue USD', 'Kim Reporting KRW @1500',
  'Kim Rows', 'Kim Share of Korea', 'Source', 'Metric Definition'
];
const y26header = [
  'Month', '2025 Official Kim KRW @1500', '2025 Official Kim K USD',
  '2026 Actual Invoice KRW', '2026 Actual Invoice K USD',
  'Forecast Included KRW', 'Forecast Included K USD',
  '2026 Actual + Forecast KRW', '2026 Actual + Forecast K USD', '2026 Month Status'
];
function sources() {
  return {
    official2025: [y25header, ['2025-10','10000','15000000', '10','2000', '3000000','2']],
    forecast2026: [y26header, ['10월','3000000','2','8000000','5.333','1500000','1.0',
      '9500000','6.333','PARTIAL_SOURCE_COVERAGE'], ['11월','4000000','2.667',null,null,'2500000','1.667']],
    lifecycleMonths: [{month:'2026-10',actual:11000000,invoiceKUSD:7.333,
      pending:4000000,pendingKUSD:2.667,forecast:3000000,forecastKUSD:2,
      netRevenue:10000000,netRevenueKUSD:6.667,invoices:5,quality:'INVOICES_VERIFIED_FORECAST_ESTIMATED'}],
    asOf:'2026-10-15T03:00:00Z'
  };
}
test('2025 official net stays separate from 2026 VAT-inclusive invoice gross', () => {
  const result=projectMonthlyRevenue(sources());
  const a=result.rows.find(x=>x.month==='2025-10');
  const b=result.rows.find(x=>x.month==='2026-10');
  assert.equal(a.officialNetKRW,3000000);
  assert.equal(a.officialNetKUSD,2);
  assert.equal(a.issuedGrossKRW,null);
  assert.equal(b.officialNetKRW,null);
  assert.equal(b.issuedGrossKRW,11000000);
  assert.equal(b.verifiedNetKRW,10000000);
  assert.equal(b.pendingKRW,4000000);
  assert.equal(b.forecastKRW,3000000);
  assert.equal(result.comparability,'DIFFERENT_BASES_NO_DIRECT_YOY');
});
test('latest lifecycle overrides overlapping stale annual 2026 rows, no duplicate sum', () => {
  const result=projectMonthlyRevenue(sources());
  const b=result.rows.find(x=>x.month==='2026-10');
  assert.notEqual(b.issuedGrossKRW,19000000);
  assert.equal(b.source,'LIFECYCLE_CURRENT');
  assert.equal(b.currentMonth,true);
});
test('historical snapshot values remain available but are never reclassified as verified net', () => {
  const rows=projectMonthlyRevenue(sources()).rows;
  const nov=rows.find(x=>x.month==='2026-11');
  assert.equal(nov.forecastKRW,2500000);
  assert.equal(nov.issuedGrossKRW,null);
  assert.equal(nov.verifiedNetKRW,null);
  assert.equal(nov.source,'2026_FORECAST_OVERVIEW');
});
test('missing and malformed 2025 source fails closed without inventing official revenue', () => {
  const x=sources();x.official2025=[['Month','Wrong column'],['2025-10','100']];
  const result=projectMonthlyRevenue(x);
  assert.equal(result.rows.filter(r=>r.year===2025).length,0);
  assert.ok(result.issues.includes('OFFICIAL_2025_SOURCE_HEADER_NOT_VERIFIED'));
});
test('malformed 2026 data does not prevent independently verified lifecycle month', () => {
  const x=sources(); x.forecast2026=[['Month','Corrupted'],['10월','999']];
  const result=projectMonthlyRevenue(x);
  assert.equal(result.rows.find(r=>r.month==='2026-10').issuedGrossKRW,11000000);
  assert.equal(result.rows.find(r=>r.month==='2026-11').source,'MISSING');
});
test('no source does not show unverified values as available', () => {
  const result=projectMonthlyRevenue({});
  assert.equal(result.available,false);
  assert.equal(result.rows.length,12);
  assert.equal(result.rows[0].issuedGrossKRW,null);
  assert.equal(result.rows[0].forecastKRW,null);
  assert.equal(result.rows[0].currentMonth,false);
});
test('amount parsing and month labels reject invalid or negative revenue', () => {
  assert.equal(amount('₩1,234,567'),1234567);
  assert.equal(amount(''),null);
  assert.equal(amount('-10'),null);
  assert.equal(amount('garbage'),null);
  assert.equal(monthNumber('1월'),1);
  assert.equal(monthNumber('12월'),12);
  assert.equal(monthNumber('TOTAL'),null);
});
