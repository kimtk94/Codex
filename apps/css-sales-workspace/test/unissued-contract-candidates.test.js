'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {projectUnissuedContracts,HEAD}=require('../lib/unissued-contract-candidates');
const NOW=Date.parse('2026-10-31T22:30:00+09:00');
const CANDIDATE='CANDIDATE_ONLY_REQUIRES_ORIGINAL_CONTRACT_REVIEW';
const HOLD='QUARANTINE_NO_CONTRACT_ATTRIBUTION';
const row=(amea,state,online='',finance='')=>[
  amea,'Korea-ChangWon Univ.-'+amea,'9640005','X209SC26065705-Z01',
  online?'H209SC26107211':'',online,online?'X209SC26107211-Z01-F001':'',
  finance,state,'0','2','2','10604000','10604000','2026-10-31','2026-10-26',
  state==='NO_AMEA_SOURCE_CANDIDATE'?HOLD:CANDIDATE,
  'Original contract needed','2026-10-31 21:47:32 KST','https://github.com/kimtk94/Codex/actions/runs/41202248094'
];
test('owner review exposes AMEA candidate as unapproved and warns on stale finance source',()=>{
 const r=projectUnissuedContracts([HEAD,
  row('AMEA2026090309','FINANCE_AMEA_CANDIDATE','','X209SC26107211'),
  row('AMEA2026091134','NO_AMEA_SOURCE_CANDIDATE')
 ],NOW);
 assert.equal(r.available,true);
 assert.equal(r.status,'REVIEW_SOURCE_STALE');
 assert.equal(r.candidateCount,1);
 assert.equal(r.missingCount,1);
 assert.equal(r.items[0].candidateX,'X209SC26107211');
 assert.equal(r.items[0].unsafeWatchX,'X209SC26065705-Z01');
 assert.equal(r.items[0].onlineH,'');
 assert.equal(r.items[0].attributionVerified,false);
 assert.equal(r.items[0].paymentVerified,false);
 assert.equal(r.items[0].revenueActualApproved,false);
});
test('confirmed source parity is still only a contract candidate',()=>{
 const r=projectUnissuedContracts([HEAD,row('AMEA2026090309',
  'ONLINE_FINANCE_SAME_X_CANDIDATE','X209SC26107211-Z01','X209SC26107211')],NOW);
 assert.equal(r.available,true);
 assert.equal(r.verified,false);
 assert.equal(r.items[0].onlineH,'H209SC26107211');
 assert.equal(r.items[0].candidateX,'X209SC26107211-Z01');
 assert.equal(r.items[0].issuanceVerified,false);
});
test('invalid schema, duplicate AMEA, unauthorized approval and cross-source mismatch fail closed',()=>{
 const base=row('AMEA2026090309','FINANCE_AMEA_CANDIDATE','','X209SC26107211');
 const a=HEAD.slice();a[3]='Approved Watch X';
 assert.equal(projectUnissuedContracts([a,base],NOW).available,false);
 assert.equal(projectUnissuedContracts([HEAD,base,base],NOW).available,false);
 const forged=base.slice();forged[16]='CONTRACT_APPROVED';
 assert.equal(projectUnissuedContracts([HEAD,forged],NOW).available,false);
 const conflict=row('AMEA2026090309','ONLINE_FINANCE_SAME_X_CANDIDATE','X209SC26107211-Z01','X209SC26065705');
 assert.equal(projectUnissuedContracts([HEAD,conflict],NOW).available,false);
});
test('invalid dates or future source dates fail closed',()=>{
 const base=row('AMEA2026090309','FINANCE_AMEA_CANDIDATE','','X209SC26107211');
 const future=base.slice();future[15]='2026-11-01';
 assert.equal(projectUnissuedContracts([HEAD,future],NOW).available,false);
 const bad=base.slice();bad[14]='2026-02-31';
 assert.equal(projectUnissuedContracts([HEAD,bad],NOW).available,false);
});
test('lifecycle retains owner authentication and isolates optional crosswalk reads',()=>{
 const api=fs.readFileSync(path.join(__dirname,'..','api','lifecycle.js'),'utf8');
 assert.match(api,/checkOwner\(req,token/);
 assert.match(api,/spreadsheets\.readonly/);
 assert.match(api,/const contractsPromise=\(async\(\)=>/);
 assert.match(api,/projectUnissuedContracts\(await contractsPromise\)/);
 assert.ok(!api.includes('Unissued Invoice Watch\'!M'));
});
test('contract review web panel is textContent-only and leaves billing unchanged',()=>{
 const page=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
 for(const id of ['contractReview','contractReviewRows','contractReviewSummary','contractQuery','contractState'])
   assert.ok(page.includes('id="'+id+'"'));
 assert.match(page,/r\.unsafeWatchX\?'⚠ '/);
 assert.match(page,/귀속 미승인/);
 const match=page.match(/<script>([\s\S]*?)<\/script>/);
 assert.ok(match);
 assert.doesNotThrow(()=>new vm.Script(match[1]));
 assert.ok(!page.includes('fetch(\'/api/contracts/write'));
});
