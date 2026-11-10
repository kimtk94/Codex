import test from "node:test";
import assert from "node:assert/strict";
import {isGbUnit,fromFeishuQuote,calculateDraft,draftDescription,draftPreflight,descriptionBasis,descriptionReview,DESCRIPTION_TEMPLATE_VERSION}
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
  assert.match(description,/^1110 Quote Draft /);
  assert.match(description,/6Gb/);
  assert.match(description,/5 samples/);
  assert.match(description,/150,000KRW/);
  assert.doesNotMatch(description,/Reference Quote|기존 Quote는 참고값/);
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

test("Description template stays deterministic and never imports old Progress Description",()=>{
  const original=quote();
  original.progress_description="OLD CUSTOMER PROGRESS: PO received 2026-08-01";
  original.oldDescription="Legacy text";
  const draft=fromFeishuQuote(original,new Date("2026-11-09T15:03:00Z")).draft;
  draft.account={name:"Synthetic School",id:"001000000000000AAA"};
  draft.contact={name:"Synthetic PI",id:"003000000000000AAA"};
  draft.products[0].samples="12";
  draft.products[0].sampleUnitKrw="200000";
  const description=draftDescription(draft);
  assert.equal(DESCRIPTION_TEMPLATE_VERSION,"OPPO_QUOTE_SHORT_V2");
  assert.equal(description,draftDescription({...draft}));
  assert.match(description,/^1110 Quote Draft /);
  assert.doesNotMatch(description,/Account\/Contact|Reference Quote/);
  assert.match(description,/6Gb/);
  assert.match(description,/12 samples/);
  assert.match(description,/200,000KRW/);
  assert.doesNotMatch(description,/PO received|OLD CUSTOMER PROGRESS|Legacy text/);
  assert.deepEqual(descriptionReview(draft,description),{
    stale:false,complete:true,missing:[]
  });
});

test("Manually locked Description is not overwritten and becomes HOLD when sample price changes",()=>{
  const source=quote();
  source.reference={
    status:"PASS",accountId:"001000000000000AAA",accountName:"Synthetic School",
    contactId:"003000000000000AAA",contactName:"Synthetic PI",products:[]
  };
  const draft=fromFeishuQuote(source).draft;
  draft.name="Korea-Synthetic-Project";
  draft.products[0].samples="8";
  draft.products[0].sampleUnitKrw="85000";
  const original=draftDescription(draft);
  const manual=original+"\n수동 메모: 이번 분석은 연구실 요청에 따름.";
  const lockedBasis=descriptionBasis(draft);
  const first=draftPreflight({...draft,description:manual,descriptionManualBasis:lockedBasis});
  assert.equal(first.status,"PREVIEW_READY");
  const updated={...draft,products:draft.products.map(p=>({...p,sampleUnitKrw:"95000"}))};
  const unchangedManual=manual;
  assert.equal(unchangedManual,manual);
  assert.equal(descriptionReview(updated,unchangedManual,lockedBasis).stale,true);
  const next=draftPreflight({...updated,description:unchangedManual,
    descriptionManualBasis:lockedBasis});
  assert.equal(next.status,"HOLD");
  assert.ok(next.errors.includes("DESCRIPTION_LOCKED_STALE"));
  assert.ok(next.errors.includes("DESCRIPTION_CURRENT_FACTS_MISSING"));
  const regenerated=draftDescription(updated);
  const repaired=draftPreflight({...updated,description:regenerated,descriptionManualBasis:null});
  assert.equal(repaired.status,"PREVIEW_READY");
  assert.match(regenerated,/95,000KRW/);
});

test("Manual description can be re-confirmed only if current dated Gb, quantity, and unit rate are present",()=>{
  const source=quote();
  source.reference={
    status:"PASS",accountId:"001000000000000AAA",accountName:"Synthetic School",
    contactId:"003000000000000AAA",contactName:"Synthetic PI",products:[]
  };
  const draft=fromFeishuQuote(source).draft;
  draft.name="Korea-Synthetic-Project";
  draft.products[0].samples="4";
  draft.products[0].sampleUnitKrw="160000";
  const basis=descriptionBasis(draft);
  const incomplete="2026-11-10 · 4 samples · mRNA service";
  const blocked=draftPreflight({...draft,description:incomplete,descriptionManualBasis:basis});
  assert.ok(blocked.errors.includes("DESCRIPTION_CURRENT_FACTS_MISSING"));
  const complete=draftDescription(draft)+"\nManual remark";
  const review=descriptionReview(draft,complete,basis);
  assert.equal(review.stale,false);
  assert.equal(review.complete,true);
  assert.equal(draftPreflight({...draft,description:complete,descriptionManualBasis:basis}).status,
    "PREVIEW_READY");
});

test("Actual short one-line SFDC style with mRNA service and optional Gb",()=>{
  const old=quote("6");
  old.reference={
    status:"PASS",
    opportunityName:"Korea-Example-University-mRNA-Project",
    accountId:"001000000000000AAA",accountName:"Synthetic School",
    contactId:"003000000000000AAA",contactName:"Synthetic PI",products:[]
  };
  const draft=fromFeishuQuote(old,new Date("2026-11-09T15:01:00Z")).draft;
  draft.name="Korea-Example-mRNA";
  draft.products[0].samples="12";
  draft.products[0].sampleUnitKrw="250000";
  assert.equal(draft.products[0].serviceLabel,"mRNA-Seq");
  assert.equal(draftDescription(draft),
    "1110 Quote Draft mRNA-Seq 6Gb 12 samples * 250,000KRW");
  assert.equal(draftPreflight({...draft,description:draftDescription(draft)}).status,
    "PREVIEW_READY");
  assert.doesNotMatch(draftDescription(draft),/Issued|VAT|Reference Quote|Account/);
});

test("Report without a Gb-unit process must not insert an unsupported Gb",()=>{
  const old=quote();
  old.reference={status:"PASS",opportunityName:"Korea-Test-WGS",products:[]};
  for(const p of old.process_lines){p.data_unit="M raw reads";p.data_size="90";}
  const draft=fromFeishuQuote(old,new Date("2026-11-09T15:01:00Z")).draft;
  draft.products[0].samples="4";
  draft.products[0].sampleUnitKrw="180000";
  assert.equal(draftDescription(draft),
    "1110 Quote Draft WGS 4 samples * 180,000KRW");
});

test("Issued state cannot pass preflight without actual issued evidence",()=>{
  const old=quote();
  old.reference={
    status:"PASS",opportunityName:"Korea-Test-mRNA",
    accountId:"001000000000000AAA",accountName:"School",
    contactId:"003000000000000AAA",contactName:"PI",products:[]
  };
  const draft=fromFeishuQuote(old).draft;
  draft.name="Korea-Example-Sequence";
  draft.products[0].samples="10";
  draft.products[0].sampleUnitKrw="150000";
  draft.descriptionStatus="Quote Issued";
  const preflight=draftPreflight({...draft,description:draftDescription(draft)});
  assert.equal(preflight.status,"HOLD");
  assert.ok(preflight.errors.includes("QUOTE_ISSUED_EVIDENCE_REQUIRED"));
});
