import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {kstToday,kstOneCalendarMonthLater,EXPECTED_SAMPLE_STAGE}
  from "../lib/sfdc-new-opportunity-defaults.mjs";
import {verifiedQuoteProcessBreakdown,reportProcessComposition}
  from "../lib/sfdc-quote-process-review.mjs";
import {validateRequest,freshProgress} from "../lib/sfdc-commands.mjs";
import {buildPairDraft} from "../lib/sfdc-paired-clone.mjs";

const quote={
 id:"a0P000000000000AAA",opportunityId:"006000000000000AAA",
 quotationNumber:"AMEA2026091421",productCount:1,
 pricingStatus:"VERIFIED_PROCESS_LINES",sourceVatRateVerified10Pct:true,
 samples:42,dataSize:12,totalPriceKrw:8190000,grandTotalKrw:9009000,
 sampleUnitNetKrw:190000,cloudUnitNetKrw:35000,sourceCloudUnits:6,cloudLinePresent:true,
 processPriceLines:[
  {processName:"Library preparation",processType:"Library",packNo:"1",
   sourceQty:42,unitPriceKrw:150000,sourceNetKrw:6300000,isCloud:false},
  {processName:"Sequencing",processType:"Sequencing",packNo:"1",
   sourceQty:42,unitPriceKrw:40000,sourceNetKrw:1680000,isCloud:false},
  {processName:"AliCloud",sourceQty:6,unitPriceKrw:35000,
   sourceNetKrw:210000,isCloud:true}
 ],
 productName:"Eukaryotic mRNA",productCategory:"RNA",
 processNames:"Library preparation,Sequencing,AliCloud"
};
const opportunity={
 id:"006000000000000AAA",resource:"opportunity",name:"Korea-Example-42-mRNA-12Gb",
 accountId:"001000000000000AAA",contactId:"003000000000000AAA",
 accountName:"Example University",contactName:"Lee",service:"mRNA-Seq",
 closeDate:"2026-11-02"
};

test("KST month-ahead new Opportunity default and end-of-month clamp",()=>{
 assert.equal(kstToday(new Date("2026-11-10T15:01:00Z")),"2026-11-11");
 assert.equal(kstOneCalendarMonthLater(new Date("2026-11-10T15:01:00Z")),"2026-12-11");
 assert.equal(kstOneCalendarMonthLater(new Date("2026-01-30T15:01:00Z")),"2026-02-28");
 assert.equal(kstOneCalendarMonthLater(new Date("2028-01-30T15:01:00Z")),"2028-02-29");
 assert.equal(kstOneCalendarMonthLater(new Date("2026-12-30T15:01:00Z")),"2027-01-31");
});
test("Verified SFDC Quote shows each KRW process including AliCloud, Pack once per sample",()=>{
 const result=verifiedQuoteProcessBreakdown(quote,12,12);
 assert.equal(result.ok,true);
 assert.equal(result.items.length,3);
 assert.deepEqual(result.items.map(x=>x.unitPriceKrw),[150000,40000,35000]);
 assert.deepEqual(result.items.map(x=>x.quantity),[12,12,2]);
 assert.equal(result.items.reduce((n,x)=>n+x.projectedNetKrw,0),2350000);
 assert.equal(result.originalSampleRateKrw,190000);
 assert.equal(result.pack.quantity,12);
 assert.equal(result.pack.sourcePackNo,"1");
 assert.equal(result.pack.needsReview,true);
 const override=verifiedQuoteProcessBreakdown(quote,12,12,210000);
 assert.equal(override.manualOverride,true);
 assert.equal(override.priceAllocation,"PROCESS_ALLOCATIONS_MUST_BE_REVISED");
});
test("No USD converted Quote process treated as verified KRW rate",()=>{
 const result=reportProcessComposition({samples:"18",processes:[
  {name:"Sequencing",dataUnit:"Gb",sourceUnitUsd:"5.23"},
  {name:"Pack Sample",dataUnit:"sample",sourceUnitUsd:"12.5"}
 ]});
 assert.equal(result.krwUnitVerified,false);
 assert.equal(result.rows.length,2);
 assert.equal(result.pack.quantity,18);
});
test("Single Oppo+Quote validation requires matching names and explicit Pack/price approvals",()=>{
 const draft=buildPairDraft({status:"PASS",selectionStatus:"EXACT_ONE",
   opportunity,linkedQuotes:[quote]},{progressDescription:""}).form;
 const base={...draft,action:"oppo_quote_pair",mode:"check",
   samples:12,cloudUnits:2,amountKrw:2350000,packQuantity:12,
   quoteName:draft.opportunityName,progressDescription:freshProgress({
     ...draft,samples:12,cloudUnits:2}),closeDate:"2026-12-11",
   sampleStage:EXPECTED_SAMPLE_STAGE};
 assert.equal(validateRequest(base).ok,true);
 assert.equal(validateRequest({...base,quoteName:"Different"}).ok,false);
 assert.equal(validateRequest({...base,packQuantity:24}).ok,false);
 assert.equal(validateRequest({...base,mode:"save",confirmSave:true,
   noDuplicateConfirmed:true,priceConfirmed:true,
   packConfirmed:true,processPriceReviewed:true}).ok,true);
 assert.equal(validateRequest({...base,mode:"save",confirmSave:true,
   noDuplicateConfirmed:true,priceConfirmed:true,
   packConfirmed:false,processPriceReviewed:true}).ok,false);
});
test("UI has single save, visible included Quote processes and no confirmed sample receipt",()=>{
 const main=readFileSync(new URL("../app/sales/commands/page.jsx",import.meta.url),"utf8");
 const draft=readFileSync(new URL("../app/sales/commands/pair/ReportOppoDraft.jsx",import.meta.url),"utf8");
 const lead=readFileSync(new URL("../app/sales/mail/page.jsx",import.meta.url),"utf8");
 assert.match(main,/action:isPaired\?"oppo_quote_pair":tab/);
 assert.match(main,/Oppo \+ Quote 연속 생성/);
 assert.match(main,/verifiedQuoteProcessBreakdown/);
 assert.match(main,/Pack 수량/);
 assert.match(draft,/report-process-inclusions-/);
 assert.match(draft,/신규 Opportunity Close Date/);
 assert.match(lead,/Description 있음 · 내용 검토/);
 assert.match(lead,/Lead 생성일/);
 assert.match(lead,/최근 발송일/);
});
