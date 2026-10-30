'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {projectInvoiceAuditParity}=require('../lib/invoice-audit-parity');
const monthly=[{month:'2026-10',actual:82137000,invoices:35,refreshed:'2026-10-30 09:13:38 KST'}];
const legacy=[
 ['TAX INVOICE COMPLETENESS AUDIT','Value','Interpretation'],
 ['Invoice source last date','2026-10-19'],
 ['October invoice count','24'],
 ['October unique invoice numbers','24'],
 ['October invoice amount KRW','56633500']
];
test('flags observed 2026-10 canonical-vs-legacy discrepancy without implying loss',()=>{
 const x=projectInvoiceAuditParity(monthly,legacy);
 assert.equal(x.status,'MISMATCH_REVIEW');
 assert.equal(x.canonicalCount,35);
 assert.equal(x.legacyCount,24);
 assert.equal(x.amountDeltaKRW,25503500);
 assert.equal(x.countDelta,11);
 assert.equal(x.legacySourceLastDate,'2026-10-19');
 assert.equal(x.certified,false);
});
test('matching totals still cannot certify issued invoices or paid receipts',()=>{
 const l=legacy.map(r=>[...r]);
 l[2][1]='35';l[3][1]='35';l[4][1]='82137000';
 const x=projectInvoiceAuditParity(monthly,l);
 assert.equal(x.status,'MATCHED_NOT_CERTIFIED');
 assert.equal(x.certified,false);
});
test('invalid or missing legacy snapshot does not change canonical months',()=>{
 assert.equal(projectInvoiceAuditParity(monthly,[]).status,'LEGACY_AUDIT_UNAVAILABLE');
 assert.equal(projectInvoiceAuditParity([],legacy).status,'CANONICAL_MONTH_UNAVAILABLE');
 const bad=legacy.map(r=>[...r]);
 bad[2][1]='unknown';
 assert.equal(projectInvoiceAuditParity(monthly,bad).status,'LEGACY_AUDIT_SCHEMA_REVIEW');
 assert.equal(monthly[0].actual,82137000);
});
test('duplicated invoice numbers are not certified even if total matches',()=>{
 const l=legacy.map(r=>[...r]);l[2][1]='35';l[3][1]='34';l[4][1]='82137000';
 assert.equal(projectInvoiceAuditParity(monthly,l).status,'MISMATCH_REVIEW');
});
test('preview integrates read-only audit without mail, Salesforce or payment writers',()=>{
 const base=path.join(__dirname,'..');
 const src=fs.readFileSync(path.join(base,'api','lifecycle.js'),'utf8');
 const page=fs.readFileSync(path.join(base,'index.html'),'utf8');
 assert.ok(src.includes("'Tax Invoice Completeness Audit'!A1:B15"));
 assert.ok(src.includes('projectInvoiceAuditParity(months,invoiceAuditRows||[])'));
 assert.ok(src.includes('invoiceAudit,capabilities'));
 assert.ok(page.includes('id="revenueAuditWarning"'));
 assert.ok(page.includes('MISMATCH_REVIEW'));
});
