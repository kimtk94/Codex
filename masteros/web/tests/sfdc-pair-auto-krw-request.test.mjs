import test from "node:test";
import assert from "node:assert/strict";
import {verifiedSourcePrice,prefillVerifiedKrw} from "../lib/sfdc-pair-auto-krw.mjs";
import {calculateDraft,draftDescription,opportunityUnitPriceSummary}
  from "../lib/sfdc-report-quote-draft.mjs";
import {validatePairRequest} from "../lib/sfdc-pair-request-queue.mjs";
import {historicalKrwReference,prefillHistoricalKrw} from "../lib/sfdc-pair-index-krw.mjs";

const quoteId="a0P000000000001AAA",oppoId="006000000000001AAA";
const ident={status:"PASS",sourceVerified:true,nativeQuoteId:quoteId};
const source={status:"PASS",source:"LIVE_SALESFORCE",read_only:true,
 cache:{state:"LIVE_SOURCE"},id:quoteId,opportunityId:oppoId,productCount:1,
 pricingStatus:"VERIFIED_PROCESS_LINES",sourceVatRateVerified10Pct:true,
 cloudLinePresent:true,sourcePackVerified:true,productName:"mRNA sequencing",
 samples:9,dataSize:6,sampleUnitNetKrw:100000,cloudUnitNetKrw:30000,
 sourceCloudUnits:1,totalPriceKrw:930000,processPriceLines:[
 {sourceQty:9,unitPriceKrw:100000,isCloud:false,packNo:"Pack1"},
 {sourceQty:1,unitPriceKrw:30000,isCloud:true,packNo:"Pack1"}]};
function draft(){
 return {qid:"QID-2026-11-01-111111",sourceQuoteId:quoteId,
  sourceOpportunityId:oppoId,sourceKrwRateStatus:"UNVERIFIED",
  accountMode:"KEEP",account:{id:"001000000000AAA",name:"University"},
  contact:{id:"003000000000AAA",name:"Researcher"},
  name:"Korea-Research-mRNA-Quote",
  date:"2026-11-17",closeDate:"2026-12-17",
  descriptionStatus:"Quote Draft",description:"",
  products:[{id:"qproduct001",productionGb:"6",samples:"",sampleUnitKrw:"",
    cloudUnitKrw:"",serviceLabel:"mRNA-Seq",
    priceEvidenceStatus:"NOT_VERIFIED",
    processes:[{name:"Sequencing",processId:"Process-2026-001"}],
    amplicon:{enabled:false,regions:[]}}]};
}
test("native KRW rates from authenticated source Quote prefill sample+Cloud",()=>{
 const result=verifiedSourcePrice(source,ident);
 assert.equal(result.ok,true);
 const populated=prefillVerifiedKrw(draft(),result);
 assert.equal(populated.products[0].samples,"9");
 assert.equal(populated.products[0].sampleUnitKrw,"100000");
 assert.equal(populated.products[0].cloudUnitKrw,"30000");
 const totals=calculateDraft(populated);
 assert.equal(totals.netKrw,930000);
 assert.equal(totals.items[0].cloudUnits,1);
 assert.equal(totals.items[0].cloudNetKrw,30000);
 assert.equal(opportunityUnitPriceSummary(totals).products[0].unitPriceNetKrw,100000);
 assert.deepEqual(totals.quoteLineItems.map(x=>x.kind),["PRODUCT","ALICLOUD"]);
});
test("100Gb AliCloud blocks step up without manual retyping",()=>{
 const p=prefillVerifiedKrw(draft(),verifiedSourcePrice(source,ident));
 p.products[0].samples="20";
 const total=calculateDraft(p);
 assert.equal(total.netKrw,2060000);
 assert.equal(total.items[0].cloudUnits,2);
 assert.equal(total.items[0].cloudNetKrw,60000);
 assert.equal(opportunityUnitPriceSummary(total).products[0].unitPriceNetKrw,100000);
});
test("invalid or unverified source price never silently applies",()=>{
 const bad=[{...source,pricingStatus:"PROCESS_BREAKDOWN_UNVERIFIED"},
  {...source,totalPriceKrw:1000000},
  {...source,sourceCloudUnits:2},
  {...source,sourcePackVerified:false},
  {...source,processPriceLines:[source.processPriceLines[0]]}];
 for(const q of bad)assert.equal(verifiedSourcePrice(q,ident).ok,false);
 const edited=draft();edited.products[0].sampleUnitKrw="110000";
 const out=prefillVerifiedKrw(edited,verifiedSourcePrice(source,ident));
 assert.equal(out.products[0].sampleUnitKrw,"110000");
 assert.ok(out.priceCandidate);
});
test("paired creation request is locally queued pending approval, not Salesforce save",()=>{
 const ready=prefillVerifiedKrw(draft(),verifiedSourcePrice(source,ident));
 ready.description=draftDescription(ready,calculateDraft(ready));
 const r=validatePairRequest({mode:"SUBMIT_FOR_APPROVAL",draft:ready});
 assert.equal(r.ok,true);
 assert.equal(r.status,"PENDING_APPROVAL");
 assert.equal(r.savePermitted,false);
 assert.equal(r.salesforceWrite,false);
 assert.equal(r.approvalRequired,true);
 assert.equal(r.canonical.review.verifiedNativeRateForUnchangedAmount,true);
 assert.equal(validatePairRequest({mode:"SUBMIT_FOR_APPROVAL",draft:ready}).requestId,r.requestId);
 const hold=draft();hold.description="";
 const hr=validatePairRequest({mode:"SUBMIT_FOR_APPROVAL",draft:hold});
 assert.equal(hr.ok,true);
 assert.equal(hr.status,"NEEDS_REVIEW");
 assert.equal(hr.savePermitted,false);
});

