import test from "node:test";
import {inferAmpliconReference,ampliconRegionUnits,regionByCode} from "../lib/sfdc-amplicon-regions.mjs";
import assert from "node:assert/strict";
import {isGbUnit,fromFeishuQuote,calculateDraft,draftDescription,draftPreflight,descriptionBasis,descriptionReview,DESCRIPTION_TEMPLATE_VERSION,draftChanges}
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
    "1110 Quote Draft mRNA-Seq 6Gb 12 samples * 250,000KRW Samples expected soon; sample receipt, QC and PO are not confirmed.");
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
    "1110 Quote Draft WGS 4 samples * 180,000KRW Samples expected soon; sample receipt, QC and PO are not confirmed.");
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


const jungAmplicon=()=>({
  status:"PASS",qid:"QID-2026-09-04-396506",
  sfdc_record_id:"a0P000000000000AAA",
  currency:"USD_CONVERTED_ONLY",krw_rate_verified:false,
  source_mail_received_kst:"2026-11-09 17:00:23 KST",
  reference:{
    status:"PASS",
    opportunityName:"Korea-Yonsei Univ.-18-16Sv4v5-18-Archaeal16Sv4v5-WOBI-JeongJinGyeong",
    accountId:"001000000000000AAA",accountName:"Synthetic Reference Institute",
    contactId:"003000000000000AAA",contactName:"Synthetic Scientist",
    products:[]
  },
  process_lines:[
    {quotation_product_id:"QD-738646",process_id:"Process-2020-04-29-00039",
     process_name:"Library preparation",data_unit:"K tags",
     sample_quantity:"36",data_size:"100",unit_price_usd:"0",
     product_total_usd_converted:"0.98"},
    {quotation_product_id:"QD-738646",process_id:"Process-2020-04-29-00031",
     process_name:"Sequencing by data amount",data_unit:"K tags",
     sample_quantity:"36",data_size:"100",unit_price_usd:"40",
     product_total_usd_converted:"0.98"},
    {quotation_product_id:"QD-738646",process_id:"Process-2020-04-29-00032",
     process_name:"Analysis by sample",data_unit:"K tags",
     sample_quantity:"36",data_size:"100",unit_price_usd:"0",
     product_total_usd_converted:"0.98"},
    {quotation_product_id:"QD-738646",process_id:"Process-2020-04-29-00034",
     process_name:"Data release",data_unit:"G raw data",
     sample_quantity:"1",data_size:"1",unit_price_usd:"23.33",
     product_total_usd_converted:"0.98"}
  ]
});

test("Actual Jeong Jin-gyeong 18 samples x 2 regions = 36 region services",()=>{
  const source=jungAmplicon();
  const verified=inferAmpliconReference(source.reference.opportunityName,source.process_lines);
  assert.equal(verified.status,"REGION_SERVICE_UNITS_MATCHED");
  assert.equal(verified.samples,"18");
  assert.deepEqual(verified.regions.map(x=>x.label),
    ["16S V4-V5","Archaeal 16S V4-V5"]);
  assert.equal(ampliconRegionUnits(verified.samples,verified.regions),36);
  const extracted=fromFeishuQuote(source,new Date("2026-11-09T16:00:00Z"));
  assert.equal(extracted.ok,true);
  const draft=extracted.draft;
  assert.equal(draft.name,source.reference.opportunityName); // near-copy
  assert.equal(draft.account.name,"Synthetic Reference Institute");
  assert.equal(draft.contact.name,"Synthetic Scientist");
  assert.equal(draft.products.length,1);
  assert.equal(draft.products[0].samples,"18");
  assert.equal(draft.products[0].amplicon.enabled,true);
  assert.equal(draft.products[0].amplicon.regions.length,2);
  assert.equal(draft.products[0].sampleUnitKrw,""); // historical USD != KRW
  assert.deepEqual(draftChanges(draft),[]);
  const pending=calculateDraft(draft);
  assert.equal(pending.ok,false);
  assert.equal(pending.items[0].serviceQuantity,36);
  assert.equal(pending.quoteLineItems.length,2);
  assert.equal(pending.quoteLineItems[0].sampleQuantity,18);
  assert.equal(pending.quoteLineItems[1].sampleQuantity,18);
  assert.equal(pending.quoteLineItems[0].originalQuoteProductId,"QD-738646");
});

