import test from "node:test";
import assert from "node:assert/strict";
import {isGbUnit,fromFeishuQuote,calculateDraft,draftDescription,draftPreflight}
  from "../lib/sfdc-report-quote-draft.mjs";

const quote=(gb="6",processQuantity="12")=>({
  status:"PASS",qid:"QID-2026-11-09-001111",
  sfdc_record_id:"a0P000000000000AAA",
  source_mail_received_kst:"2026-11-09 17:00:23 KST",
  currency:"USD_CONVERTED_ONLY",krw_rate_verified:false,
  process_lines:[
    {quotation_product_id:"QD-001",process_id:"P-SEQ",
      process_name:"Sequencing by data amount",data_unit:"G raw data",
      unit_price_usd:"7.50",sample_quantity:processQuantity,data_size:gb,
      product_total_usd_converted:"1000"},
    {quotation_product_id:"QD-001",process_id:"P-PREP",
      process_name:"Library preparation",data_unit:"G raw data",
      unit_price_usd:"35",sample_quantity:"1",data_size:gb,
      product_total_usd_converted:"1000"},
    {quotation_product_id:"QD-001",process_id:"P-QC",
      process_name:"QC",data_unit:"NA",unit_price_usd:"20",
      sample_quantity:"99",data_size:"NA",product_total_usd_converted:"1000"}
  ]
});

test("Gb production is the project discriminator, not old process quantity",()=>{
  assert.equal(isGbUnit("G raw data"),true);
  assert.equal(isGbUnit("M raw reads"),false);
  const first=fromFeishuQuote(quote("6","12"),new Date("2026-11-09T17:00:00Z"));
  const alternate=fromFeishuQuote(quote("6","99999"),new Date("2026-11-09T17:00:00Z"));
  const otherGb=fromFeishuQuote(quote("12","12"),new Date("2026-11-09T17:00:00Z"));
  assert.ok(first.ok);
  assert.equal(first.draft.products[0].referenceProductionGb,6);
  assert.equal(first.draft.products[0].productionGb,"6");
  assert.equal(first.draft.products[0].samples,"");
  assert.equal(first.draft.products[0].sampleUnitKrw,"");
  assert.equal(first.draft.products[0].projectKey,alternate.draft.products[0].projectKey);
  assert.notEqual(first.draft.products[0].projectKey,otherGb.draft.products[0].projectKey);
  assert.equal(first.draft.date,"2026-11-10");
});

test("New sample price and sample count remain separately editable; old USD is reference only",()=>{
  const a=fromFeishuQuote(quote()).draft;
  const b={...a,products:a.products.map(p=>({...p,samples:"5",sampleUnitKrw:"150000"}))};
  const c={...b,products:b.products.map(p=>({...p,samples:"20"}))};
  const calc=calculateDraft(b);
  assert.equal(calc.ok,true);
  assert.equal(calc.netKrw,750000);
  assert.equal(calc.vatKrw,75000);
  assert.equal(calc.grossKrw,825000);
  assert.equal(calc.items[0].projectKey,calculateDraft(c).items[0].projectKey);
  assert.equal(calc.sourceRateVerified,false);
  assert.equal(calc.crmSavePermitted,false);
  assert.notEqual(calc.netKrw,calculateDraft(c).netKrw);
});

test("Existing report quantity cannot become a new sample count",()=>{
  const old=quote("6","500");
  const draft=fromFeishuQuote(old).draft;
  assert.equal(draft.products[0].samples,"");
  assert.equal(calculateDraft(draft).code,"INPUT_SAMPLE_PRICE_OR_GB");
  assert.equal(draft.products[0].referenceTotalUsd,"1000");
});

test("When source Gb rows disagree, production remains unverified and editable",()=>{
  const old=quote();
  old.process_lines[1].data_size="12";
  const draft=fromFeishuQuote(old).draft;
  assert.deepEqual(draft.products[0].gbCandidates,[6,12]);
  assert.equal(draft.products[0].productionGb,"");
  assert.equal(draft.products[0].referenceProductionGb,null);
});

test("Non-Gb process data size must not become Gb production",()=>{
  const old=quote();
  for(const row of old.process_lines){row.data_unit="M raw reads";row.data_size="90";}
  const draft=fromFeishuQuote(old).draft;
  assert.equal(draft.products[0].productionGb,"");
  assert.equal(draft.products[0].gbCandidates.length,0);
});

test("Description is concise, dated, reference-based, and does not copy old Progress Description",()=>{
  const draft=fromFeishuQuote(quote(),new Date("2026-11-09T16:00:00Z")).draft;
  draft.products[0].samples="5";
  draft.products[0].sampleUnitKrw="150000";
  draft.name="Korea-Example-mRNA";
  const description=draftDescription(draft);
  assert.match(description,/2026-11-10/);
  assert.match(description,/6 Gb/);
  assert.match(description,/5 samples/);
  assert.match(description,/150,000 KRW\/sample/);
  assert.match(description,/Reference Quote: QID-/);
  assert.doesNotMatch(description,/99 samples|12 samples/);
  const preflight=draftPreflight({...draft,description:description+" 수동 변경"});
  assert.equal(preflight.status,"HOLD");
  assert.ok(preflight.errors.includes("REFERENCE_ACCOUNT_CONTACT_UNVERIFIED"));
  assert.equal(preflight.description.endsWith("수동 변경"),true);
  assert.equal(preflight.salesforceWrite,false);
  assert.equal(preflight.feishuWrite,false);
  assert.equal(preflight.crmSavePermitted,false);
});

test("Preclassified reference can keep source Account and Contact independently of project Gb",()=>{
  const old=quote();
  old.reference={
    status:"PASS",opportunityName:"Korea-Synthetic-mRNA",
    opportunityExternalId:"Opp-2026-11-09-901",
    accountId:"001000000000000AAA",accountName:"Synthetic University",
    contactId:"003000000000000AAA",contactName:"Synthetic Scientist",
    contactEmail:"synthetic@example.test",products:[]
  };
  const draft=fromFeishuQuote(old).draft;
  draft.name="Korea-Synthetic-New";
  draft.products[0].samples="5";draft.products[0].sampleUnitKrw="100000";
  const check=draftPreflight({...draft,description:draftDescription(draft)});
  assert.equal(check.status,"PREVIEW_READY");
  assert.equal(check.accountContactMode,"KEEP");
  assert.equal(check.crmSavePermitted,false);
  draft.accountMode="CHANGE";
  draft.account={id:"001000000000000AAB",name:"Different Institute"};
  draft.contact={id:"",name:"Different Researcher",email:""};
  const changed=draftPreflight({...draft,description:draftDescription(draft)});
  assert.equal(changed.status,"HOLD");
  assert.ok(changed.errors.includes("ACCOUNT_CONTACT_REVALIDATION_REQUIRED"));
  assert.equal(calculateDraft(draft).items[0].projectKey,
               check.pricing.items[0].projectKey);
});

test("No verified source ID gives HOLD but can be used as a reference",()=>{
  const old=quote();
  old.sfdc_record_id="";
  const extracted=fromFeishuQuote(old);
  assert.equal(extracted.ok,true);
  const draft=extracted.draft;
  draft.name="Korea-Example-mRNA";
  draft.products[0].samples="5";
  draft.products[0].sampleUnitKrw="100000";
  const r=draftPreflight({...draft,description:draftDescription(draft)});
  assert.equal(r.status,"HOLD");
  assert.ok(r.errors.includes("REFERENCE_RECORD_ID_UNMAPPED"));
});
