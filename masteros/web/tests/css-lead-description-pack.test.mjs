import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {closeDateOneMonthFromKst} from "../lib/css-close-date.mjs";
import {quoteProcessReview} from "../lib/css-quote-process-review.mjs";

test("Close Date defaults one KST calendar month forward, including month ends",()=>{
  assert.equal(closeDateOneMonthFromKst(new Date("2026-11-11T06:40:00Z")),"2026-12-11");
  assert.equal(closeDateOneMonthFromKst(new Date("2026-01-31T06:00:00Z")),"2026-02-28");
  assert.equal(closeDateOneMonthFromKst(new Date("2024-01-31T06:00:00Z")),"2024-02-29");
  assert.equal(closeDateOneMonthFromKst(new Date("2026-12-31T03:00:00Z")),"2027-01-31");
  assert.equal(closeDateOneMonthFromKst(new Date("2026-11-10T15:30:00Z")),"2026-12-11");
});
const base={
 pricingStatus:"VERIFIED_PROCESS_LINES",productCount:1,
 sourceVatRateVerified10Pct:true,cloudLinePresent:true,
 sampleUnitNetKrw:120000,cloudUnitNetKrw:30000,
 sourceCloudUnits:1,totalPriceKrw:1470000,samples:12,dataSize:6,
 processPriceLines:[
  {packNo:"P1",processName:"QC",isCloud:false,sourceQty:12,unitPriceKrw:20000},
  {packNo:"P1",processName:"Library",isCloud:false,sourceQty:12,unitPriceKrw:100000},
  {packNo:"P2",processName:"AliCloud",isCloud:true,sourceQty:1,unitPriceKrw:30000}
 ]
};
test("Quote process review itemizes every included process, per-sample rate and Pack",()=>{
  const x=quoteProcessReview(base,12,6);
  assert.equal(x.ok,true);
  assert.equal(x.packStatus,"PASS");
  assert.equal(x.sampleUnitKrw,120000);
  assert.equal(x.cloudUnitKrw,30000);
  assert.equal(x.netKrw,1470000);
  assert.deepEqual(x.lines.map(v=>v.quantity),[12,12,1]);
});
test("Missing/mismatched Pack and missing process-price proofs are review, not accepted",()=>{
  assert.equal(quoteProcessReview({...base,processPriceLines:base.processPriceLines.map(
    (p,i)=>i===0?{...p,packNo:""}:p)},12,6).packStatus,"REVIEW_MISSING_PACK");
  assert.equal(quoteProcessReview({...base,processPriceLines:base.processPriceLines.map(
    (p,i)=>i===0?{...p,packNo:"P3"}:p)},12,6).packStatus,"REVIEW_SAME_SAMPLE_MULTIPLE_PACKS");
  assert.equal(quoteProcessReview({...base,pricingStatus:"PROCESS_BREAKDOWN_UNVERIFIED"},12,6).ok,false);
});
test("Quote process review rejects source line, price and cloud mismatches",()=>{
 const badLine={...base,processPriceLines:base.processPriceLines.map(
   (p,i)=>i===0?{...p,sourceNetKrw:99999}:p)};
 assert.equal(quoteProcessReview(badLine,12,6).ok,false);
 const badUnit={...base,processPriceLines:base.processPriceLines.map(
   (p,i)=>i===1?{...p,unitPriceKrw:90000}:p)};
 assert.equal(quoteProcessReview(badUnit,12,6).code,"PROCESS_PRICE_PARITY_MISMATCH");
 const badGross={...base,totalPriceKrw:1471000};
 assert.equal(quoteProcessReview(badGross,12,6).ok,false);
 assert.equal(quoteProcessReview({...base,sourceCloudUnits:2},12,6).ok,false);
});

test("Lead description and combined Oppo Quote UI retain safety boundaries",()=>{
  const mail=readFileSync(new URL("../app/sales/mail/page.jsx",import.meta.url),"utf8");
  const opp=readFileSync(new URL("../app/sales/commands/page.jsx",import.meta.url),"utf8");
  const picker=readFileSync(new URL("../app/sales/commands/IdentityPicker.jsx",import.meta.url),"utf8");
  const worker=readFileSync(new URL("../scripts/css_mail_local.py",import.meta.url),"utf8");
  const raw=readFileSync(new URL("../scripts/sfdc_record_catalog.py",import.meta.url),"utf8");
  assert.match(mail,/lead-description-HAS_DESCRIPTION|lead-description-/);
  assert.match(mail,/Lead 생성일/);
  assert.match(mail,/생성 후 최초 발송일/);
  assert.match(worker,/LEAD_DESCRIPTION_ID_PARITY/);
  assert.match(worker,/raw_descriptions=descriptions/);
  assert.match(opp,/OPPO_ONLY_SAVE_BLOCKED_USE_PAIRED_FLOW/);
  assert.match(opp,/closeDateOneMonthFromKst\(\)/);
  assert.match(opp,/oppo-quote-process-lines/);
  assert.match(picker,/selected\.account\.id!==account\.id/);
  assert.match(raw,/"packNo":str\(cells\[1\]\)/);
});
