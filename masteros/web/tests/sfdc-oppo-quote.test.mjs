import test from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_REQUEST, MODES, unitForMode, validateDraft, formatDraft } from "../lib/sfdc-oppo-quote.mjs";

const draft = () => ({
  contact_email: "researcher@example.org",
  service: "PMP",
  sequencing_mode: "PE250",
  sample_count: 5,
  depth_per_sample: 1,
  depth_unit: "M reads",
});

test("single-service only: multiple products or unsupported services fail closed", () => {
  for (const service of ["PMP+PML", "PML", "mRNA", "", null]) {
    const r = draft(); r.service = service;
    assert.equal(validateDraft(r).ok, false);
  }
});
test("mode and unit cross-product never silently converts historical values", () => {
  for (const mode of MODES) for (const unit of ["M reads", "Gb"]) {
    const r = draft(); r.sequencing_mode = mode; r.depth_unit = unit;
    assert.equal(validateDraft(r).ok, unit === unitForMode(mode));
  }
});
test("all supported modes preserve per-sample quantity and explicit total", () => {
  for (const mode of MODES) for (const count of [1, 5, 500]) {
    const r = draft(); r.sequencing_mode = mode; r.depth_unit = unitForMode(mode);
    r.sample_count = count; r.depth_per_sample = 1.25;
    const result = validateDraft(r);
    assert.equal(result.ok, true);
    assert.equal(result.draft.summary.nominal_total_depth, count * 1.25);
    assert.equal(result.draft.summary.depth_unit, r.depth_unit);
    assert.equal(result.draft.salesforce_save_allowed, false);
  }
});
test("unverified customer identity, institution, and Salesforce IDs cannot be injected", () => {
  for (const extra of [
    { contact_name: "김동명이" }, { institution: "Synthetic University" },
    { account_id: "001000000000000AAA" }, { opportunity_id: "006000000000000AAA" },
    { quotation_id: "a0P000000000000AAA" }, { save_allowed: true },
    { price: 100000 }, { business_entity: "Korea" },
  ]) {
    const r = { ...draft(), ...extra };
    assert.equal(validateDraft(r).ok, false);
  }
});
test("invalid draft has no printable approved command and never returns inferred IDs", () => {
  for (const changes of [
    { contact_email: "" }, { sample_count: 0 },
    { sequencing_mode: "250PE" }, { depth_unit: "Gb" },
  ]) {
    const r = {...draft(), ...changes};
    assert.equal(validateDraft(r).ok, false);
    assert.throws(() => formatDraft(r));
  }
  const valid = JSON.parse(formatDraft(draft()));
  assert.deepEqual(valid.required_checks, [
    "exact_contact_email_identity",
    "account_record_id_and_contact_lookup",
    "existing_opportunity_and_quotation_duplicates",
    "approved_opportunity_name_amount_stage_close_date",
    "current_business_entity_promotion_type_valid_thru",
    "verified_price_and_quote_lines",
    "post_creation_native_006_parent_and_a0P_quote_links",
  ]);
  for (const field of ["account_id","contact_id","opportunity_id","quotation_id","price","save_approved"]) {
    assert.equal(Object.hasOwn(valid,field),false);
  }
});
test("repeated draft generation is deterministic and remains strictly no-save", () => {
  const r = draft();
  const outputs = Array.from({length:3},()=>formatDraft(r));
  assert.equal(new Set(outputs).size,1);
  for(const value of outputs) {
    const command = JSON.parse(value);
    assert.equal(command.salesforce_save_allowed,false);
    assert.equal(command.opportunity_created,false);
    assert.equal(command.quotation_created,false);
  }
});

test("PE250 and other modes switch units", () => {
  assert.equal(unitForMode("PE250"), "M reads");
  for (const m of MODES.filter(x => x !== "PE250")) assert.equal(unitForMode(m), "Gb");
  assert.throws(() => unitForMode("250PE"));
});
test("valid PMP five samples, one M reads per sample", () => {
  const r = validateDraft(draft());
  assert.equal(r.ok, true);
  assert.deepEqual(r.draft.request, draft());
  assert.equal(r.draft.summary.nominal_total_depth, 5);
  assert.equal(r.draft.summary.depth_unit, "M reads");
  assert.equal(r.draft.summary.reads_basis, "UNSPECIFIED_WHETHER_READS_OR_READ_PAIRS");
  assert.equal(r.draft.salesforce_save_allowed, false);
  assert.equal(r.draft.opportunity_created, false);
  assert.equal(r.draft.quotation_created, false);
});
test("PE150+Gb valid, PE150+M reads invalid", () => {
  const r = draft();r.sequencing_mode = "PE150";r.depth_unit = "Gb";r.depth_per_sample=6;
  assert.equal(validateDraft(r).draft.summary.nominal_total_depth,30);
  r.depth_unit = "M reads";
  assert.equal(validateDraft(r).ok,false);
});
test("PE250+Gb does not inherit historical units", () => {
  const r=draft();r.depth_unit="Gb";
  assert.equal(validateDraft(r).ok,false);
});
test("sample quantities must be positive integer", () => {
  for(const count of [0,2.5,-1,501,NaN,Infinity]) {
    const r=draft();r.sample_count=count;assert.equal(validateDraft(r).ok,false);
  }
});
test("depth must be finite positive and bounded", () => {
  for(const depth of [0,-1,NaN,Infinity,-Infinity,100001]) {
    const r=draft();r.depth_per_sample=depth;assert.equal(validateDraft(r).ok,false);
  }
});
test("email invalid or missing blocks command", () => {
  for(const email of ["","researcher","researcher@"," researcher@example.org","x@y z"]) {
    const r=draft();r.contact_email=email;assert.equal(validateDraft(r).ok,false);
  }
});
test("unknown fields prevent accidental CRM write or customer-ID claims", () => {
  const r=draft();r.account_id="001000000000000AAA";
  assert.equal(validateDraft(r).ok,false);
});
test("no quote price, stage, close date, parent ID or API execution in preview", () => {
  const r=validateDraft(draft()).draft;
  const text=JSON.stringify(r);
  for(const forbidden of ["amount","price","close_date","stage","parent_record_id","save_approved"]) {
    assert.equal(text.includes('"' + forbidden + '"'),false);
  }
  assert.equal(r.required_checks.length,7);
});
test("invalid draft cannot be copied as valid command", () => {
  const r=draft();r.contact_email="";
  assert.throws(()=>formatDraft(r));
});
test("default web form contains no customer email", () => {
  assert.equal(DEFAULT_REQUEST.contact_email,"");
  assert.equal(DEFAULT_REQUEST.sample_count,5);
  assert.equal(DEFAULT_REQUEST.depth_per_sample,1);
});
test("reject null, array, and missing request properties", () => {
  for(const r of [null,[],{},{"contact_email":"a@example.org"}])assert.equal(validateDraft(r).ok,false);
});
