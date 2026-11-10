import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

const page=readFileSync(new URL("../app/sales/mail/page.jsx",import.meta.url),"utf8");
const css=readFileSync(new URL("../app/sales/mail/page.module.css",import.meta.url),"utf8");

test("selecting a mail opens a visible modal, not a hidden section under the table",()=>{
  assert.match(page,/role="dialog"/);
  assert.match(page,/aria-modal="true"/);
  assert.match(page,/data-testid="mail-review-dialog"/);
  assert.match(page,/setSelected\(item\)/);
  assert.match(css,/\.modalBackdrop\{position:fixed;inset:0;z-index:1400/);
  assert.match(css,/\.modal\{[^\n]*max-height:min\(90dvh,850px\)/);
});
test("review action requires explicit second confirmation without a blocking native confirm",()=>{
  assert.match(page,/setConfirming\(\{payload,caption\}\)/);
  assert.match(page,/data-testid="confirm-review-action"/);
  assert.match(page,/onClick=\{confirmWrite\}/);
  assert.match(page,/disabled=\{busy\|\|loading\|\|data\?\.mailSourceStatus!=="FRESH"/);
  assert.doesNotMatch(page,/window\.confirm\(/);
});
test("dialog can close with Escape, has keyboard focus, and does not silently send",()=>{
  assert.match(page,/event\.key==="Escape"/);
  assert.match(page,/modalRef\.current\?\.querySelector/);
  assert.match(page,/document\.body\.style\.overflow="hidden"/);
  assert.match(page,/메일을 보내거나 삭제하지 않으며/);
});
