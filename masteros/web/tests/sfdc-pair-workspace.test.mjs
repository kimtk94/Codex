import test from "node:test";
import assert from "node:assert/strict";
import {previewCandidate,pairWebRequest,priceLines,cloudQuantity} from "../lib/sfdc-pair-workspace.mjs";

const ids={opp:"006000000000000AAA",quote:"a0P000000000000AAA",
  newOpp:"006000000000000AAB"};
const quote={id:ids.quote,opportunityId:ids.opp,
  productCount:1,productName:"Demo RNA Product",productCategory:"RNA",
  pricingStatus:"VERIFIED_PROCESS_LINES",sourceVatRateVerified10Pct:true,
  cloudLinePresent:true};
const bundle={status:"PASS",selectionStatus:"EXACT_ONE",
  opportunity:{id:ids.opp,name:"Synthetic Opportunity"},
  linkedQuotes:[quote]};
const form={sourceOpportunityId:ids.opp,sourceQuoteId:ids.quote,
  newOpportunityName:"Synthetic-12-New",samples:12,dataSizeGb:12,
  productUnitOverrideKrw:"",cloudUnitOverrideKrw:""};

test("linked source must be a unique verified source pair",()=>{
  assert.equal(previewCandidate(bundle).pricingReady,true);
  assert.equal(previewCandidate({...bundle,selectionStatus:"MULTIPLE_SELECT_REQUIRED"}).ok,false);
  assert.equal(previewCandidate({...bundle,linkedQuotes:[{...quote,opportunityId:ids.newOpp}]}).ok,false);
});

test("two Products are evidence-only when source process mapping is absent",()=>{
  const result=previewCandidate({...bundle,linkedQuotes:[{
    ...quote,productCount:2,pricingStatus:"MULTI_PRODUCT_PROCESS_BREAKDOWN_UNVERIFIED",
    sourceProductEvidence:[{productKey:"item1",productName:"Service One"},
                           {productKey:"item2",productName:"Service Two"}]
  }]});
  assert.equal(result.ok,true);
  assert.equal(result.pricingReady,false);
  assert.equal(result.productEvidence.length,2);
  assert.equal(result.priceStatus,"SOURCE_PROCESS_PRICE_HOLD");
});

test("local web never creates SAVE request",()=>{
  for(const mode of ["CHECK_PRICE","CHECK_FORMS","CHECK_READBACK"]){
    const f={...form,newOpportunityId:ids.newOpp};
    const result=pairWebRequest(f,mode);
    assert.equal(result.ok,true);
    assert.equal(result.body.runMode,"CHECK");
    assert.equal(result.body.mode,mode);
    assert.equal(result.body.newOpportunityId,mode==="CHECK_READBACK"?ids.newOpp:undefined);
  }
  assert.equal(pairWebRequest(form,"SAVE").ok,false);
  assert.equal(pairWebRequest(form,"CREATE_PAIR").ok,false);
});

test("readback requires a truly new Opportunity ID",()=>{
  assert.equal(pairWebRequest({...form,newOpportunityId:ids.opp},"CHECK_READBACK").ok,false);
  assert.equal(pairWebRequest({...form,newOpportunityId:ids.newOpp},"CHECK_READBACK").ok,true);
});

test("per-Product unit prices stay separate, cloud is not a Product",()=>{
  const pricing={
    "Product Price Items JSON":JSON.stringify([
      {product:"A",qty:20,unit_krw:110000,net_krw:2200000},
      {product:"B",qty:20,unit_krw:190000,net_krw:3800000}
    ]),
    "Product Net KRW":6000000,"Cloud Qty":3,"Cloud Net KRW":105000,
    "Quote Net KRW":6105000,"VAT KRW":610500,"Quote Gross KRW":6715500
  };
  const rows=priceLines(pricing);
  assert.equal(rows.length,2);
  assert.deepEqual(rows.map(x=>x.unit_krw),[110000,190000]);
  assert.equal(rows.reduce((n,x)=>n+x.net_krw,0),6000000);
});

test("reject per-Product breakdown arithmetic mismatch",()=>{
  const p={"Product Price Items JSON":
      JSON.stringify([{product:"A",qty:10,unit_krw:100000,net_krw:100}]),
    "Product Net KRW":1000000};
  assert.equal(priceLines(p).length,0);
  assert.equal(priceLines({...p,"Product Price Items JSON":"NOT_JSON"}).length,0);
  assert.equal(priceLines({...p,"Product Price Items JSON":JSON.stringify([
    {product:"A",qty:10,unit_krw:100000,net_krw:1000000}]),
    "Product Net KRW":1000001}).length,0);
});

test("AliCloud 100 Gb rounds exactly once",()=>{
  assert.equal(cloudQuantity(10,10),1);
  assert.equal(cloudQuantity(10,15),2);
  assert.equal(cloudQuantity(12,12),2);
  assert.equal(cloudQuantity(20,12),3);
});
