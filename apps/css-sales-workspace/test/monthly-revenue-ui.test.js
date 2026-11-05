'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const lifecycle=fs.readFileSync(path.join(root,'api','lifecycle.js'),'utf8');

test('Monthly Revenue and existing workspace modules remain navigable',()=>{
  for(const id of ['overview','projects','contractReview','revenue','monthlyRevenue','statements','mail','leads','sales','health']){
    assert.match(html,new RegExp('id="'+id+'" class="view'));
  }
  assert.match(html,/data-view="monthlyRevenue"/);
  assert.match(html,/id="monthlyChart"/);
  assert.match(html,/id="monthlyHeaders"/);
  assert.match(html,/id="monthlyRows"/);
  assert.match(html,/id="monthlyMode"/);
  assert.match(html,/id="monthlyFilter"/);
  assert.match(html,/drawMonthlyRevenue\(\)/);
});

test('source-aware labels and legacy source reports were not removed',()=>{
  for(const value of [
    '2025 공식 Revenue','2026 Invoice','Pending','Forecast',
    'Revenue L4 Monthly Mix','Revenue Monthly Institution',
    'BI Project Month Control','Billing Control Dashboard',
    '2025 Official Monthly'
  ]) assert.ok(html.includes(value),value);
  assert.match(html,/두 연도는 집계·VAT 기준이 달라/);
  assert.match(html,/원본 기반 검증 상태 확인 중/);
});

test('page script parses without external dependencies and preserves owner gate',()=>{
  const match=html.match(/<script>([\s\S]*?)<\/script>/);
  assert.ok(match,'inline UI script exists');
  assert.doesNotThrow(()=>new vm.Script(match[1],{filename:'index.html:inline'}));
  assert.match(match[1],/fetch\('\/api\/lifecycle'/);
  assert.match(match[1],/credentials:'same-origin'/);
  assert.match(match[1],/res\.status===401/);
});

test('lifecycle API reads both sources only after existing owner authorization',()=>{
  assert.match(lifecycle,/checkOwner\(req,token/);
  assert.match(lifecycle,/if\(!owner\.valid\)return res\.status\(401\)/);
  assert.match(lifecycle,/BI 2025 Official Monthly/);
  assert.match(lifecycle,/BI 2026 Forecast Overview/);
  assert.match(lifecycle,/projectMonthlyRevenue/);
  assert.match(lifecycle,/monthlyComparison/);
  assert.match(lifecycle,/Cache-Control','private, no-store'/);
});

test('no public unauthenticated monthly API or client-side service-account content',()=>{
  assert.doesNotMatch(html,/GOOGLE_SERVICE_ACCOUNT_JSON|PRIVATE KEY|BEGIN PRIVATE KEY/);
  assert.doesNotMatch(html,/public\/monthly-revenue\.json/);
  assert.match(lifecycle,/https:\/\/www\.googleapis\.com\/auth\/spreadsheets\.readonly/);
});
