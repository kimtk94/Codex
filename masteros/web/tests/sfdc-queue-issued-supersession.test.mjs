import test from "node:test";
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {supersedeQueueQuoteDraft} from "../lib/sfdc-queue-issued-supersession.mjs";

function fixture(){
 const canonical={
  reference:{qid:"QID-2026-11-01-123456",sourceQuoteId:"a0P000000000001",
    opportunityId:"006000000000001"},
  proposed:{
   name:"Korea-Synthetic-4-PMP-5Gb",
   date:"2026-11-18",closeDate:"2026-12-18",
   description:"1118 Quote Draft PMP 5Gb 4 samples * 57,500KRW / Data release 1 × 30,000KRW",
   accountMode:"KEEP",
   account:{id:"001000000000001",name:"University"},
   contact:{id:"003000000000001",name:"Scientist"},
   quoteFeeMode:"EXCLUDE",
   products:[{id:"QD-123",samples:"4",productionGb:"5",sampleUnitKrw:"57500",
     fixedProcessLines:[{processName:"Data release",quantity:1,unitPriceKrw:30000,netKrw:30000}],
     processIds:["Process-2020-01-01-00001"]}]
  },
  review:{preflightStatus:"HOLD",missing:["NATIVE_ACCOUNT_CURRENT_PRICE_RECHECK"]}
 };
 const id="OPPOQUOTE-"+createHash("sha256")
  .update(JSON.stringify(canonical)).digest("hex").slice(0,24);
 return {ok:true,requestId:id,status:"NEEDS_REVIEW",canonical,
   state:"AWAITING_OPERATOR_APPROVAL",approved:false,requestedWrite:false,
   salesforceWrite:false,savePermitted:false,
   quoteWriterVerified:false,approvalRequired:true,receivedAtUtc:"2026-11-18T01:00:00Z"};
}

test("immutable Quote Draft queue is superseded by Quote Issued with only description changed",()=>{
 const old=fixture(),original=JSON.stringify(old);
 const next=supersedeQueueQuoteDraft(old,old.requestId);
 assert.equal(next.ok,true);
 assert.equal(next.newQueue.canonical.proposed.description,
   old.canonical.proposed.description.replace("Quote Draft","Quote Issued"));
 assert.equal(JSON.stringify(old),original,"source must remain immutable");
 assert.notEqual(next.requestId,old.requestId);
 assert.equal(next.newQueue.supersedesRequestId,old.requestId);
 assert.equal(next.newQueue.state,"AWAITING_OPERATOR_APPROVAL");
 assert.equal(next.newQueue.status,"NEEDS_REVIEW");
 assert.equal(next.newQueue.approved,false);
 assert.equal(next.newQueue.salesforceWrite,false);
 assert.equal(next.newQueue.savePermitted,false);
 assert.equal(next.crmWrites,0);
 const src=structuredClone(old.canonical),dst=structuredClone(next.newQueue.canonical);
 src.proposed.description=dst.proposed.description;
 assert.deepEqual(src,dst,"all names, IDs, prices, fees, service and sample quantities unchanged");
 assert.deepEqual(next.newQueue.canonical.proposed.contact,old.canonical.proposed.contact);
});

test("tampering, already-approved status, or duplicate wording cannot generate a replacement",()=>{
 const old=fixture();
 assert.equal(supersedeQueueQuoteDraft(old,"OPPOQUOTE-"+'a'.repeat(24)).code,
   "SOURCE_QUEUE_IDENTITY_INVALID");
 const approved=structuredClone(old);approved.approved=true;
 assert.equal(supersedeQueueQuoteDraft(approved,old.requestId).code,
   "SOURCE_QUEUE_ALREADY_APPROVED_OR_WRITTEN");
 const tampered=structuredClone(old);
 tampered.canonical.proposed.products[0].sampleUnitKrw="500000";
 assert.equal(supersedeQueueQuoteDraft(tampered,old.requestId).code,
   "SOURCE_QUEUE_IDENTITY_INVALID");
 const noStatus=structuredClone(old);
 noStatus.canonical.proposed.description="1118 Quote Issued PMP";
 noStatus.requestId="OPPOQUOTE-"+createHash("sha256")
  .update(JSON.stringify(noStatus.canonical)).digest("hex").slice(0,24);
 assert.equal(supersedeQueueQuoteDraft(noStatus,noStatus.requestId).code,
   "SOURCE_QUOTE_DRAFT_NOT_UNIQUE");
});
