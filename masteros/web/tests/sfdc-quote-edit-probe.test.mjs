import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {pairWebRequest} from "../lib/sfdc-pair-workspace.mjs";

const form={
  sourceOpportunityId:"006000000000000AAA",sourceQuoteId:"a0P000000000000AAA",
  newOpportunityName:"New Opportunity with Source Price",
  samples:12,dataSizeGb:5,productUnitOverrideKrw:"",cloudUnitOverrideKrw:""
};

test("source Price/Cloud editor probe is read-only and cannot start a save",()=>{
  const req=pairWebRequest(form,"CHECK_WRITE_CONTROLS");
  assert.equal(req.ok,true);
  assert.equal(req.body.mode,"CHECK_WRITE_CONTROLS");
  assert.equal(req.body.runMode,"CHECK");
  for(const mode of ["SAVE","COMMIT","CREATE","CREATE_PAIR"]){
    assert.equal(pairWebRequest(form,mode).ok,false);
  }
});

test("UI shows source controls and reason final new Quote is still HOLD",()=>{
  const ui=readFileSync(new URL("../app/sales/commands/pair/advanced/page.jsx",import.meta.url),"utf8");
  const route=readFileSync(new URL("../app/api/sfdc/pair-check-local/route.js",import.meta.url),"utf8");
  const worker=readFileSync(new URL("../scripts/sfdc_pair_web_preview.py",import.meta.url),"utf8");
  const source=readFileSync(new URL("../scripts/sfdc_quote_edit_probe.py",import.meta.url),"utf8");
  assert.match(ui,/data-testid="source-quote-edit-probe"/);
  assert.match(ui,/data-testid="source-edit-probe-details"/);
  assert.match(ui,/신규 Quote 생성이나 저장 성공을 의미하지 않습니다/);
  assert.match(route,/CHECK_WRITE_CONTROLS/);
  assert.match(worker,/SOURCE_EDIT_PROBE_PASS_NEW_QUOTE_WRITER_NOT_VERIFIED/);
  assert.match(source,/control\.press\("ControlOrMeta\+A"\)/);
  assert.match(source,/control\.press\("Backspace"\)/);
  assert.match(source,/control\.type\(str\(before\),delay=25\)/);
  assert.doesNotMatch(source,/control\.fill\(str\(before\)\)/);
  assert.match(source,/SOURCE_PRICE_CHANGED_AFTER_CANCEL/);
});
