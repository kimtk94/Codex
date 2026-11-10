import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
const page=readFileSync(new URL("../app/sales/mail/page.jsx",import.meta.url),"utf8");
const body=readFileSync(new URL("../app/api/css/mail-body-local/route.js",import.meta.url),"utf8");
const styles=readFileSync(new URL("../app/sales/mail/page.module.css",import.meta.url),"utf8");

test("mail row and exact UID open a text-only body viewer",()=>{
  assert.match(page,/onClick=\{\(\)=>selectMail\(r\)\}/);
  assert.match(page,/data-testid="mail-body-text"/);
  assert.match(page,/\{bodyInfo\.text\}<\/pre>/);
  assert.doesNotMatch(page,/dangerouslySetInnerHTML/);
  assert.match(body,/UID=\/\^inbox:/);
  assert.match(body,/authorizeCssMailLocal/);
  assert.match(body,/MAIL_BODY_KEY_INVALID/);
});
test("viewer preserves skip, prior, next and CC rule choices without automatic write",()=>{
  assert.match(page,/navigateMail\(-1\)/);
  assert.match(page,/navigateMail\(1\)/);
  assert.match(page,/requestReview\("SKIP_MAIL"\)/);
  assert.match(page,/SKIP_CC_TO/);
  assert.match(page,/data-testid="review-action-area"/);
  assert.match(page,/setConfirming\(\{payload,caption\}\)/);
  assert.match(styles,/\.viewerTools\{position:sticky/);
});