test("Region selection duplicates service, not biological sample, with editable equal price",()=>{
  const baseline=fromFeishuQuote(jungAmplicon()).draft;
  const p=baseline.products[0];
  const changed={...baseline,products:[{...p,sampleUnitKrw:"60000"}]};
  const result=calculateDraft(changed);
  assert.equal(result.ok,true);
  assert.equal(result.items[0].quantity,18);
  assert.equal(result.items[0].serviceQuantity,36);
  assert.equal(result.items[0].netKrw,2160000);
  assert.equal(result.netKrw,2160000);
  assert.equal(result.vatKrw,216000);
  assert.equal(result.grossKrw,2376000);
  assert.deepEqual(result.quoteLineItems.map(x=>x.netKrw),[1080000,1080000]);
  assert.equal(result.quoteLineItems.length,2);
  assert.equal(draftChanges(changed).length,1);
  const description=draftDescription(changed);
  assert.match(description,/^1110 Quote Draft /);
  assert.match(description,/Amplicon-Seq/);
  assert.match(description,/16S V4-V5/);
  assert.match(description,/Archaeal 16S V4-V5/);
  assert.match(description,/18 samples \* 2 regions \* 60,000KRW\/region/);
  assert.doesNotMatch(description,/36 samples/);
  assert.equal(draftPreflight({...changed,description}).status,"PREVIEW_READY");
});

test("Region-specific rates are separately calculable with 18 same specimens",()=>{
  const baseline=fromFeishuQuote(jungAmplicon(),new Date("2026-11-09T16:00:00Z")).draft;
  const p=baseline.products[0];
  const rates=p.amplicon.regions.map((r,i)=>({...r,unitKrw:i===0?"70000":"50000"}));
  const changed={...baseline,products:[{...p,
    amplicon:{...p.amplicon,regions:rates}
  }]};
  const result=calculateDraft(changed);
  assert.equal(result.ok,true);
  assert.equal(result.items[0].serviceQuantity,36);
  assert.deepEqual(result.quoteLineItems.map(x=>x.netKrw),[1260000,900000]);
  assert.equal(result.netKrw,2160000);
  const desc=draftDescription(changed);
  assert.match(desc,/16S V4-V5 70,000KRW/);
  assert.match(desc,/Archaeal 16S V4-V5 50,000KRW/);
  assert.equal(draftPreflight({...changed,description:desc}).status,"PREVIEW_READY");
});

test("Removing a Region reduces service count but never changes original sample count",()=>{
  const baseline=fromFeishuQuote(jungAmplicon()).draft;
  const p=baseline.products[0];
  const edited={...p,sampleUnitKrw:"60000",
    amplicon:{...p.amplicon,regions:p.amplicon.regions.slice(0,1)}};
  const copy={...baseline,products:[edited]};
  const calc=calculateDraft(copy);
  assert.equal(calc.items[0].quantity,18);
  assert.equal(calc.items[0].regionCount,1);
  assert.equal(calc.items[0].serviceQuantity,18);
  assert.equal(calc.netKrw,1080000);
  assert.equal(calc.quoteLineItems.length,1);
  assert.ok(draftChanges(copy).some(x=>x.field.endsWith(".regions")));
  const extra=regionByCode("ITS1");
  assert.equal(extra.label,"ITS1");
  assert.equal(ampliconRegionUnits("18",[...edited.amplicon.regions,extra]),36);
});

test("Different sample counts across Regions must not be merged as same specimens",()=>{
  const name="Korea-Synthetic-18-16Sv4v5-12-Archaeal16Sv4v5";
  const data=inferAmpliconReference(name,[{data_unit:"K tags",sample_quantity:"30"}]);
  assert.equal(data.enabled,false);
  assert.equal(data.status,"MIXED_SAMPLE_COUNTS");
});
