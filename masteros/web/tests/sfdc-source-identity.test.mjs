import test from "node:test";
import assert from "node:assert/strict";
import {reconcileQuoteSource,applyVerifiedSource,canonicalSalesforceId,sameSalesforceId} from "../lib/sfdc-source-identity.mjs";

const f={status:"PASS",sfdc_record_id:"a0PABCDEFGHIJKL",
  reference:{accountId:"001ABCDEFGHIJKL",contactExternalId:"Contact-2026-001",
    opportunityName:"Korea-Institute-PMP"}};
const cache={state:"LIVE_SOURCE"};
const q={status:"PASS",source:"LIVE_SALESFORCE",read_only:true,cache,
  id:"a0PABCDEFGHIJKL",opportunityId:"006ABCDEFGHIJKL",
  accountId:"001ABCDEFGHIJKL",contactId:"003ABCDEFGHIJKL",
  name:"Quotation differs"};
const o={status:"PASS",source:"LIVE_SALESFORCE",read_only:true,cache,
  id:"006ABCDEFGHIJKL",accountId:"001ABCDEFGHIJKL",
  contactId:"003ABCDEFGHIJKL",accountName:"Institute",contactName:"Client",
  name:"Korea-Institute-PMP"};

test("native Quote and linked Opportunity match but different names require review",()=>{
  const r=reconcileQuoteSource(f,q,o);
  assert.equal(r.status,"PASS");
  assert.equal(r.nameReview,true);
  assert.equal(r.contact.id,"003ABCDEFGHIJKL");
  assert.equal(r.nativeOpportunityId,"006ABCDEFGHIJKL");
  assert.equal(r.canSave,false);
  assert.equal(r.krwRateVerified,false);
});
test("missing or mismatched source never promotes customer IDs",()=>{
  const variants=[
    [f,{...q,accountId:"001ZZZZZZZZZZZZ"},o],
    [f,q,{...o,contactId:"003ZZZZZZZZZZZZ"}],
    [f,{...q,opportunityId:"006ZZZZZZZZZZZZ"},o],
    [f,{...q,id:"a0PZZZZZZZZZZZZ"},o],
    [f,{...q,cache:{state:"FRESH_CACHE"}},o],
    [f,q,{...o,cache:undefined}],
    [{...f,sfdc_record_id:""},q,o],
    [{...f,reference:{...f.reference,contactId:"003ZZZZZZZZZZZZ"}},q,o]
  ];
  for(const v of variants){
    const r=reconcileQuoteSource(...v);
    assert.equal(r.status,"HOLD",r.code);
    assert.equal(r.sourceVerified,false);
  }
});
test("verified IDs hydrate KEEP draft but never rewrite changed fields",()=>{
  const r=reconcileQuoteSource(f,q,o);
  const d={
    sourceQuoteId:f.sfdc_record_id,accountMode:"KEEP",
    account:{id:f.reference.accountId,name:"Old"},
    referenceAccount:{id:f.reference.accountId,name:"Old"},
    contact:{externalId:f.reference.contactExternalId,name:"Old"},
    referenceContact:{externalId:f.reference.contactExternalId,name:"Old"},
    name:"Edited name",date:"2026-11-10",
    products:[{id:"x",samples:"48",productionGb:"12",sampleUnitKrw:"25000"}],
    referenceDefaults:{name:"Original",account:{id:f.reference.accountId,name:"Old"},
      contact:{id:"",name:"Old"}}
  };
  const fresh=applyVerifiedSource(d,r);
  assert.equal(fresh.contact.id,"003ABCDEFGHIJKL");
  assert.equal(fresh.account.id,"001ABCDEFGHIJKL");
  assert.equal(fresh.sourceOpportunityId,"006ABCDEFGHIJKL");
  assert.equal(fresh.products[0].samples,"48");
  assert.equal(fresh.products[0].sampleUnitKrw,"25000");
  assert.equal(fresh.name,"Edited name");
  assert.equal(fresh.referenceDefaults.contact.id,"003ABCDEFGHIJKL");
});
test("CHANGE mode never overwrites customer selection",()=>{
  const r=reconcileQuoteSource(f,q,o);
  const d={sourceQuoteId:f.sfdc_record_id,accountMode:"CHANGE",
    referenceAccount:{id:f.reference.accountId},account:{id:"OTHER"},
    contact:{id:"OTHER"},products:[]};
  assert.equal(applyVerifiedSource(d,r),d);
});

test("Salesforce 15 and checksum-verified 18 character IDs are the same record",()=>{
  const a15="001ABCDEFGHIJKL";
  const a18="001ABCDEFGHIJKLY55";
  assert.equal(canonicalSalesforceId(a18,"001"),a15);
  assert.equal(sameSalesforceId(a15,a18,"001"),true);
  assert.equal(sameSalesforceId(a15,a18.slice(0,15)+"XXX","001"),false);
  assert.equal(sameSalesforceId(a15,a15.toLowerCase(),"001"),false);
  assert.equal(sameSalesforceId(a15,"001ABCDEFGHIJKM","001"),false);
});

test("Feishu 15-character Account and Salesforce 18-character Account reconcile",()=>{
  const fx={...f,reference:{...f.reference,accountId:"001ABCDEFGHIJKL"}};
  const qx={...q,id:"a0PABCDEFGHIJKL255",opportunityId:"006ABCDEFGHIJKLY55",
    accountId:"001ABCDEFGHIJKLY55",contactId:"003ABCDEFGHIJKLY55"};
  const ox={...o,id:"006ABCDEFGHIJKL",accountId:"001ABCDEFGHIJKL",
    contactId:"003ABCDEFGHIJKL"};
  const r=reconcileQuoteSource(fx,qx,ox);
  assert.equal(r.status,"PASS",r.code);
  assert.equal(r.account.id,qx.accountId);
  const draft={sourceQuoteId:fx.sfdc_record_id,accountMode:"KEEP",
    referenceAccount:{id:fx.reference.accountId,name:"Old"},
    account:{id:fx.reference.accountId,name:"Old"},contact:{id:"",name:"Old"},
    products:[{samples:"48",productionGb:"12",sampleUnitKrw:"25000"}],
    referenceDefaults:{account:{id:fx.reference.accountId},contact:{id:""}}};
  const hydrated=applyVerifiedSource(draft,r);
  assert.equal(hydrated.contact.id,qx.contactId);
  assert.equal(hydrated.products[0].samples,"48");
  assert.equal(hydrated.products[0].sampleUnitKrw,"25000");
  assert.equal(hydrated.sourceOpportunityId,ox.id);
  assert.equal(hydrated.crmSavePermitted,undefined);
});

test("Invalid Salesforce 18-character checksum never authorizes source inheritance",()=>{
  const bad={...q,id:"a0PABCDEFGHIJKLZZZ"};
  const result=reconcileQuoteSource(f,bad,o);
  assert.equal(result.status,"HOLD");
  assert.equal(result.canSave,false);
});
