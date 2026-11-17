import test from "node:test";
import assert from "node:assert/strict";
import {
 createLocalProcessProduct,addLocalProcessProduct,editLocalProcessLine,
 removeLocalProcessProduct,setLocalProductQuantityReviewed,
 reviewLocalProcessDraft,exportLocalOppoQuoteReview
} from "../lib/sfdc-local-process-draft.mjs";

const qid="QID-2026-11-17-123456",product="e".repeat(64),p2="f".repeat(64);
const names=[
 "Process-2020-01-01-00001","Process-2020-01-01-00002",
 "Process-2020-01-01-00003"
];
const account="001000000000001",contact="003000000000001";
const identity={ok:true,account_id:account,contact_id:contact};
const intake=(samples="2",production="6",basis="PER_SAMPLE",unit="Gb")=>({
 input:{samples,production,basis,unit,service:"RNA"},
 suggested:{opportunityName:"Korea-Synthetic-RNA",quotationName:"Korea-Synthetic-RNA",closeDateKst:"2026-12-17"}
});
function group(overrides={}){
 return {key:qid+"|"+product,quote_id:qid,product_signature:product,
  product_name:"Synthetic RNA",created_date:"2026-11-17",
  review_status:"HOLD",hold_reason:"HISTORICAL_FRACTIONAL_SAMPLE_RATE_HOLD",
  sample_rate_auto_applicable:false,fee_included:false,crm_writes:0,
  process_net_krw:"6900",account_id:account,contact_id:contact,
  lines:[
   {process_id:names[0],process_name:"Library preparation",
    process_quantity:2,unit_price_krw:"3000",process_net_krw:"6000",
    data_unit:"Gb",data_size:"6"},
   {process_id:names[1],process_name:"Data release",
    process_quantity:4,unit_price_krw:"150",process_net_krw:"600",
    data_unit:"Gb",data_size:"1"},
   {process_id:names[2],process_name:"AliCloud storage",
    process_quantity:1,unit_price_krw:"300",process_net_krw:"300",
    data_unit:"Gb",data_size:"6"}],...overrides};
}
function copied(){const result=createLocalProcessProduct(group());assert.equal(result.ok,true);return [result.product]}
test("explicit source Product copy preserves ORIGINAL process prices and counts separately",()=>{
 const result=createLocalProcessProduct(group());
 assert.equal(result.ok,true);
 assert.equal(result.product.lines.length,3);
 assert.equal(result.product.lines[0].original_process_quantity,"2");
 assert.equal(result.product.lines[0].new_process_quantity,"2");
 assert.equal(result.product.lines[0].original_unit_price_krw,"3000");
 assert.equal(result.product.lines[0].proposed_unit_price_krw,"3000");
 assert.equal(result.new_price_approved,false);
 assert.equal(result.crm_writes,0);
 assert.equal(result.product.quantity_depth_reviewed,false);
});
test("adding up to eight Products requires explicit click, duplicate source remains HOLD",()=>{
 const base=copied();
 const duplicate=addLocalProcessProduct(base,group());
 assert.equal(duplicate.ok,false);
 assert.equal(duplicate.code,"HOLD_PRODUCT_ALREADY_IN_DRAFT");
 assert.equal(duplicate.products.length,1);
 const next=addLocalProcessProduct(base,group({product_signature:p2}));
 assert.equal(next.ok,true);
 assert.equal(next.products.length,2);
 assert.equal(removeLocalProcessProduct(next.products,qid,p2).length,1);
});
test("new Quote with unchanged source quantity is still HOLD until operator reviews",()=>{
 const d=reviewLocalProcessDraft(copied(),intake(),identity);
 assert.equal(d.status,"HOLD_NEW_PROCESS_QUANTITY_CONFIRMATION");
 assert.equal(d.process_net_krw,"6600");
 assert.equal(d.cloud_net_krw,"300");
 assert.equal(d.net_krw,"6900");
 assert.equal(d.vat_krw,"690");
 assert.equal(d.gross_krw,"7590");
 assert.equal(d.source_product_reference_only,true);
 assert.equal(d.actual_sf_product_ids_verified,false);
 assert.equal(d.pack_verified,false);
 assert.equal(d.salesforce_save_allowed,false);
 assert.equal(d.price_approved,false);
});
test("operator can change process quantities and rates without changing source snapshot",()=>{
 const source=copied();
 let target=editLocalProcessLine(source,qid,product,names[0],
   {new_process_quantity:"4",proposed_unit_price_krw:"3200"});
 target=editLocalProcessLine(target,qid,product,names[1],{new_process_quantity:"8"});
 target=editLocalProcessLine(target,qid,product,names[2],{new_process_quantity:"2"});
 assert.equal(source[0].lines[0].new_process_quantity,"2");
 assert.equal(source[0].lines[0].original_unit_price_krw,"3000");
 assert.equal(target[0].lines[0].original_unit_price_krw,"3000");
 assert.equal(target[0].lines[0].proposed_unit_price_krw,"3200");
 assert.equal(reviewLocalProcessDraft(target,intake("4"),identity).status,"HOLD_NEW_PROCESS_QUANTITY_CONFIRMATION");
 target=setLocalProductQuantityReviewed(target,qid,product,true);
 const sum=reviewLocalProcessDraft(target,intake("4"),identity);
 assert.equal(sum.status,"LOCAL_QUOTE_DRAFT_REVIEW_REQUIRED");
 assert.equal(sum.process_net_krw,"14000");
 assert.equal(sum.cloud_net_krw,"600");
 assert.equal(sum.net_krw,"14600");
 assert.equal(sum.vat_krw,"1460");
 assert.equal(sum.gross_krw,"16060");
 assert.equal(sum.products[0].lines[0].edited_from_source,true);
 assert.equal(sum.price_approved,false);
 assert.equal(sum.salesforce_save_allowed,false);
});
test("changing a new Quote price invalidates prior operator quantity-depth confirmation",()=>{
 let target=setLocalProductQuantityReviewed(copied(),qid,product,true);
 assert.equal(target[0].quantity_depth_reviewed,true);
 target=editLocalProcessLine(target,qid,product,names[0],{proposed_unit_price_krw:"2800"});
 assert.equal(target[0].quantity_depth_reviewed,false);
 assert.equal(reviewLocalProcessDraft(target,intake(),identity).status,
   "HOLD_NEW_PROCESS_QUANTITY_CONFIRMATION");
});
test("a user can uncheck a process and the new Quote total excludes it, preserving source",()=>{
 let target=editLocalProcessLine(copied(),qid,product,names[1],{include:false});
 target=setLocalProductQuantityReviewed(target,qid,product,true);
 const summary=reviewLocalProcessDraft(target,intake(),identity);
 assert.equal(summary.selected_process_count,2);
 assert.equal(summary.process_net_krw,"6000");
 assert.equal(summary.cloud_net_krw,"300");
 assert.equal(summary.products[0].lines[1].excluded_from_new_quote,true);
 assert.equal(summary.products[0].lines[1].original_unit_price_krw,"150");
 assert.equal(summary.status,"LOCAL_QUOTE_DRAFT_REVIEW_REQUIRED");
});
test("source quantity different from new sample count must never auto-scale",()=>{
 let draft=setLocalProductQuantityReviewed(copied(),qid,product,true);
 const summary=reviewLocalProcessDraft(draft,intake("48"),identity);
 assert.equal(summary.products[0].lines[0].new_process_quantity,"2");
 assert.equal(summary.status,"HOLD_PROCESS_QTY_DIFFERS_FROM_NEW_SAMPLES");
});
test("TOTAL production or changed Gb fails source equivalence and asks to review",()=>{
 const draft=setLocalProductQuantityReviewed(copied(),qid,product,true);
 assert.equal(reviewLocalProcessDraft(draft,intake("2","6","TOTAL"),identity).status,
   "HOLD_PRODUCTION_UNIT_DEPTH_RECHECK");
 assert.equal(reviewLocalProcessDraft(draft,intake("2","8"),identity).status,
   "HOLD_PRODUCTION_UNIT_DEPTH_RECHECK");
 assert.equal(reviewLocalProcessDraft(draft,intake("2","6","PER_SAMPLE","M reads"),identity).status,
   "HOLD_PRODUCTION_UNIT_DEPTH_RECHECK");
});
test("referenced Quote from different customer is comparison-only, never adopts their IDs",()=>{
 const other={ok:true,account_id:"001000000000002",contact_id:"003000000000002"};
 const draft=setLocalProductQuantityReviewed(copied(),qid,product,true);
 const r=reviewLocalProcessDraft(draft,intake(),other);
 assert.equal(r.status,"HOLD_SOURCE_CUSTOMER_DIFFERENT");
 assert.equal(r.products[0].compared_to_selected_customer,"OTHER_SOURCE_CUSTOMER_RECHECK_REQUIRED");
 const exported=exportLocalOppoQuoteReview(draft,intake(),other);
 assert.equal(exported.customer_reference.account_id,other.account_id);
 assert.equal(exported.quote_products[0].source_account_id,account);
 assert.equal(exported.sfdc_quote_saved,false);
});
test("invalid zero quantity, negative/non-precision price and unsafe decimals all HOLD",()=>{
 for(const bad of ["0","-100","1.00001","nan","100,000","1000000000000000"]){
  const target=editLocalProcessLine(copied(),qid,product,names[0],
    {proposed_unit_price_krw:bad});
  assert.equal(reviewLocalProcessDraft(target,intake(),identity).status,
    "HOLD_INVALID_PROCESS_QTY_OR_RATE",bad);
 }
 const zeroQty=editLocalProcessLine(copied(),qid,product,names[0],{new_process_quantity:"0"});
 assert.equal(reviewLocalProcessDraft(zeroQty,intake(),identity).status,
   "HOLD_INVALID_PROCESS_QTY_OR_RATE");
});
test("precise 4-decimal KRW yields 5-decimal VAT, no rounding or fabricated integer prices",()=>{
 const tiny=group({lines:[
  {process_id:names[0],process_name:"Library preparation",
   process_quantity:1,unit_price_krw:"0.0001",process_net_krw:"0.0001",
   data_unit:"Gb",data_size:"6"}],process_net_krw:"0.0001"});
 let draft=createLocalProcessProduct(tiny).product;
 draft={...draft,quantity_depth_reviewed:true};
 const r=reviewLocalProcessDraft([draft],intake("1"),identity);
 assert.equal(r.net_krw,"0.0001");
 assert.equal(r.vat_krw,"0.00001");
 assert.equal(r.gross_krw,"0.00011");
 assert.equal(r.status,"HOLD_FRACTIONAL_KRW_TOTAL");
});
test("multiple Products aggregate safely and remain unapproved even if all checked",()=>{
 const first=setLocalProductQuantityReviewed(copied(),qid,product,true);
 const second=createLocalProcessProduct(group({quote_id:"QID-2026-11-01-987654",
   product_signature:p2,account_id:account,contact_id:contact})).product;
 const selected={...second,quantity_depth_reviewed:true};
 const r=reviewLocalProcessDraft([...first,selected],intake(),identity);
 assert.equal(r.product_count,2);
 assert.equal(r.net_krw,"13800");
 assert.equal(r.vat_krw,"1380");
 assert.equal(r.status,"LOCAL_QUOTE_DRAFT_REVIEW_REQUIRED");
 assert.equal(r.crm_writes,0);
});
test("duplicate Process in source or unverified Source Product is rejected fail-closed",()=>{
 const rows=group().lines;
 assert.equal(createLocalProcessProduct(group({lines:[rows[0],rows[0]]})).ok,false);
 assert.equal(createLocalProcessProduct(group({fee_included:true})).ok,false);
 assert.equal(createLocalProcessProduct(group({sample_rate_auto_applicable:true})).ok,false);
 assert.equal(createLocalProcessProduct(group({review_status:"UNVERIFIED"})).ok,false);
 assert.equal(reviewLocalProcessDraft([],intake(),identity).salesforce_save_allowed,false);
});
test("JSON review never represents a Salesforce creation request or price approval",()=>{
 const local=exportLocalOppoQuoteReview(copied(),intake(),identity);
 assert.equal(local.status,"HOLD_NEW_PROCESS_QUANTITY_CONFIRMATION");
 assert.equal(local.version,"sfdc-local-original-process-product-draft-v1");
 assert.equal(local.opportunity_name,local.quotation_name);
 assert.equal(local.close_date_kst,"2026-12-17");
 assert.equal(local.quote_fee_included,false);
 assert.equal(local.customer_reference.live_write_identity_verified,false);
 assert.equal(local.price_approved,false);
 assert.equal(local.salesforce_save_allowed,false);
 assert.equal(local.sfdc_quote_saved,false);
 assert.equal(local.crm_writes,0);
});
