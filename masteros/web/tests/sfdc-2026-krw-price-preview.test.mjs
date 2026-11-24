import test from "node:test";
import assert from "node:assert/strict";
import {canonicalPriceUnit,verifyPriceLine,parseKrwEvidence,rankKrwPrices,candidateSelection,summarizeKrwProductPrices} from "../lib/sfdc-2026-krw-price-preview.mjs";
const aid="001000000000AAA",otherAid="001000000000AAB",cid="003000000000AAA",otherCid="003000000000AAB";
const product="e".repeat(64),process="Process-2026-01-01-00001";
const base={source_kind:"VERIFIED_SFDC_KRW_PROCESS_PRICE",source_verified:true,
 created_date:"2026-10-01",quote_id:"QID-2026-10-01-123456",active:true,
 approval_status:"APPROVED",currency:"KRW",was_usd_converted:false,
 vat_basis:"VAT_EXCLUDED",account_id:aid,contact_id:cid,
 process_id:process,product_signature:product,unit_price_krw:"300000",
 data_unit:"G raw data",data_size:"6",sample_quantity:20,process_name:"Sequencing by data amount"};
const when=Date.parse("2026-11-16T10:00:00Z");
const evidence=(records=[base])=>JSON.stringify({version:"sfdc-2026-krw-process-prices-v1",
 source:"SFDC_AUTHENTICATED_READ_ONLY_KRW_PROCESS_LINES",generated_at:"2026-11-16T09:00:00Z",
 salesforce_write_performed:false,records});
test("2026 native KRW only, 2025/converted USD/false approval excluded",()=>{
 const rows=[base,{...base,currency:"USD"},{...base,was_usd_converted:true},
  {...base,created_date:"2025-12-01"},{...base,approval_status:"PENDING"},
  {...base,contact_id:"CP202604123456"}];
 const x=parseKrwEvidence(evidence(rows),when);
 assert.equal(x.records.length,1);assert.equal(x.excluded_count,5);
 assert.equal(x.rejected.NOT_NATIVE_KRW,2);
 assert.equal(x.rejected.OUTSIDE_2026,1);
 assert.equal(x.rejected.NOT_APPROVED_ACTIVE,1);
 assert.equal(x.rejected.CONTACT_003_UNVERIFIED,1);
});
test("read-only same contact > same account > other account and no rate application",()=>{
 const rows=[{...base,account_id:otherAid,contact_id:otherCid,quote_id:"QID-2026-09-01-111111"},
 {...base,contact_id:otherCid,quote_id:"QID-2026-09-02-222222"},
 base];
 const src=parseKrwEvidence(evidence(rows),when);
 const found=rankKrwPrices(src,{product_signature:product,process_id:process,
  account_id:aid,contact_id:cid,data_unit:"Gb",data_size:"6",sample_quantity:20,production_basis:"PER_SAMPLE"});
 assert.deepEqual(found.candidates.map(x=>x.tier),["SAME_ACCOUNT_CONTACT","SAME_ACCOUNT_OTHER_CONTACT","OTHER_CUSTOMER_SAME_PRODUCT_PROCESS"]);
 assert.equal(found.candidates[0].unit_price_krw,"300000");
 assert.equal(found.candidates[0].comparison_only,true);
 assert.equal(found.price_auto_apply,false);
 assert.equal(found.crm_writes,0);
 const chosen=candidateSelection({input:{service:"RNA"}},found.candidates[0]);
 assert.equal(chosen.applied_to_new_quote,false);
 assert.equal(chosen.state,"COMPARISON_ONLY_REQUIRES_AUTHENTICATED_PRICE_RECHECK");
});
test("different product/process/units are not linked, no currency conversion",()=>{
 const src=parseKrwEvidence(evidence(),when);
 for(const request of [{product_signature:"b".repeat(64),process_id:process,data_unit:"Gb"},
  {product_signature:product,process_id:"Process-2026-01-01-99999",data_unit:"Gb"},
  {product_signature:product,process_id:process,data_unit:"M raw reads"}]){
  assert.equal(rankKrwPrices(src,{...request,sample_quantity:20,production_basis:"PER_SAMPLE",data_size:"6"}).candidates.length,0);
 }
 assert.equal(canonicalPriceUnit("M reads"),"M raw reads");
 assert.equal(canonicalPriceUnit("G raw data"),"Gb");
});
test("all user-provided evidence remains unverified even if source flag present",()=>{
 const src=parseKrwEvidence(evidence(),when);
 assert.equal(src.source_authenticated_in_browser,false);
 assert.equal(src.prices_approved_for_new_quote,false);
 const found=rankKrwPrices(src,{product_signature:product,process_id:process,data_unit:"Gb",data_size:"6",sample_quantity:20,production_basis:"PER_SAMPLE"});
 assert.equal(found.candidates.length,1);
 assert.equal(found.candidates[0].source_recheck_required,true);
});
test("reject bad schema, future/stale input and invalid price figures",()=>{
 assert.throws(()=>parseKrwEvidence("notjson",when),/INVALID_JSON/);
 assert.throws(()=>parseKrwEvidence(JSON.stringify({records:[]}),when),/INVALID_EVIDENCE_SCHEMA/);
 assert.throws(()=>parseKrwEvidence(evidence(),Date.parse("2026-11-18T10:00:00Z")),/STALE_OR_FUTURE_LOCAL_EVIDENCE/);
 assert.equal(verifyPriceLine({...base,unit_price_krw:"12USD"}),"KRW_UNIT_PRICE_MISSING");
 assert.equal(verifyPriceLine({...base,unit_price_krw:"0"}),"PASS");
 assert.equal(verifyPriceLine({...base,vat_basis:"VAT_INCLUDED"}),"VAT_BASIS_UNVERIFIED");
});

