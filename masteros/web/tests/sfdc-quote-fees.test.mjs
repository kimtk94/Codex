import test from "node:test";
import assert from "node:assert/strict";
import {attachVerifiedSourceFees,isVerifiedSourceFee,quoteFeeBreakdown}
  from "../lib/sfdc-quote-fees.mjs";
import {calculateDraft,draftDescription,draftPreflight,descriptionReview}
  from "../lib/sfdc-report-quote-draft.mjs";
import {validatePairRequest} from "../lib/sfdc-pair-request-queue.mjs";

const quote="a0P000000000001AAA";
const qp="a0N000000000001";
const evidence={
  status:"PASS",source:"LIVE_SALESFORCE_READ_ONLY",salesforce_write:false,
  nativeQuoteId:quote,feeCount:1,totalFeeKrw:300,
  feeLines:[{feeType:"SP Sample Shipping Fee",feeKrw:300,
    productName:"Synthetic Hi-C",sourceQuoteProductId:qp,currency:"KRW"}]
};
function draft(){
  return {sourceQuoteId:quote,sourceOpportunityId:"006000000000001AAA",
    qid:"QID-2026-11-10-111111",name:"Korea-Synthetic-Quote",
    date:"2026-11-17",closeDate:"2026-12-17",descriptionStatus:"Quote Draft",
    accountMode:"KEEP",account:{id:"001000000000001",name:"Synthetic"},
    contact:{id:"003000000000001",name:"Synthetic Person"},
    sourceKrwRateStatus:"VERIFIED",feeMode:"EXCLUDE",sourceFeeLines:[],
    source:"FEISHU_REPORT_USD_CONVERTED_ONLY",
    products:[{id:qp,productionGb:"5",samples:"2",sampleUnitKrw:"1000",
      cloudUnitKrw:"",serviceLabel:"Hi-C",processes:[{name:"Seq",processId:"P1"}],
      priceEvidenceStatus:"LIVE_SFDC_KRW_VERIFIED",
      priceSourceQuoteId:quote,priceSourceUnitKrw:1000,
      priceSourceCloudUnitKrw:0,amplicon:{enabled:false,regions:[]}}]
  };
}
test("no source fee is ever copied by default",()=>{
  const p=attachVerifiedSourceFees(draft(),evidence);
  assert.equal(p.feeMode,"EXCLUDE");
  assert.equal(p.sourceFeeLines.length,1);
  const calc=calculateDraft(p);
  assert.equal(calc.netKrw,2000);
  assert.equal(calc.grossKrw,2200);
  assert.equal(calc.quoteLineItems.some(x=>x.kind==="QUOTE_FEE"),false);
  assert.equal(calc.feeNetKrw,0);
});
test("explicit keep includes Fee after process net without inflating sample rate",()=>{
  const p={...attachVerifiedSourceFees(draft(),evidence),feeMode:"KEEP"};
  const calc=calculateDraft(p);
  assert.equal(calc.processNetKrw,2000);
  assert.equal(calc.feeNetKrw,300);
  assert.equal(calc.netKrw,2300);
  assert.equal(calc.vatKrw,230);
  assert.equal(calc.grossKrw,2530);
  assert.deepEqual(calc.quoteLineItems.map(x=>x.kind),["PRODUCT","QUOTE_FEE"]);
  assert.equal(calc.items[0].unitKrw,1000);
  assert.match(draftDescription(p),/SP Sample Shipping Fee 300KRW/);
  assert.deepEqual(descriptionReview(p,draftDescription(p)).missing,[]);
  const review=draftPreflight({...p,description:draftDescription(p)});
  assert.equal(review.status,"HOLD");
  assert.ok(review.errors.includes("QUOTE_FEE_SOURCE_REVALIDATION_REQUIRED"));
  const req=validatePairRequest({mode:"SUBMIT_FOR_APPROVAL",draft:{...p,
    description:draftDescription(p)}});
  assert.equal(req.ok,true);
  assert.equal(req.status,"NEEDS_REVIEW");
  assert.equal(req.canonical.proposed.quoteFeeLines.length,1);
  assert.equal(req.canonical.proposed.products[0].sampleUnitKrw,"1000");
  assert.equal(req.canonical.review.feeSourceRecheckRequired,true);
  assert.equal(req.savePermitted,false);
});
test("quote fee source tampering and cross-quote evidence fail closed",()=>{
  assert.equal(isVerifiedSourceFee(evidence,quote),true);
  assert.equal(isVerifiedSourceFee({...evidence,totalFeeKrw:301},quote),false);
  assert.equal(isVerifiedSourceFee({...evidence,feeLines:[{...evidence.feeLines[0],feeType:"Unknown"}]},quote),false);
  assert.equal(isVerifiedSourceFee({...evidence,nativeQuoteId:"a0P000000000002AAA"},quote),false);
  const noEvidence=attachVerifiedSourceFees(draft(),{...evidence,totalFeeKrw:400});
  assert.equal(noEvidence.feeEvidenceStatus,undefined);
  assert.equal(noEvidence.sourceFeeLines.length,0);
});
test("KEEP without verified source Fee is neither priced nor queued",()=>{
  const p={...draft(),feeMode:"KEEP"};
  assert.equal(quoteFeeBreakdown(p).ok,false);
  assert.equal(calculateDraft(p).code,"QUOTE_FEE_SOURCE_NOT_VERIFIED");
  const request=validatePairRequest({mode:"SUBMIT_FOR_APPROVAL",draft:{
    ...p,description:draftDescription(p)
  }});
  assert.equal(request.ok,false);
});
test("fee option changes revalidate an edited progress description",()=>{
  const source=attachVerifiedSourceFees(draft(),evidence);
  const old=draftDescription(source);
  const kept={...source,feeMode:"KEEP"};
  const result=descriptionReview(kept,old);
  assert.equal(result.complete,false);
  assert.ok(result.missing.some(x=>x.includes("SP Sample Shipping Fee")));
});
test("shipping is not introduced through evidence-only indexing for other QIDs",()=>{
  assert.equal(isVerifiedSourceFee(evidence,"a0P000000000002AAA"),false);
  const keep={...attachVerifiedSourceFees(draft(),evidence),feeMode:"KEEP"};
  const charge=quoteFeeBreakdown(keep);
  assert.equal(charge.quoteFeeItems[0].referenceOnly,true);
  assert.equal(charge.quoteFeeItems[0].needsNativeRecheck,true);
});
