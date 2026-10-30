'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'..');
const api=fs.readFileSync(path.join(root,'api/lifecycle.js'),'utf8');
const page=fs.readFileSync(path.join(root,'index.html'),'utf8');

test('VAT-excluded Revenue comes from optional verified private source only',()=>{
  assert.ok(api.includes("'BI Revenue Net VAT Monthly'!A1:I24"));
  assert.ok(api.includes('gross===item.actual&&count===item.invoices'));
  assert.ok(api.includes("month.netRevenue=null;month.netRevenueKUSD=null;"));
  assert.ok(api.includes("revenueNetStatus='VERIFIED'"));
  assert.ok(api.includes("revenueNetStatus!=='VERIFIED'"));
  assert.ok(!api.includes('item.netRevenue=item.actual'));
});
test('gross billing cannot masquerade as net recognized sales',()=>{
  assert.ok(page.includes('Revenue (VAT 제외)'));
  assert.ok(page.includes('Invoice 발행 (VAT 포함)'));
  assert.ok(page.includes("'검증 대기'"));
  assert.ok(page.includes('netText(r.netRevenue)'));
  assert.ok(page.includes('Pending (세금 기준 미확인)'));
});
