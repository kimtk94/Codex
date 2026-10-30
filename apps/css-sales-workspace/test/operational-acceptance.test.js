'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {projectOperationalAcceptance,HEADER}=require('../lib/operational-acceptance');

const NOW=Date.parse('2026-10-30T22:45:00+09:00');
const CHECKED='2026-10-30 22:32:32 KST';
const HEAD=HEADER.slice();
const CHECKS=[
 ['QQ','Inbox/Sent source','PASS','DATA'],
 ['Revenue','Gross/net invoice parity','PASS','DATA'],
 ['Revenue','Canonical vs stale legacy','PASS','DATA'],
 ['SFDC','Three subscription Reports','PASS','DATA'],
 ['Mail','Body cache completeness','WARN','DATA'],
 ['Mail','Body workflow execution','PASS','DATA'],
 ['Feishu','Online projects','PASS','DATA'],
 ['Payment','Paid invoice evidence','BLOCK','FINANCE'],
 ['Release','Owner-authenticated Preview E2E','BLOCK','RELEASE'],
 ['Release','Production READY SHA parity','BLOCK','RELEASE'],
 ['Decision','Production acceptance','BLOCK','RELEASE']
];
function fixture(){
 return [HEAD,...CHECKS.map(([area,check,state,gate])=>
   [area,check,state,gate,'2026-10-30 22:32:32 KST','no PII; test fixture','Manual review only',CHECKED])];
}
test('central real-like source renders PASS WARN BLOCK and never grants promotion',()=>{
 const result=projectOperationalAcceptance(fixture(),NOW);
 assert.equal(result.available,true);
 assert.equal(result.status,'BLOCK');
 assert.equal(result.releaseApproved,false);
 assert.deepEqual(result.counts,{pass:6,warn:1,block:4});
 assert.equal(result.browserE2E,'BLOCK');
 assert.equal(result.productionParity,'BLOCK');
 assert.equal(result.rows.length,11);
 assert.equal(result.checked,CHECKED);
 assert.equal(result.reason,'SOURCE_BLOCKED');
});
test('missing header, release row and duplicate checks fail closed',()=>{
 const badHeader=fixture();badHeader[0][0]='Untrusted';
 assert.equal(projectOperationalAcceptance(badHeader,NOW).available,false);
 const missing=fixture().slice(0,-1);
 assert.equal(projectOperationalAcceptance(missing,NOW).status,'BLOCK');
 const duplicate=fixture();duplicate[3][1]=duplicate[2][1];
 assert.equal(projectOperationalAcceptance(duplicate,NOW).reason,'ACCEPTANCE_SOURCE_VALUES_INVALID');
});
test('forged PASS cannot upgrade a BLOCKED release',()=>{
 const rows=fixture();rows[11][2]='PASS';
 const out=projectOperationalAcceptance(rows,NOW);
 assert.equal(out.status,'BLOCK');
 assert.equal(out.releaseApproved,false);
 assert.equal(out.counts.block,3);
});
test('even all PASS stays pending human approval',()=>{
 const rows=fixture();
 for(const r of rows.slice(1))r[2]='PASS';
 const out=projectOperationalAcceptance(rows,NOW);
 assert.equal(out.available,true);
 assert.equal(out.status,'READY_FOR_MANUAL_REVIEW');
 assert.equal(out.releaseApproved,false);
 assert.equal(out.reason,'MANUAL_RELEASE_APPROVAL_STILL_REQUIRED');
});
test('stale, future or inconsistent snapshot is not accepted',()=>{
 const old=fixture();
 for(const r of old.slice(1))r[7]='2026-10-29 01:20:00 KST';
 const s=projectOperationalAcceptance(old,NOW);
 assert.equal(s.status,'BLOCK');
 assert.equal(s.reason,'ACCEPTANCE_SNAPSHOT_STALE');
 const future=fixture();
 for(const r of future.slice(1))r[7]='2026-11-01 22:32:32 KST';
 assert.equal(projectOperationalAcceptance(future,NOW).status,'BLOCK');
 const conflict=fixture();conflict[1][7]='2026-10-30 22:30:00 KST';
 assert.equal(projectOperationalAcceptance(conflict,NOW).reason,'ACCEPTANCE_SNAPSHOT_INCONSISTENT');
});
test('invalid enum and manipulated RELEASE gate never become accepted',()=>{
 const enumVal=fixture();enumVal[2][2]='GREEN';
 assert.equal(projectOperationalAcceptance(enumVal,NOW).available,false);
 const missingRelease=fixture();missingRelease[9][3]='INFO';
 assert.equal(projectOperationalAcceptance(missingRelease,NOW).reason,'ACCEPTANCE_RELEASE_GATE_INVALID');
});
test('lifecycle uses independent read-only status fetch with failure isolation',()=>{
 const api=fs.readFileSync(path.join(__dirname,'..','api','lifecycle.js'),'utf8');
 assert.ok(api.includes("'CSS Operational Acceptance'!A1:H20"));
 assert.ok(api.includes('const acceptancePromise=fetch('));
 assert.ok(api.includes('.catch(()=>[])'));
 assert.ok(api.includes('automation.acceptance=projectOperationalAcceptance(await acceptancePromise)'));
 assert.ok(api.includes('spreadsheets.readonly'));
 assert.ok(!api.includes('spreadsheets.values.update('));
});
test('control tower renders gate with textContent and never pretends automatic production approval',()=>{
 const page=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
 assert.ok(page.includes('id="releaseGateStatus"'));
 assert.ok(page.includes('id="releaseGateRows"'));
 assert.ok(page.includes('gate.status'));
 assert.ok(page.includes('자동 Production 승격 불가'));
 const script=page.match(/<script>([\s\S]*?)<\/script>/);
 assert.ok(script);
 assert.doesNotThrow(()=>new vm.Script(script[1]));
 assert.equal(page.includes("fetch('/api/promote'"),false);
});
