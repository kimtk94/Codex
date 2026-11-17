import test from "node:test";
import assert from "node:assert/strict";
import {historicalKrwReference,prefillHistoricalKrw}
  from "../lib/sfdc-pair-index-krw.mjs";
import {parseKrwEvidence,rankKrwPrices,candidateSelection}
  from "../lib/sfdc-2026-krw-price-preview.mjs";

const account="001000000000001",contact="003000000000001";
const account2="001000000000002",contact2="003000000000002";
const qid="QID-2026-11-17-123456";
const product="f".repeat(64);
const ids=[
 "Process-2020-04-29-00039","Process-2020-04-29-00031",
 "Process-2020-04-29-00032","Process-2020-04-29-00034",
 "Process-2020-04-29-00035"
];
const common={
 source_kind:"VERIFIED_SFDC_KRW_PROCESS_PRICE",
 source_verified:true,created_date:"2026-08-11",quote_id:qid,
 active:true,approval_status:"APPROVED",currency:"KRW",
 was_usd_converted:false,vat_basis:"VAT_EXCLUDED",account_id:account,
 contact_id:contact,product_signature:product,data_unit:"G raw data"
};
const line=(i,price,qty,gb,extra={})=>({...common,
 process_id:ids[i],process_name:[
  "Library preparation","Sequencing by data amount",
  "Analysis by sample","Data release","AliCloud storage"
 ][i],sample_quantity:qty,data_size:String(gb),
 unit_price_krw:String(price),...extra});
