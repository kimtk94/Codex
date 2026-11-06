import test from "node:test";
import assert from "node:assert/strict";
import { inspectLocalContactEvidence } from "../lib/sfdc-local-contact-evidence.mjs";

const NOW = Date.parse("2026-11-06T00:00:00Z");
const A = {
  contact_id: "003000000000AAA",
  account_id: "001000000000AAA",
  korean_name: "김민수",
  institution_name: "합성대학교 산학협력단",
  email: "synthetic-a@example.org",
  linked_opportunity_ids: ["006000000000AAA"],
};
const B = {
  contact_id: "003000000000AAB",
  account_id: "001000000000AAB",
  korean_name: "김민수",
  institution_name: "가상대학교 산학협력단",
  email: "synthetic-b@example.org",
  linked_opportunity_ids: ["006000000000AAB"],
};
function evidence(extra = {}) {
  return JSON.stringify({
    version: "sfdc-oppo-contact-readback-v1",
    source: "SFDC_LIGHTNING_READ_ONLY",
    scope: "OPPORTUNITY_LINKED_CONTACTS",
    salesforce_write_performed: false,
    query: "김민수",
    generated_at: "2026-11-05T23:30:00Z",
    unresolved_matches: 0,
    candidates: [A, B],
    ...extra,
  });
}
const inspect = raw => inspectLocalContactEvidence(raw, "김민수", NOW);

test("private, recent full query creates non-executable local preview candidates", () => {
  const res = inspect(evidence());
  assert.equal(res.ok, true);
  assert.equal(res.exact_match_count, 2);
  assert.equal(res.requires_institution_choice, true);
  assert.equal(res.salesforce_save_allowed, false);
  assert.equal(res.status, "LOCAL_PREVIEW_ONLY_SERVER_RECHECK_REQUIRED");
  assert.equal(res.candidates.length, 2);
});
test("local file never permits mismatched customer name", () => {
  assert.equal(inspect(evidence({ query:"김민석" })).status, "SEARCH_NAME_MISMATCH");
});
test("unresolved matching Salesforce records prevent a unique-candidate claim", () => {
  assert.equal(inspect(evidence({ unresolved_matches:1 })).status, "INCOMPLETE_LOCAL_SEARCH_SCOPE");
});
test("stale or future files are rejected, independent of file name", () => {
  assert.equal(inspect(evidence({ generated_at:"2026-11-05T15:00:00Z" })).status, "STALE_OR_FUTURE_LOCAL_EVIDENCE");
  assert.equal(inspect(evidence({ generated_at:"2026-11-06T00:10:00Z" })).status, "STALE_OR_FUTURE_LOCAL_EVIDENCE");
});
test("source marker cannot grant Salesforce save permission", () => {
  assert.equal(inspect(evidence({ salesforce_write_performed:true })).status, "UNTRUSTED_LOCAL_EXPORT_SCHEMA");
  assert.equal(inspect(evidence({ source:"SFDC_API" })).status, "UNTRUSTED_LOCAL_EXPORT_SCHEMA");
});
test("malformed or excessive data fails closed", () => {
  assert.equal(inspect("{invalid").status, "INVALID_LOCAL_JSON");
  assert.equal(inspect("x".repeat(256 * 1024 + 10)).status, "LOCAL_FILE_EMPTY_OR_TOO_LARGE");
  assert.equal(inspect(evidence({ candidates: Array(31).fill(A) })).status, "INCOMPLETE_LOCAL_SEARCH_SCOPE");
});
test("incomplete same-name Contact cannot be silently ignored", () => {
  assert.equal(inspect(evidence({ candidates:[A, {...B,account_id:""}] })).status, "INCOMPLETE_OPPO_LINKED_CONTACT_DATA");
});
test("Contact not linked to an Opportunity does not create a selectable result", () => {
  const r = inspect(evidence({ candidates:[{...A,linked_opportunity_ids:[]}] }));
  assert.equal(r.ok,true);
  assert.equal(r.exact_match_count,0);
});
test("invalid query input is rejected before file parsing", () => {
  assert.equal(inspectLocalContactEvidence(evidence(), "John", NOW).status, "INVALID_KOREAN_NAME");
});
test("unnormalized missing timestamp or missing required metadata is rejected", () => {
  assert.equal(inspect(evidence({ generated_at:"11/05/2026" })).status, "MISSING_SOURCE_TIMESTAMP");
  assert.equal(inspect(evidence({ scope:"UNKNOWN" })).status, "UNTRUSTED_LOCAL_EXPORT_SCHEMA");
});
