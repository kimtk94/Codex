import test from "node:test";
import assert from "node:assert/strict";
import {validateProjectManager} from "../lib/css-project-manager.mjs";
const row={
  project_id:"X209SC26011111-Z01",quote_name:"",
  quote_match_state:"QUOTE_UNLINKED",bucket:"ACTIVE",
  receipt_state:"결제 증빙 미확인"
};
const payload={
  status:"PASS_MIRROR_ONLY",original_feishu_verified:false,
  payment_receipt_verified:false,counts:{total:1,active:1,payment:0,archive:0},
  project_rows:[row]
};
test("read-only project snapshot and no claimed original verification",()=>{
  assert.equal(validateProjectManager(payload).project_rows.length,1);
});
test("reject false paid status and mismatched counts",()=>{
  for(const patch of [
    {project_rows:[{...row,receipt_state:"PAID"}]},
    {counts:{...payload.counts,archive:1}},
    {original_feishu_verified:true},
    {project_rows:[row,row]},
    {project_rows:[{...row,quote_name:"fabricated"}]}
  ])assert.throws(()=>validateProjectManager({...payload,...patch}));
});
test("stale Quote export remains queryable but cannot claim source health",()=>{
  const stale={...payload,status:"STALE_QUOTE_HEADER",
    quote_header_status:"STALE_OR_MISSING_HEADER",
    quote_header_age_hours:500,quote_header_freshness_limit_hours:72};
  assert.equal(validateProjectManager(stale).status,"STALE_QUOTE_HEADER");
  assert.throws(()=>validateProjectManager({...stale,quote_header_status:"CURRENT_HEADER_MIRROR"}));
});
test("accept incomplete mail window explicitly",()=>{
  assert.equal(validateProjectManager({...payload,status:"PARTIAL_MIRROR"}).status,"PARTIAL_MIRROR");
});

test("candidate remains separate from verified Quote identity",()=>{
  assert.throws(()=>validateProjectManager({
    ...payload,
    project_rows:[{...row,quote_name:"unsafe",quote_candidate_name:"unverified",
      quote_candidate_state:"UNVERIFIED_APPROVAL_DEDUP",quote_candidate_count:1}]
  }));
  const candidate={...row,quote_candidate_name:"unverified",
    quote_candidate_state:"UNVERIFIED_APPROVAL_DEDUP",quote_candidate_count:1};
  assert.equal(validateProjectManager({...payload,project_rows:[candidate]}).project_rows[0].quote_name,"");
});
test("previous CSS completion cannot falsely move current project to Payment",()=>{
  assert.throws(()=>validateProjectManager({
    ...payload,counts:{total:1,active:0,payment:1,archive:0},
    project_rows:[{...row,bucket:"PAYMENT",legacy_completion_conflict:true}]
  }));
});

test("historical CSS 100 percent cannot render as current completed",()=>{
  assert.throws(()=>validateProjectManager({
    ...payload,
    project_rows:[{...row,progress_percent:100,progress_conflict:true,
      progress_display_percent:100}]
  }),/FALSE_CURRENT_COMPLETION_PROGRESS/);
  const correct={...row,progress_percent:100,progress_conflict:true,
    progress_display_percent:null};
  assert.equal(validateProjectManager({...payload,project_rows:[correct]}).project_rows[0].bucket,"ACTIVE");
});
test("invoice evidence may exist but receipt remains unverified",()=>{
  const withInvoice={...row,invoice_evidence_state:"EXACT_X_INVOICE_MIRROR",
    invoice_notice_count:2,invoice_exact_x_count:1};
  assert.equal(validateProjectManager({...payload,project_rows:[withInvoice]}).project_rows[0].receipt_state,"결제 증빙 미확인");
  assert.throws(()=>validateProjectManager({...payload,project_rows:[
    {...withInvoice,receipt_state:"PAID"}]}));
});
