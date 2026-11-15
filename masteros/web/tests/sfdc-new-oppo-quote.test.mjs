import test from "node:test";
import assert from "node:assert/strict";
import {PATTERNS,nextMonth,createIntake} from "../lib/sfdc-new-oppo-quote.mjs";
const base={institution:"제주대학교",contact:"이태백",identityMode:"KEEP",service:"RNA",
 samples:"48",production:"6",basis:"PER_SAMPLE",unit:"Gb",cloud:"YES",referenceQuote:"",
 desiredName:"",sampleType:"Human",status:"SAMPLES_EXPECTED"};
test("matched names and calendar-month Close Date",()=>{
 const v=createIntake(base,"2026-11-15");
 assert.equal(v.status,"HOLD_SFDC_ID_PRODUCT_PRICE_APPROVAL");
 assert.equal(v.suggested.opportunityName,v.suggested.quotationName);
 assert.equal(v.suggested.closeDateKst,"2026-12-15");
 assert.equal(nextMonth("2027-01-31"),"2027-02-28");
 assert.equal(nextMonth("2028-01-31"),"2028-02-29");
});
test("total Gb and per-sample Gb keep distinct, Alicloud rounds up",()=>{
 const v=createIntake(base,"2026-11-15");
 assert.equal(v.suggested.productionTotal.value,288);
 assert.equal(v.suggested.alicloudQuantity,3);
 const t=createIntake({...base,production:"150",basis:"TOTAL"},"2026-11-15");
 assert.equal(t.suggested.alicloudQuantity,2);
 const reads=createIntake({...base,unit:"M reads"},"2026-11-15");
 assert.equal(reads.suggested.alicloudQuantity,null);
});
test("missing required fields produce HOLD and no fabricated native IDs/prices",()=>{
 const v=createIntake({...base,institution:"",contact:"",samples:"",production:""},"2026-11-15");
 assert.equal(v.status,"HOLD_REQUIRED_INPUT");
 assert.deepEqual(v.missing.slice(0,2),["institution","contact"]);
 assert.equal(v.suggested.productId,null);
 assert.equal(v.suggested.pricePerProcess,null);
 assert.equal(v.salesforceSaveAllowed,false);
 assert.equal(v.crmWrites,0);
});
test("invalid units, fractional samples, unsafe name block intake",()=>{
 const v=createIntake({...base,unit:"unknown",samples:"2.5",desiredName:"bad\nname"},"2026-11-15");
 assert.ok(["unit","samples","desiredName"].every(x=>v.missing.includes(x)));
 assert.equal(v.suggested.productionTotal,null);
});
test("single-cell never gets guessed processes and reference quote is not verified",()=>{
 const v=createIntake({...base,service:"SPATIAL",referenceQuote:"sample-ref"},"2026-11-15");
 assert.equal(PATTERNS.SPATIAL.processes.length,0);
 assert.equal(v.suggested.historicalProcesses.length,0);
 assert.equal(v.suggested.referenceQuoteState,"USER_REFERENCE_UNVERIFIED");
 assert.equal(v.salesforceSaveAllowed,false);
});
