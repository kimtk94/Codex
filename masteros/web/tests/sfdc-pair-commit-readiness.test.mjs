import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {pairWebRequest} from "../lib/sfdc-pair-workspace.mjs";
const ids={opportunity:"006000000000000AAA",quote:"a0P000000000000AAA"};
const form={sourceOpportunityId:ids.opportunity,sourceQuoteId:ids.quote,
  newOpportunityName:"Korea-Demo-Pair",samples:12,dataSizeGb:6,
  productUnitOverrideKrw:"",cloudUnitOverrideKrw:""};

test("one-action preflight is read-only and a save is still prohibited",()=>{
  const req=pairWebRequest(form,"CHECK_SAVE_READINESS");
  assert.equal(req.ok,true);
  assert.equal(req.body.runMode,"CHECK");
  assert.equal(req.body.mode,"CHECK_SAVE_READINESS");
  for(const mode of ["SAVE","CREATE","CREATE_PAIR","COMMIT"]){
    assert.equal(pairWebRequest(form,mode).ok,false);
  }
});
test("local UI renders actionable Pack and final Quote readiness, no fake save",()=>{
  const page=readFileSync(new URL("../app/sales/commands/pair/advanced/page.jsx",import.meta.url),"utf8");
  const route=readFileSync(new URL("../app/api/sfdc/pair-check-local/route.js",import.meta.url),"utf8");
  const worker=readFileSync(new URL("../scripts/sfdc_pair_web_preview.py",import.meta.url),"utf8");
  assert.match(page,/data-testid="pair-save-readiness-check"/);
  assert.match(page,/data-testid="pair-create-readiness"/);
  assert.match(page,/새 Quote의 공정·단가·Pack 저장/);
  assert.match(page,/result\.pack\.process_lines\.map/);
  assert.match(page,/저장하지 않습니다/);
  assert.match(route,/"CHECK_SAVE_READINESS"/);
  assert.match(worker,/QUOTE_PACK_RATE_CLOUD_WRITE_AND_READBACK_NOT_VERIFIED/);
  assert.match(worker,/"salesforce_write": False, "save_permitted": False/);
});
