'use strict';

// Source-safe, read-only projection. Never mix 2025 official net with 2026
// invoice gross into a single revenue total or calculate a false YoY rate.
const EXPECTED_2025 = [
  'Month', 'Korea Revenue USD', 'Korea Reporting KRW @1500',
  'Korea Rows', 'Kim Taehoon Revenue USD', 'Kim Reporting KRW @1500'
];
const EXPECTED_2026 = [
  'Month', '2025 Official Kim KRW @1500',
  '2025 Official Kim K USD', '2026 Actual Invoice KRW',
  '2026 Actual Invoice K USD', 'Forecast Included KRW',
  'Forecast Included K USD'
];

function amount(value) {
  if (value === null || value === undefined || String(value).trim() === '') return null;
  const v = Number(String(value).replace(/[₩,$\s]/g, ''));
  return Number.isFinite(v) && v >= 0 ? v : null;
}

function validHeader(rows, prefix) {
  return Array.isArray(rows) && Array.isArray(rows[0]) &&
    prefix.every((field, i) => rows[0][i] === field);
}

function monthNumber(value) {
  const match = /^(0?[1-9]|1[0-2])월$/.exec(String(value || '').trim());
  return match ? Number(match[1]) : null;
}

function monthKey(year, n) {
  return String(year) + '-' + String(n).padStart(2, '0');
}

function projectMonthlyRevenue({official2025, forecast2026, lifecycleMonths, asOf} = {}) {
  const y25ok = validHeader(official2025, EXPECTED_2025);
  const y26ok = validHeader(forecast2026, EXPECTED_2026);
  const by2025 = new Map();
  if (y25ok) {
    for (const r of official2025.slice(1)) {
      const match = /^2025-(0[1-9]|1[0-2])$/.exec(String(r[0] || ''));
      if (!match) continue;
      const n = Number(match[1]);
      const usd = amount(r[4]), krw = amount(r[5]);
      if (usd === null || krw === null) continue;
      by2025.set(n, {
        month: monthKey(2025, n), year: 2025, monthNumber: n,
        officialNetKRW: krw, officialNetKUSD: usd / 1000,
        issuedGrossKRW: null, issuedGrossKUSD: null,
        verifiedNetKRW: null, verifiedNetKUSD: null,
        pendingKRW: null, pendingKUSD: null, forecastKRW: null, forecastKUSD: null,
        source: '2025_OFFICIAL_USD_NET', coverage: 'OFFICIAL_REVENUE',
        count: amount(r[6]), currentMonth: false
      });
    }
  }

  const old2026 = new Map();
  if (y26ok) {
    for (const r of forecast2026.slice(1)) {
      const n = monthNumber(r[0]);
      if (!n || old2026.has(n)) continue;
      old2026.set(n, {
        issuedGrossKRW: amount(r[3]), issuedGrossKUSD: amount(r[4]),
        forecastKRW: amount(r[5]), forecastKUSD: amount(r[6]),
        coverage: String(r[9] || 'PARTIAL_SOURCE_COVERAGE')
      });
    }
  }
  const recent2026 = new Map();
  for (const r of Array.isArray(lifecycleMonths) ? lifecycleMonths : []) {
    const match = /^2026-(0[1-9]|1[0-2])$/.exec(String(r.month || ''));
    if (match) recent2026.set(Number(match[1]), r);
  }

  // Current month label is explanatory only; it does not impute missing actuals.
  const now = asOf ? new Date(asOf) : new Date();
  const kst = Number.isFinite(now.getTime()) ?
    new Date(now.getTime() + 9 * 3600 * 1000).toISOString().slice(0, 7) : '';

  const y2026 = [];
  for (let n = 1; n <= 12; n++) {
    const base = old2026.get(n) || {};
    const recent = recent2026.get(n);
    const month = monthKey(2026, n);
    y2026.push({
      month, year: 2026, monthNumber: n,
      officialNetKRW: null, officialNetKUSD: null,
      // Recent verified lifecycle takes precedence over stale annual forecast
      // snapshots, never add the two values.
      issuedGrossKRW: recent ? recent.actual : (base.issuedGrossKRW ?? null),
      issuedGrossKUSD: recent ? recent.invoiceKUSD : (base.issuedGrossKUSD ?? null),
      verifiedNetKRW: recent && recent.netRevenue !== undefined ? recent.netRevenue : null,
      verifiedNetKUSD: recent && recent.netRevenueKUSD !== undefined ? recent.netRevenueKUSD : null,
      pendingKRW: recent ? recent.pending : null,
      pendingKUSD: recent ? recent.pendingKUSD : null,
      forecastKRW: recent ? recent.forecast : (base.forecastKRW ?? null),
      forecastKUSD: recent ? recent.forecastKUSD : (base.forecastKUSD ?? null),
      source: recent ? 'LIFECYCLE_CURRENT' : (old2026.has(n) ? '2026_FORECAST_OVERVIEW' : 'MISSING'),
      coverage: recent ? String(recent.quality || 'SOURCE_REVIEW') : (base.coverage || 'NOT_AVAILABLE'),
      count: recent ? recent.invoices : null,
      currentMonth: month === kst
    });
  }

  const issues = [];
  if (!y25ok) issues.push('OFFICIAL_2025_SOURCE_HEADER_NOT_VERIFIED');
  if (!y26ok) issues.push('FORECAST_2026_SOURCE_HEADER_NOT_VERIFIED');
  if (by2025.size !== 12) issues.push('OFFICIAL_2025_MONTHS_INCOMPLETE');
  const rows = [
    ...[...by2025.values()].sort((a, b) => a.month.localeCompare(b.month)),
    ...y2026
  ];
  return {
    available: y25ok || y26ok || recent2026.size > 0,
    comparability: 'DIFFERENT_BASES_NO_DIRECT_YOY',
    exchangeRate2025: 1500,
    rows,
    issues,
    sources: {
      official2025: y25ok ? 'BI 2025 Official Monthly' : 'NOT_VERIFIED',
      annual2026: y26ok ? 'BI 2026 Forecast Overview' : 'NOT_VERIFIED',
      recent: 'BI Revenue Lifecycle Monthly + BI Revenue Net VAT Monthly'
    }
  };
}

module.exports = {projectMonthlyRevenue, amount, monthNumber, validHeader};
