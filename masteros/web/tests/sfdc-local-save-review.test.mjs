import test from "node:test";
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {reviewQueueRecord,isQueueRequestId} from "../lib/sfdc-local-save-review.mjs";

function makeEntry(){
 const canonical={
  reference:{qid:"QID-2026-11-01-123456",
   sourceQuoteId:"a0P000000000001",opportunityId:"006000000000001"},
  proposed:{
   name:"Korea-Synthetic-mRNA-48samples",date:"2026-11-18",
   closeDate:"2026-12-18",description:"New sample intake expected; PO unconfirmed.",
   accountMode:"CHANGE",
   account:{id:"001000000000001",name:"가상대학교"},
   contact:{id:"003000000000001",name:"가상연구원"},
   products:[{
    id:"QD-SYNTHETIC-01",serviceLabel:"Synthetic RNA",
    productionGb:"6",samples:"48",sampleUnitKrw:"200000",cloudUnitKrw:"30000",
    processIds:["Process-2026-01-01-00001","Process-2026-01-01-00002"],
    processNames:["Synthetic preparation","Synthetic sequencing"],
    priceEvidenceStatus:"LIVE_SFDC_KRW_VERIFIED"
   }],
   quoteFeeMode:"EXCLUDE",
   quoteFeeLines:[]},
  review:{preflightStatus:"PREVIEW_READY",
   missing:[],verifiedNativeRateForUnchangedAmount:true}
 };
 const requestId="OPPOQUOTE-"+createHash("sha256")
  .update(JSON.stringify(canonical)).digest("hex").slice(0,24);
 return {requestId,canonical,state:"AWAITING_OPERATOR_APPROVAL",
  status:"PENDING_APPROVAL",approved:false,requestedWrite:false,
  salesforceWrite:false,savePermitted:false,
  receivedAtUtc:"2026-11-18T01:20:00Z"};
}

test("valid local queue becomes read-only review with immutable original reference",()=>{
 const e=makeEntry(),r=reviewQueueRecord(e,e.requestId);
 assert.equal(r.status,"QUEUE_REVIEW_READY_SFDC_NATIVE_RECHECK_REQUIRED");
 assert.equal(r.requestId,e.requestId);
 assert.equal(r.account.sourceIdPresent,true);
 assert.equal(r.contact.sourceIdPresent,true);
 assert.equal(r.name,"Korea-Synthetic-mRNA-48samples");
 assert.equal(r.productCount,1);
 assert.equal(r.products[0].original_process_ids.length,2);
 assert.equal(r.products[0].historical_sample_unit_krw,"200000");
 assert.equal(r.products[0].historical_sample_subtotal_krw,"9600000");
 assert.equal(r.provisionalSampleOnlySubtotalKrw,"9600000");
 assert.equal(r.provisionalExcludesCloudFeeAndProcessDifferences,true);
 assert.equal(r.salesforceCreateEnabled,false);
 assert.equal(r.approvalLocked,true);
 assert.equal(r.salesforceWrite,false);
 assert.equal(r.crmWrites,0);
 assert.equal(r.verifiedCheckCount,0);
 assert.equal(r.requiredChecks.length,10);
});
test("old verified Quote price is not new client price approval",()=>{
 const e=makeEntry(),r=reviewQueueRecord(e,e.requestId);
 assert.equal(e.canonical.review.verifiedNativeRateForUnchangedAmount,true);
 assert.equal(r.requiredChecks.find(x=>x.id==="new_client_price").passed,false);
 assert.equal(r.requiredChecks.find(x=>x.id==="native_id_identity").passed,false);
 assert.equal(r.requiredChecks.find(x=>x.id==="approval").passed,false);
});
test("tampering with canonical data after request id is issued is blocked",()=>{
 const e=makeEntry();
 e.canonical.proposed.products[0].sampleUnitKrw="1000";
 assert.equal(reviewQueueRecord(e,e.requestId).code,"QUEUE_IMMUTABLE_DIGEST_MISMATCH");
});
test("approval-pending envelope cannot be promoted to a Save request",()=>{
 for(const key of ["approved","requestedWrite","salesforceWrite","savePermitted"]){
   const e=makeEntry();e[key]=true;
   assert.equal(reviewQueueRecord(e,e.requestId).status,"HOLD_QUEUE_RECORD",key);
 }
 for(const st of ["CREATED","APPROVED","COMMITTED"]){
   const e=makeEntry();e.state=st;
   assert.equal(reviewQueueRecord(e,e.requestId).status,"HOLD_QUEUE_RECORD",st);
 }
});
test("requestId path traversal cannot select a different queue file",()=>{
 for(const v of ["","../abc","OPPOQUOTE-ABC","OPPOQUOTE-"+"a".repeat(25),
  "OPPOQUOTE-"+"a".repeat(24)+"/../../x"]){
  assert.equal(isQueueRequestId(v),false,v);
  assert.equal(reviewQueueRecord(makeEntry(),v).status,"HOLD_QUEUE_RECORD",v);
 }
});
test("no fee or AliCloud inferred from historical sample-only subtotal",()=>{
 const e=makeEntry();
 const r=reviewQueueRecord(e,e.requestId);
 assert.equal(r.cloudAndFeeStatus,"HOLD_SOURCE_RECHECK");
 assert.equal(r.fees.length,0);
 assert.equal(r.provisionalExcludesCloudFeeAndProcessDifferences,true);
 assert.equal(r.savePermitted,false);
});
test("invalid historical sample rate does not invent a product total",()=>{
 const e=makeEntry();
 e.canonical.proposed.products[0].sampleUnitKrw="RECHECK";
 e.requestId="OPPOQUOTE-"+createHash("sha256")
  .update(JSON.stringify(e.canonical)).digest("hex").slice(0,24);
 const r=reviewQueueRecord(e,e.requestId);
 assert.equal(r.provisionalSampleOnlySubtotalKrw,null);
 assert.equal(r.products[0].historical_sample_subtotal_krw,null);
 assert.equal(r.status,"QUEUE_REVIEW_READY_SFDC_NATIVE_RECHECK_REQUIRED");
});
test("queue record must have one to twelve well formed products",()=>{
 const e=makeEntry();e.canonical.proposed.products=[];
 e.requestId="OPPOQUOTE-"+createHash("sha256")
 .update(JSON.stringify(e.canonical)).digest("hex").slice(0,24);
 assert.equal(reviewQueueRecord(e,e.requestId).code,"QUEUE_CANONICAL_INVALID");
});

