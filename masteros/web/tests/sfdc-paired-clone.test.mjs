import test from "node:test";
import assert from "node:assert/strict";
import {cloudUnits,derivePairPrice,buildPairDraft,validatePairPayload} from "../lib/sfdc-paired-clone.mjs";
const quote={
 id:"a0P000000000000AAA",opportunityId:"006000000000000AAA",
 quotationNumber:"AMEA2026091421",productCount:1,
 pricingStatus:"VERIFIED_PROCESS_LINES",sourceVatRateVerified10Pct:true,
 samples:42,dataSize:12,totalPriceKrw:8190000,grandTotalKrw:9009000,
 sampleUnitNetKrw:190000,cloudUnitNetKrw:35000,sourceCloudUnits:6,cloudLinePresent:true,
 processPriceLines:[
  {processName:"Library preparation",sourceQty:42,unitPriceKrw:190000,sourceNetKrw:7980000,isCloud:false},
  {processName:"AliCloud",sourceQty:6,unitPriceKrw:35000,sourceNetKrw:210000,isCloud:true}
 ],
 productName:"Plant and Animal Eukaryotic mRNA (WOBI)",
 productCategory:"AMEA Plant and Animal RNA Sequencing",
 processNames:"Library preparation,Sequencing by data amount,Analysis by sample,Data release"
};
const opportunity={
 id:"006000000000000AAA",resource:"opportunity",name:"Korea-Example-42-mRNA-12Gb",
 accountId:"001000000000000AAA",contactId:"003000000000000AAA",
 accountName:"Example Institute",contactName:"KimTest",
 service:"Eukaryotic mRNA Sequencing",closeDate:"2026-11-30"
};
const bundle={status:"PASS",selectionStatus:"EXACT_ONE",opportunity,linkedQuotes:[quote]};
test("Cloud rounds total Gb once; 100, 150, 144 and 504 Gb examples",()=>{
 assert.equal(cloudUnits(1,100),1);
 assert.equal(cloudUnits(1,150),2);
 assert.equal(cloudUnits(12,12),2);
 assert.equal(cloudUnits(42,12),6);
 assert.equal(cloudUnits(2,100.5),3);
 assert.throws(()=>cloudUnits(0,12));
});
test("Actual 42-sample source splits sample and AliCloud fees and reprices 12",()=>{
 const price=derivePairPrice(quote,12,12);
 assert.deepEqual([price.unitPriceNetKrw,price.cloudUnitNetKrw,price.cloudUnits,
   price.sourceCloudUnits,price.netKrw,price.vatKrw,price.grossKrw],
   [190000,35000,2,6,2350000,235000,2585000]);
 assert.equal(price.cloudPriceIncluded,true);
 assert.equal(price.priceBasis,"SOURCE_QUOTE_PROCESS_UNIT_PRICES");
});
test("Block missing source process proof, inconsistent net, and data-size change",()=>{
 assert.equal(derivePairPrice({...quote,pricingStatus:"VERIFIED_SINGLE_LINE"},12,12).code,
  "SOURCE_PROCESS_PRICE_UNVERIFIED");
 assert.equal(derivePairPrice({...quote,totalPriceKrw:8170000},12,12).code,
  "SOURCE_PROCESS_SUM_MISMATCH");
 assert.equal(derivePairPrice(quote,12,15).code,"DATA_SIZE_CHANGED_REPRICE_REQUIRED");
 assert.equal(derivePairPrice({...quote,cloudLinePresent:false},12,12).code,
  "SOURCE_PROCESS_PRICE_UNVERIFIED");
 assert.equal(derivePairPrice({...quote,productCount:2},12,12).code,
  "SOURCE_PROCESS_PRICE_UNVERIFIED");
});
test("Only one linked Quote, same parent, one product, original progress discarded",()=>{
 const b=buildPairDraft(bundle,{closeDate:"",progressDescription:""});
 assert.equal(b.ok,true);
 assert.equal(b.form.progressDescription,"");
 assert.equal(b.form.unitPriceNetKrw,190000);
 assert.equal(b.form.cloudUnitNetKrw,35000);
 assert.equal(b.form.cloudUnits,6);
 assert.equal(b.form.amountKrw,8190000);
 assert.equal(buildPairDraft({...bundle,linkedQuotes:[quote,quote]}).ok,false);
 assert.equal(buildPairDraft({...bundle,selectionStatus:"MULTIPLE_SELECT_REQUIRED"}).ok,false);
});
test("Paired save requires source IDs, correct Cloud and explicit approvals",()=>{
 const b=buildPairDraft(bundle,{});const request={
  ...b.form,action:"oppo_quote_pair",mode:"save",samples:12,
  amountKrw:2350000,cloudUnits:2,closeDate:"2026-11-30",
  opportunityName:"Korea-Example-12-mRNA-12Gb",
  quoteName:"Korea-Example-12-mRNA-12Gb",packQuantity:12,
  progressDescription:"New quotation requested for 12 samples; PO not confirmed.",
  confirmSave:true,noDuplicateConfirmed:true,priceConfirmed:true,packConfirmed:true,
 };
 assert.equal(validatePairPayload(request).ok,true);
 assert.equal(validatePairPayload({...request,cloudUnits:12}).ok,false);
 assert.equal(validatePairPayload({...request,amountKrw:2340000}).ok,false);
 assert.equal(validatePairPayload({...request,confirmSave:false}).ok,false);
 assert.equal(validatePairPayload({...request,priceConfirmed:false}).ok,false);
 assert.equal(validatePairPayload({...request,dataSize:20}).ok,false);
 assert.equal(validatePairPayload({...request,sourceCloudUnits:5}).ok,false);
});
