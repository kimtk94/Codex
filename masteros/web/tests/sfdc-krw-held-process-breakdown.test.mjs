import test from "node:test";
import assert from "node:assert/strict";
import {parseKrwEvidence} from "../lib/sfdc-2026-krw-price-preview.mjs";
import {listKrwOriginalProcessGroups} from "../lib/sfdc-pair-index-krw.mjs";

const qid="QID-2026-11-17-111111",product="f".repeat(64);
const base={
 source_kind:"VERIFIED_SFDC_KRW_PROCESS_PRICE",source_verified:true,
 created_date:"2026-11-10",quote_id:qid,active:true,
 approval_status:"APPROVED",currency:"KRW",was_usd_converted:false,
 vat_basis:"VAT_EXCLUDED",account_id:"001000000000001",
 contact_id:"003000000000001",product_signature:product,
 product_name:"Synthetic product",data_unit:"G raw data"
};
const code=["Process-2020-01-01-00001","Process-2020-01-01-00002",
 "Process-2020-01-01-00003","Process-2020-01-01-00004"];
function line(i,price,qty,size,changes={}){
 return {...base,process_id:code[i],unit_price_krw:String(price),
 sample_quantity:qty,data_size:String(size),
 process_name:["Library preparation","Sequencing by data amount",
   "Data release","AliCloud storage"][i],...changes};
}
function parsed(rows){
 const text=JSON.stringify({version:"sfdc-2026-krw-process-prices-v1",
  source:"SFDC_AUTHENTICATED_READ_ONLY_KRW_PROCESS_LINES",
  generated_at:new Date().toISOString(),salesforce_write_performed:false,
  records:rows});
 return parseKrwEvidence(text);
}
const get=rows=>listKrwOriginalProcessGroups(parsed(rows));

test("HOLD fractional biological sample rate still displays every original Process rate and qty",()=>{
 const rows=[line(0,"1000",3,6),line(1,"0",3,6),
   line(2,"500",4,1)];
 const x=get(rows);
 assert.equal(x.status,"LOCAL_ORIGINAL_PROCESS_DISPLAY_ONLY");
 assert.equal(x.total,1);
 assert.equal(x.heldCount,1);
 const g=x.groups[0];
 assert.equal(g.review_status,"HOLD");
 assert.equal(g.hold_reason,"HISTORICAL_FRACTIONAL_SAMPLE_RATE_HOLD");
 assert.equal(g.lines.length,3);
 assert.equal(g.lines[2].process_quantity,4);
 assert.equal(g.lines[2].unit_price_krw,"500");
 assert.equal(g.lines[2].process_net_krw,"2000");
 assert.equal(g.process_net_krw,"5000");
 assert.equal(g.historical_sample_rate_krw,null);
 assert.equal(g.sample_rate_auto_applicable,false);
 assert.equal(g.fee_included,false);
 assert.equal(x.price_auto_apply,false);
 assert.equal(x.crm_writes,0);
});
test("valid historical sample rate is still COMPARISON_ONLY and never auto-applies",()=>{
 const x=get([line(0,1000,2,6),line(1,0,2,6),line(2,500,4,1)]);
 assert.equal(x.comparableCount,1);
 assert.equal(x.heldCount,0);
 assert.equal(x.groups[0].historical_sample_rate_krw,"2000");
 assert.equal(x.groups[0].sample_rate_auto_applicable,false);
});
test("mixed nonrelease process quantities HOLD but reveal source rows",()=>{
 const x=get([line(0,1000,2,6),line(1,500,4,6),line(2,0,2,1)]);
 assert.equal(x.heldCount,1);
 assert.equal(x.groups[0].hold_reason,"HISTORICAL_MIXED_PROCESS_QUANTITIES");
 assert.equal(x.groups[0].process_net_krw,"4000");
 assert.equal(x.groups[0].lines.length,3);
});
test("exactly separate two Products under the same QID rather than mixing rows",()=>{
 const b="a".repeat(64);
 const x=get([line(0,1000,2,6),line(2,0,2,1),
   line(0,3000,3,6,{product_signature:b,product_name:"Other synthetic Product"}),
   line(2,500,4,1,{product_signature:b,product_name:"Other synthetic Product"})]);
 assert.equal(x.total,2);
 assert.equal(x.groups.length,2);
 assert.equal(new Set(x.groups.map(g=>g.product_signature)).size,2);
 assert.equal(x.groups.reduce((sum,g)=>sum+Number(g.process_net_krw),0),7000);
});
test("duplicate Process IDs within a Product remain review HOLD with all rows visible",()=>{
 const r=line(0,1000,2,6);
 const x=get([r,{...r,unit_price_krw:"2000"}]);
 assert.equal(x.total,1);
 assert.equal(x.groups[0].hold_reason,"HISTORICAL_PRODUCT_NOT_IDENTIFIED");
 assert.equal(x.groups[0].lines.length,2);
 assert.equal(x.groups[0].process_net_krw,"6000");
});
test("Cloud process amount is preserved separately and original Quote Fee is never added",()=>{
 const x=get([line(0,3000,2,6),line(2,150,4,1),line(3,30000,2,6)]);
 assert.equal(x.groups[0].process_net_krw,"66600");
 assert.equal(x.groups[0].lines.filter(r=>r.cloud).length,1);
 assert.equal(x.groups[0].lines.find(r=>r.cloud).process_net_krw,"60000");
 assert.equal(x.groups[0].fee_included,false);
});
test("four decimal places remain exact without premature rounding",()=>{
 const x=get([line(0,"0.0001",3,6),line(2,"0.0001",1,1)]);
 assert.equal(x.groups[0].lines[0].process_net_krw,"0.0003");
 assert.equal(x.groups[0].process_net_krw,"0.0004");
 assert.equal(x.groups[0].review_status,"HOLD");
});
test("invalid source provenance cannot reveal unverified prices",()=>{
 const x=parsed([line(0,1000,2,6)]);
 assert.equal(listKrwOriginalProcessGroups({...x,status:"UNVERIFIED"}).groups.length,0);
 assert.equal(listKrwOriginalProcessGroups({...x,source:"USD_FROM_REPORT"}).status,
   "HOLD_VALIDATED_SOURCE_REQUIRED");
 assert.equal(listKrwOriginalProcessGroups({...x,prices_approved_for_new_quote:true}).total,0);
 assert.equal(listKrwOriginalProcessGroups(null).crm_writes,0);
});
