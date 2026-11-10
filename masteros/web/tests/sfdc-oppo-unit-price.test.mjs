import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {opportunityPriceBreakdown,freshProgress,validateRequest} from "../lib/sfdc-commands.mjs";
import {calculateDraft,fromFeishuQuote,opportunityUnitPriceSummary} from "../lib/sfdc-report-quote-draft.mjs";

const sampleOpportunity={
  action:"opportunity_create",mode:"check",
  referenceOpportunityId:"006000000000000AAA",accountId:"001000000000000AAA",
  contactId:"003000000000000AAA",accountName:"Example University",contactName:"Lee",
  opportunityName:"Korea-Example-12-mRNA",samples:12,dataSize:6,
  service:"mRNA-Seq",unit:"Gb",unitPriceNetKrw:250000,cloudUnitNetKrw:30000,
  cloudUnits:1,amountKrw:3030000,closeDate:"2026-11-30",referenceAmea:""
};
const request={...sampleOpportunity,progressDescription:freshProgress(sampleOpportunity)};

test("Oppo amount is samples * unit price plus verified AliCloud, never VAT inclusive",()=>{
  const priced=opportunityPriceBreakdown(sampleOpportunity);
  assert.equal(priced.ok,true);
  assert.equal(priced.sampleTotalKrw,3000000);
  assert.equal(priced.cloudTotalKrw,30000);
  assert.equal(priced.netKrw,3030000);
  assert.equal(priced.vatKrw,303000);
  assert.equal(priced.grossKrw,3333000);
  assert.match(request.progressDescription,/250,000KRW\/sample/);
  assert.match(request.progressDescription,/3,030,000 KRW/);
  assert.equal(validateRequest(request).ok,true);
});

test("Unit price mismatch and stale Progress Description cannot preflight or save",()=>{
  assert.equal(validateRequest({...request,amountKrw:3000000}).code,"OPPO_UNIT_PRICE_TOTAL_MISMATCH");
  assert.equal(validateRequest({...request,unitPriceNetKrw:260000,amountKrw:3150000})
    .code,"OPPO_DESCRIPTION_UNIT_PRICE_STALE");
  assert.equal(validateRequest({...request,unitPriceNetKrw:0}).ok,false);
  assert.equal(validateRequest({...request,cloudUnits:-1}).ok,false);
});

test("Product-level biological sample price includes every Amplicon region without duplicating samples",()=>{
  const fake={ok:true,netKrw:2160000,items:[{
    id:"QD-1",quantity:18,netKrw:2160000,regionCount:2,
    amplicon:{enabled:true},serviceQuantity:36
  }]};
  const unit=opportunityUnitPriceSummary(fake);
  assert.equal(unit.ok,true);
  assert.equal(unit.overallPerSampleNetKrw,120000);
  assert.equal(unit.products[0].samples,18);
  assert.equal(unit.products[0].serviceQuantity,36);
  const multi=opportunityUnitPriceSummary({...fake,items:[...fake.items,{...fake.items[0],id:"QD-2"}]});
  assert.equal(multi.singleProduct,false);
  assert.equal(multi.overallPerSampleNetKrw,null);
});

test("Oppo GUI exposes editable unit price and calculated total, not a misleading Quote price",()=>{
  const main=readFileSync(new URL("../app/sales/commands/page.jsx",import.meta.url),"utf8");
  const pair=readFileSync(new URL("../app/sales/commands/pair/ReportOppoDraft.jsx",import.meta.url),"utf8");
  assert.match(main,/Oppo 샘플당 단가 \(KRW, VAT 제외\)/);
  assert.match(main,/data-testid="oppo-unit-price-summary"/);
  assert.match(main,/opportunityPriceBreakdown\(form\)/);
  assert.match(pair,/data-testid="oppo-price-summary"/);
  assert.match(pair,/opportunityUnitPriceSummary\(amounts\)/);
});