test("explicit Data release fixed Process is included in 2026 KRW reference comparison but not authorized Save",()=>{
 const e=makeEntry(),p=e.canonical.proposed.products[0];
 p.samples="4";p.sampleUnitKrw="57500";p.cloudUnitKrw="";
 p.fixedProcessLines=[{
  processId:"Process-2026-01-01-00001",
  processName:"Data release",
  quantity:1,unitPriceKrw:30000,netKrw:30000
 }];
 e.requestId="OPPOQUOTE-"+createHash("sha256")
   .update(JSON.stringify(e.canonical)).digest("hex").slice(0,24);
 const r=reviewQueueRecord(e,e.requestId);
 assert.equal(r.products[0].historical_sample_subtotal_krw,"230000");
 assert.equal(r.products[0].fixed_process_subtotal_krw,"30000");
 assert.equal(r.provisionalFixedProcessNetKrw,"30000");
 assert.equal(r.provisionalProcessInclusiveNetKrw,"260000");
 assert.equal(r.provisionalVat10Krw,"26000");
 assert.equal(r.provisionalGross10Krw,"286000");
 assert.equal(r.comparisonOnlyNotNativePriceApproval,true);
 assert.equal(r.salesforceCreateEnabled,false);
 assert.equal(r.approvalLocked,true);
});
test("fixed Process amount inconsistent with original row must not create a plausible comparison total",()=>{
 const e=makeEntry(),p=e.canonical.proposed.products[0];
 p.fixedProcessLines=[{
  processId:"Process-2026-01-01-00001",
  processName:"Data release",quantity:1,unitPriceKrw:30000,netKrw:29999
 }];
 e.requestId="OPPOQUOTE-"+createHash("sha256")
   .update(JSON.stringify(e.canonical)).digest("hex").slice(0,24);
 const r=reviewQueueRecord(e,e.requestId);
 assert.equal(r.fixedProcessSourceConsistent,false);
 assert.equal(r.provisionalFixedProcessNetKrw,null);
 assert.equal(r.provisionalProcessInclusiveNetKrw,null);
 assert.equal(r.savePermitted,false);
});