test("2026 zero-data-size per-sample QC lines preserve NA rather than invent Gb",()=>{
 const row={...base,data_unit:"NA",data_size:"",process_name:"Extraction and sample QC",unit_price_krw:"35000"};
 assert.equal(verifyPriceLine(row),"PASS");
 const src=parseKrwEvidence(evidence([row]),when);
 const q={product_signature:product,process_id:process,data_unit:"NA",data_size:"",sample_quantity:20,production_basis:"PER_SAMPLE"};
 const found=rankKrwPrices(src,q);
 assert.equal(found.candidates.length,1);
 assert.equal(found.candidates[0].size_match,false);
 assert.equal(found.candidates[0].data_size,"");
 assert.equal(found.candidates[0].comparison_only,true);
 assert.equal(verifyPriceLine({...row,data_unit:"Gb"}),"DATA_SIZE_MISSING");
});

test("product/process KRW portfolio separates exact unit and data size conditions",()=>{
 const rows=[base,
  {...base,quote_id:"QID-2026-10-02-123457",account_id:otherAid,contact_id:otherCid,unit_price_krw:"350000"},
  {...base,quote_id:"QID-2026-10-03-123458",process_id:"Process-2026-01-01-00002",data_unit:"NA",data_size:"",unit_price_krw:"0"}];
 const src=parseKrwEvidence(evidence(rows),when);
 const portfolio=summarizeKrwProductPrices(src);
 assert.equal(portfolio.quote_count,3);
 assert.equal(portfolio.product_count,1);
 assert.equal(portfolio.process_line_count,3);
 assert.equal(portfolio.group_count,2);
 const gb=portfolio.groups.find(g=>g.data_unit==="Gb");
 assert.equal(gb.quote_count,2);
 assert.equal(gb.account_count,2);
 assert.equal(gb.unit_price_min_krw,300000);
 assert.equal(gb.unit_price_median_krw,325000);
 assert.equal(gb.unit_price_max_krw,350000);
 assert.equal(gb.sample_min,20);
 const na=portfolio.groups.find(g=>g.data_unit==="NA");
 assert.equal(na.unit_price_min_krw,0);
 assert.equal(na.data_size,"");
 assert.equal(portfolio.price_auto_apply,false);
 assert.equal(portfolio.crm_writes,0);
 const empty=summarizeKrwProductPrices(null);
 assert.equal(empty.group_count,0);
 assert.equal(empty.process_line_count,0);
});