const source=(records,generated_at=new Date().toISOString())=>({
 version:"sfdc-2026-krw-process-prices-v1",
 source:"SFDC_AUTHENTICATED_READ_ONLY_KRW_PROCESS_LINES",
 generated_at,salesforce_write_performed:false,records
});
const productDraft=(rows,samples="2",gb="200")=>({
 processes:rows.map(x=>({processId:x.process_id,name:x.process_name})),
 productionGb:gb,samples,sampleUnitKrw:"",cloudUnitKrw:""
});
test("paid Data release with 2x process quantity is never summed as per-sample price",()=>{
 const rows=[line(0,3000000,2,200),line(1,0,2,200),
  line(2,0,2,200),line(3,150000,4,1)];
 const indexed=source(rows);
 const item=productDraft(rows);
 const p=historicalKrwReference(indexed,qid,item);
 assert.equal(p.ok,true);
 assert.equal(p.sourceSamples,2);
 assert.equal(p.sourceProductNetKrw,6600000);
 assert.equal(p.candidateSampleUnitKrw,3300000);
 assert.notEqual(p.candidateSampleUnitKrw,3150000);
 assert.equal(p.sourceGbStatus,"EXACT_SOURCE_GB_MATCH");
 assert.equal(p.pricesApprovedForNewQuote,false);
 const draft={qid,products:[item]};
 const applied=prefillHistoricalKrw(draft,indexed);
 assert.equal(applied.products[0].sampleUnitKrw,"3300000");
 assert.equal(applied.products[0].priceEvidenceStatus,"INDEX_2026_KRW_COMPARISON_ONLY");
});
test("mixed nonrelease source process quantities cannot create a false biological sample rate",()=>{
 const rows=[line(0,3000000,2,200),line(1,0,4,200),
  line(2,0,2,200),line(3,150000,4,1)];
 const result=historicalKrwReference(source(rows),qid,productDraft(rows));
 assert.equal(result.ok,false);
 assert.equal(result.code,"HISTORICAL_MIXED_PROCESS_QUANTITIES");
});
test("original source Gb must match each applicable sample process; release's data size 1 excluded",()=>{
 const rows=[line(0,3000000,2,200),line(1,0,2,200),
  line(2,0,2,200),line(3,150000,4,1)];
 assert.equal(historicalKrwReference(source(rows),qid,productDraft(rows,"2","6")).ok,false);
 const noGb=historicalKrwReference(source(rows),qid,productDraft(rows,"2",""));
 assert.equal(noGb.ok,true);
 assert.equal(noGb.sourceGbStatus,"UNVERIFIED");
});
test("fractional derived KRW per biological sample is HOLD, never rounded",()=>{
 const rows=[line(0,1000,3,6),line(1,0,3,6),
  line(2,0,3,6),line(3,500,4,1)];
 const candidate=historicalKrwReference(source(rows),qid,productDraft(rows,"3","6"));
 assert.equal(candidate.ok,false);
 assert.equal(candidate.code,"HISTORICAL_FRACTIONAL_SAMPLE_RATE_HOLD");
 const draft={qid,products:[productDraft(rows,"3","6")]};
 assert.equal(prefillHistoricalKrw(draft,source(rows)).products[0].sampleUnitKrw,"");
});
test("separately billed AliCloud stays outside process unit rate",()=>{
 const rows=[line(0,3000000,2,200),line(1,0,2,200),
  line(2,0,2,200),line(3,150000,4,1),line(4,30000,4,200)];
 const sourceRow=historicalKrwReference(source(rows),qid,productDraft(rows));
 assert.equal(sourceRow.ok,true);
 assert.equal(sourceRow.candidateCloudUnitKrw,30000);
 assert.equal(sourceRow.candidateSampleUnitKrw,3300000);
});
test("multiple source Products with indistinguishable process structures remain HOLD",()=>{
 const rows=[line(0,100000,2,6),
  line(0,200000,2,6,{product_signature:"a".repeat(64)})];
 const r=historicalKrwReference(source(rows),qid,productDraft([rows[0]],"2","6"));
 assert.equal(r.ok,false);
 assert.equal(r.code,"HISTORICAL_EXACT_PROCESS_MATCH_UNAVAILABLE");
});
test("existing manual price cannot be overwritten by a historical comparison",()=>{
 const rows=[line(0,100000,2,6)];
 const d={qid,products:[{...productDraft(rows,"2","6"),sampleUnitKrw:"999999"}]};
 assert.equal(prefillHistoricalKrw(d,source(rows)).products[0].sampleUnitKrw,"999999");
});
test("same customer with wrong depth never outranks exact-depth different customer",()=>{
 const older=line(0,100000,9,6,{quote_id:"QID-2026-09-01-111111",
   account_id:account2,contact_id:contact2});
 const newer=line(0,220000,9,10,{quote_id:"QID-2026-10-01-222222"});
 const parsed=parseKrwEvidence(JSON.stringify(source([older,newer])));
 const ranked=rankKrwPrices(parsed,{product_signature:product,process_id:ids[0],
  account_id:account,contact_id:contact,data_unit:"Gb",requested_unit:"Gb",
  data_size:"6",sample_quantity:9,production_basis:"PER_SAMPLE"});
 assert.equal(ranked.count,2);
 assert.equal(ranked.exact_count,1);
 assert.equal(ranked.candidates[0].quote_id,older.quote_id);
 assert.equal(ranked.candidates[0].suitability,"EXACT_PROCESS_AND_PRODUCTION");
 assert.equal(ranked.candidates[1].tier,"SAME_ACCOUNT_CONTACT");
 assert.equal(ranked.candidates[1].size_match,false);
 assert.equal(ranked.price_auto_apply,false);
});
test("unit mismatch and TOTAL-vs-PER_SAMPLE never claim exact match",()=>{
 const parsed=parseKrwEvidence(JSON.stringify(source([line(0,100000,9,6)])));
 const query={product_signature:product,process_id:ids[0],account_id:account,
  contact_id:contact,data_unit:"Gb",data_size:"6",sample_quantity:9,
  production_basis:"PER_SAMPLE"};
 assert.equal(rankKrwPrices(parsed,{...query,requested_unit:"M reads"}).status,
  "HOLD_REQUESTED_SOURCE_UNIT_MISMATCH");
 const total=rankKrwPrices(parsed,{...query,requested_unit:"Gb",production_basis:"TOTAL"});
 assert.equal(total.exact_count,0);
 assert.equal(total.status,"LOCAL_CONDITION_MISMATCH_CANDIDATES_ONLY");
 assert.equal(total.candidates[0].suitability,"PRODUCTION_BASIS_NOT_COMPARABLE");
});
test("same contact under different account is labeled separately and never approved",()=>{
 const sameContact=line(0,200000,9,6,{account_id:account2,
   quote_id:"QID-2026-08-01-111111"});
 const other=line(0,210000,9,6,{account_id:account2,contact_id:contact2,
   quote_id:"QID-2026-09-01-222222"});
 const parsed=parseKrwEvidence(JSON.stringify(source([other,sameContact])));
 const q={product_signature:product,process_id:ids[0],account_id:account,
  contact_id:contact,data_unit:"Gb",requested_unit:"Gb",data_size:"6",
  sample_quantity:9,production_basis:"PER_SAMPLE"};
 const ranked=rankKrwPrices(parsed,q);
 assert.equal(ranked.candidates[0].tier,"SAME_CONTACT_OTHER_ACCOUNT");
 const selected=candidateSelection({input:{service:"RNA"}},ranked.candidates[0]);
 assert.equal(selected.applied_to_new_quote,false);
 assert.equal(selected.source_production_match,"EXACT_PROCESS_AND_PRODUCTION");
});
test("leave-one-Quote-out excludes its own Price when auditing accuracy",()=>{
 const r=line(0,200000,9,6);
 const parsed=parseKrwEvidence(JSON.stringify(source([r])));
 const q={product_signature:product,process_id:ids[0],account_id:account,
 contact_id:contact,data_unit:"Gb",requested_unit:"Gb",data_size:"6",
 sample_quantity:9,production_basis:"PER_SAMPLE",exclude_quote_id:qid};
 assert.equal(rankKrwPrices(parsed,q).candidates.length,0);
});