test("exact-QID 2026 KRW index prefills comparisons without granting Save",()=>{
 const base=draft(),p=base.products[0];
 const row={source_kind:"VERIFIED_SFDC_KRW_PROCESS_PRICE",
   source_verified:true,created_date:"2026-11-01",quote_id:base.qid,
   active:true,approval_status:"APPROVED",currency:"KRW",
   was_usd_converted:false,vat_basis:"VAT_EXCLUDED",
   account_id:"001000000000AAA",contact_id:"003000000000AAA",
   process_id:"Process-2026-001",product_signature:"f".repeat(64),
   unit_price_krw:"115000",data_unit:"G raw data",data_size:"6",
   sample_quantity:9,process_name:"Sequencing by data amount"};
 const index={version:"sfdc-2026-krw-process-prices-v1",
   source:"SFDC_AUTHENTICATED_READ_ONLY_KRW_PROCESS_LINES",
   generated_at:new Date().toISOString(),salesforce_write_performed:false,
   records:[row]};
 const candidate=historicalKrwReference(index,base.qid,p);
 assert.equal(candidate.ok,true);
 assert.equal(candidate.candidateSampleUnitKrw,115000);
 assert.equal(candidate.pricesApprovedForNewQuote,false);
 const emptyGb={...p,productionGb:""};
 const withoutGb=historicalKrwReference(index,base.qid,emptyGb);
 assert.equal(withoutGb.ok,true);
 assert.equal(withoutGb.sourceGbStatus,"UNVERIFIED");
 const populated=prefillHistoricalKrw(base,index);
 assert.equal(populated.products[0].sampleUnitKrw,"115000");
 assert.equal(populated.products[0].priceEvidenceStatus,"INDEX_2026_KRW_COMPARISON_ONLY");
 populated.description=draftDescription(populated,calculateDraft(populated));
 assert.equal(validatePairRequest({mode:"SUBMIT_FOR_APPROVAL",draft:populated}).status,"NEEDS_REVIEW");
 const upgraded=prefillVerifiedKrw(populated,verifiedSourcePrice(source,ident));
 assert.equal(upgraded.products[0].sampleUnitKrw,"100000");
 assert.equal(upgraded.products[0].cloudUnitKrw,"30000");
 assert.equal(upgraded.products[0].priceEvidenceStatus,"LIVE_SFDC_KRW_VERIFIED");
 const missingGb={...base,products:[{...base.products[0],productionGb:""}]};
 const autoSource=prefillVerifiedKrw(missingGb,verifiedSourcePrice(source,ident));
 assert.equal(autoSource.products[0].productionGb,"6");
 assert.equal(autoSource.products[0].sampleUnitKrw,"100000");
 assert.equal(historicalKrwReference(index,"QID-2026-11-01-999999",p).ok,false);
});
