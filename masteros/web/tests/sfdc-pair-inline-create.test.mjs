import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";

const page=await readFile(new URL("../app/sales/commands/pair/page.jsx",import.meta.url),"utf8");
const editor=await readFile(new URL("../app/sales/commands/pair/ReportOppoDraft.jsx",import.meta.url),"utf8");
const approve=await readFile(new URL("../app/sales/commands/pair/approvals/PairedSaveApproval.jsx",import.meta.url),"utf8");

test("existing Opportunity is the default input, with source Quote only when needed",()=>{
 assert.match(page,/useState\("OPPORTUNITY"\)/);
 assert.match(page,/data\.quotes\.length===1/);
 assert.match(page,/select\(item,selectedOppo\.opportunity_external\)/);
 assert.doesNotMatch(page,/href="\/sales\/commands\/pair\/approvals"/);
 assert.match(page,/실제 SFDC 저장 지원/);
});

test("new Oppo+Quote Save is inline in the same editor, with required source evidence",()=>{
 assert.match(editor,/SourceSalesforceEvidence quote=\{quote\} onVerified=\{onSourceVerified\}/);
 assert.match(editor,/data-testid="oppo-quote-creation-request"/);
 assert.match(editor,/data-testid="oppo-quote-compact-summary"/);
 assert.match(editor,/data-testid="oppo-quote-request-confirmation"/);
 assert.match(editor,/<PairedSaveApproval compact key=\{creationRequest\.requestId\}/);
 assert.match(editor,/creationRequest\.status==="PENDING_APPROVAL"/);
 assert.doesNotMatch(editor,/href="\/sales\/commands\/pair\/approvals"/);
 assert.match(editor,/account-contact-advanced/);
 assert.match(editor,/source-quote-fees/);
});
test("two-stage native Save stays locked behind live precheck and per-record confirmation",()=>{
 assert.match(approve,/data-testid="pair-real-save-precheck"/);
 assert.match(approve,/data-testid="pair-real-save-commit"/);
 assert.match(approve,/precheck\?\.status!=="READY_FOR_OPERATOR_APPROVAL"/);
 assert.match(approve,/!duplicateChecked/);
 assert.match(approve,/window\.confirm/);
 assert.match(approve,/payload\.nonce=precheck\.nonce/);
 assert.match(approve,/payload\.approvalDigest=precheck\.approvalDigest/);
 assert.match(approve,/payload\.duplicateConfirmed=duplicateChecked/);
 assert.doesNotMatch(approve,/type="password"/);
});
