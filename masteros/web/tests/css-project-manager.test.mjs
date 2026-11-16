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
test("accept incomplete mail window explicitly",()=>{
  assert.equal(validateProjectManager({...payload,status:"PARTIAL_MIRROR"}).status,"PARTIAL_MIRROR");
});
