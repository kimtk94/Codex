'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {inspectOwnerContractReview}=require('../lib/contract-owner-audit');
const CANDIDATE='CANDIDATE_ONLY_REQUIRES_ORIGINAL_CONTRACT_REVIEW';
const QUARANTINE='QUARANTINE_NO_CONTRACT_ATTRIBUTION';
function source(){
  return {available:true,status:'REVIEW_SOURCE_STALE',verified:false,
    candidateCount:1,missingCount:1,items:[
      {amea:'AMEA2026090309',project:'ChangWon',unsafeWatchX:'X209SC26065705-Z01',
        candidateX:'X209SC26107211',source:'FINANCE',state:'FINANCE_AMEA_CANDIDATE',
        onlineH:'',onlineStage:'',gate:CANDIDATE,financeStale:true,
        attributionVerified:false,issuanceVerified:false,paymentVerified:false,
        revenueActualApproved:false},
      {amea:'AMEA2026090335',project:'Konkuk',unsafeWatchX:'X209SC26089427-Z01',
        candidateX:'',source:'NONE',state:'NO_AMEA_SOURCE_CANDIDATE',
        onlineH:'',onlineStage:'',gate:QUARANTINE,financeStale:true,
        attributionVerified:false,issuanceVerified:false,paymentVerified:false,
        revenueActualApproved:false}
    ]};
}
test('finance only AMEA candidates remain unapproved and old wrong Watch X is separated',()=>{
  assert.equal(inspectOwnerContractReview(source()),true);
});
test('missing, malformed, duplicated or non-owner source cannot PASS',()=>{
  assert.equal(inspectOwnerContractReview(null),false);
  const s=source();s.available=false;
  assert.equal(inspectOwnerContractReview(s),false);
  const duplicate=source();duplicate.items[1].amea=duplicate.items[0].amea;
  assert.equal(inspectOwnerContractReview(duplicate),false);
  const wrong=source();wrong.items[0].candidateX='X209SC26065705-Z01';
  assert.equal(inspectOwnerContractReview(wrong),false);
  const missing=source();missing.items=missing.items.slice(1);missing.candidateCount=0;
  assert.equal(inspectOwnerContractReview(missing),false);
});
test('receipt, invoice, revenue or ownership approval cannot be forged from candidate evidence',()=>{
  for(const property of ['paymentVerified','issuanceVerified','attributionVerified','revenueActualApproved']){
    const s=source();s.items[0][property]=true;
    assert.equal(inspectOwnerContractReview(s),false,property);
  }
  const forge=source();forge.items[0].gate='CONTRACT_APPROVED';
  assert.equal(inspectOwnerContractReview(forge),false);
  const count=source();count.candidateCount=2;
  assert.equal(inspectOwnerContractReview(count),false);
});
test('cross-AMEA duplicate X cannot silently pass owner diagnostic',()=>{
  const s=source();s.items[1].candidateX='X209SC26107211-Z01';
  s.items[1].gate=CANDIDATE;s.candidateCount=2;s.missingCount=0;
  assert.equal(inspectOwnerContractReview(s),false);
});
test('OAuth-only owner smoke requires contract review and excludes PII from response',()=>{
  const src=fs.readFileSync(path.join(__dirname,'..','api','lifecycle','owner-smoke.js'),'utf8');
  const html=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
  assert.match(src,/if\(!owner\.oauthValid\)/);
  assert.match(src,/inspectOwnerContractReview\(dashboard\.data\?\.contractReview\)/);
  assert.match(src,/contractReview:'AMEA_CANDIDATES_UNAPPROVED_CHECKED'/);
  assert.match(src,/dataDisclosure:'NO_CUSTOMER_DATA_IN_DIAGNOSTIC'/);
  assert.match(src,/productionPromotion:false/);
  assert.match(html,/result\.contractReview==='AMEA_CANDIDATES_UNAPPROVED_CHECKED'/);
});
