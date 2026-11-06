import test from "node:test";
import assert from "node:assert/strict";
import {
  validateKoreanNameQuery, auditContactCandidates, selectExistingContact,
  createContactLinkedNoSaveCommand,
} from "../lib/sfdc-contact-first-command.mjs";

const baseRequest = {
  contact_email: "",
  service: "PMP",
  sequencing_mode: "PE250",
  sample_count: 5,
  depth_per_sample: 1,
  depth_unit: "M reads",
};
const KNU = {
  contact_id: "003000000000AAA",
  account_id: "001000000000AAA",
  korean_name: "김민수",
  institution_name: "경북대학교 산학협력단",
  email: "a@example.org",
  linked_opportunity_ids: ["006000000000AAA"],
};
const YONSEI = {
  contact_id: "003000000000AAB",
  account_id: "001000000000AAB",
  korean_name: "김민수",
  institution_name: "연세대학교 산학협력단",
  email: "b@example.org",
  linked_opportunity_ids: ["006000000000AAB"],
};

test("Korean full name searches are valid", () => {
  assert.deepEqual(validateKoreanNameQuery(" 김 민수 "), {
    ok: true, query: "김 민수", lookup_field: "Contact Korean Name",
  });
  assert.equal(validateKoreanNameQuery("박성혁").ok, true);
});

test("Email search is disallowed even if exact", () => {
  assert.equal(validateKoreanNameQuery("a@example.org").ok, false);
});
test("English name and query too short/long are blocked", () => {
  for (const val of ["A", "John Kim", "김", "김민수123", "김민수@", "김".repeat(21), null, ""]) {
    assert.equal(validateKoreanNameQuery(val).ok, false);
  }
});
test("No authenticated lookup means no results, no contact selection", () => {
  assert.equal(auditContactCandidates("김민수", null).status, "LOOKUP_NOT_CONNECTED");
});
test("Exact Korean name only, never fuzzy-match a different person", () => {
  const r = auditContactCandidates("김민수", [KNU, {...YONSEI, korean_name:"김민석"}]);
  assert.equal(r.exact_match_count, 1);
  assert.equal(r.requires_institution_choice, false);
});
test("Homonyms across institutions require choosing the institution and record", () => {
  const r = auditContactCandidates("김민수", [KNU, YONSEI]);
  assert.equal(r.exact_match_count, 2);
  assert.equal(r.requires_institution_choice, true);
  assert.equal(selectExistingContact("김민수", [KNU, YONSEI]).status, "CONTACT_AND_INSTITUTION_NOT_SELECTED");
  const selected = selectExistingContact("김민수", [KNU, YONSEI], YONSEI.contact_id, YONSEI.account_id);
  assert.equal(selected.ok, true);
  assert.equal(selected.institution_name, YONSEI.institution_name);
  assert.equal(selected.requires_server_identity_recheck, true);
});
test("Same name in same institution is ambiguous even after institution choice", () => {
  const second = {...YONSEI, account_id:KNU.account_id};
  const r = auditContactCandidates("김민수", [KNU, second]);
  assert.equal(r.has_duplicates_within_institution, true);
  assert.equal(
    selectExistingContact("김민수",[KNU,second],KNU.contact_id,KNU.account_id).status,
    "SAME_NAME_SAME_INSTITUTION_AMBIGUOUS"
  );
});
test("Contact Account ID pairing cannot be mixed across universities", () => {
  assert.equal(
    selectExistingContact("김민수",[KNU,YONSEI],KNU.contact_id,YONSEI.account_id).status,
    "CONTACT_ACCOUNT_PAIR_MISMATCH"
  );
});
test("Even a unique name requires explicit Contact and Account choice", () => {
  assert.equal(
    selectExistingContact("김민수",[KNU]).status,
    "CONTACT_AND_INSTITUTION_NOT_SELECTED"
  );
});
test("Malformed or duplicated Contact IDs are rejected", () => {
  assert.equal(auditContactCandidates("김민수",[KNU,KNU]).status,"DUPLICATE_CONTACT_ID");
  assert.equal(auditContactCandidates("김민수",[{...KNU,contact_id:"abc"}]).status,"INCOMPLETE_OPPO_LINKED_CONTACT_DATA");
});
test("Missing Account record or email does not qualify for selection", () => {
  assert.equal(auditContactCandidates("김민수",[{...KNU,account_id:""}]).status,"INCOMPLETE_OPPO_LINKED_CONTACT_DATA");
  assert.equal(auditContactCandidates("김민수",[{...KNU,email:""}]).status,"INCOMPLETE_OPPO_LINKED_CONTACT_DATA");
});
test("Incomplete same-name row must not make another contact look unique", () => {
  const invalid = {...YONSEI,account_id:""};
  const result=auditContactCandidates("김민수",[KNU,invalid]);
  assert.equal(result.status,"INCOMPLETE_OPPO_LINKED_CONTACT_DATA");
  assert.equal(selectExistingContact("김민수",[KNU,invalid],KNU.contact_id,KNU.account_id).ok,false);
});
test("Only existing Opportunity-associated Contacts appear in search", () => {
  const noOppo = {...YONSEI,linked_opportunity_ids:[]};
  const r=auditContactCandidates("김민수",[KNU,noOppo]);
  assert.equal(r.exact_match_count,1);
  assert.equal(r.requires_institution_choice,false);
  assert.equal(r.candidates[0].contact_id,KNU.contact_id);
});

test("Contact with zero Opportunities cannot be selected or used to draft", () => {
  const onlyNoOppo={...KNU,linked_opportunity_ids:[]};
  const r=auditContactCandidates("김민수",[onlyNoOppo]);
  assert.equal(r.status,"NO_EXACT_MATCH");
  const chosen=selectExistingContact("김민수",[onlyNoOppo],onlyNoOppo.contact_id,onlyNoOppo.account_id);
  assert.equal(chosen.ok,false);
  const forged={ok:true,requires_server_identity_recheck:true,
    ...onlyNoOppo};
  assert.equal(createContactLinkedNoSaveCommand(baseRequest,forged).ok,false);
});

test("Malformed claimed Oppo link blocks the whole candidate result", () => {
  const fake={...YONSEI,linked_opportunity_ids:["006INVALID"]};
  const r=auditContactCandidates("김민수",[KNU,fake]);
  assert.equal(r.ok,false);
  assert.equal(r.status,"INCOMPLETE_OPPO_LINKED_CONTACT_DATA");
});

test("Contact command carries source Oppo ID and still requires server recheck", () => {
  const chosen=selectExistingContact("김민수",[KNU],KNU.contact_id,KNU.account_id);
  const result=createContactLinkedNoSaveCommand(baseRequest,chosen);
  assert.equal(result.ok,true);
  assert.deepEqual(result.command.contact.reference_opportunity_ids,KNU.linked_opportunity_ids);
  assert.equal(result.command.next_actions.includes("independently_verify_opportunity_contact_relationship"),true);
  assert.equal(result.command.salesforce_save_allowed,false);
});

test("Invalid name is never treated as a Contact match", () => {
  assert.equal(auditContactCandidates("John", [KNU]).status,"INVALID_KOREAN_NAME");
});
test("Selected contact populates email from existing record, not user typing", () => {
  const selected=selectExistingContact("김민수",[KNU],KNU.contact_id,KNU.account_id);
  const result=createContactLinkedNoSaveCommand(baseRequest,selected);
  assert.equal(result.ok,true);
  assert.equal(result.command.request.contact_email,KNU.email);
  assert.equal(result.command.contact.contact_id,KNU.contact_id);
  assert.equal(result.command.contact.account_id,KNU.account_id);
  assert.equal(result.command.summary.nominal_total_depth,5);
});
test("Generated command is never executable or saved", () => {
  const selected=selectExistingContact("김민수",[KNU],KNU.contact_id,KNU.account_id);
  const command=createContactLinkedNoSaveCommand(baseRequest,selected).command;
  assert.equal(command.save_clicked,false);
  assert.equal(command.salesforce_save_allowed,false);
  assert.equal(command.opportunity_created,false);
  assert.equal(command.quotation_created,false);
  assert.equal(command.send_customer_email,false);
  assert.equal(command.state,"PENDING_AUTHENTICATED_CONTACT_RECHECK");
});
test("Unselected, forged or unverified customer cannot create command", () => {
  assert.equal(createContactLinkedNoSaveCommand(baseRequest,null).ok,false);
  assert.equal(createContactLinkedNoSaveCommand(baseRequest,{ok:true}).ok,false);
});
test("A forged browser selection is not accepted for command construction", () => {
  const forged = { ok:true, requires_server_identity_recheck:true, contact_id:"FAKE", account_id:"FAKE", email:"a@example.org", institution_name:"Fake", korean_name:"김민수" };
  assert.equal(createContactLinkedNoSaveCommand(baseRequest,forged).ok,false);
});
test("KAIST and Hannam Account contacts are excluded from web automation", () => {
  for (const [id, institution_name, status] of [
    ["003000000000AAD", "KAIST Korea Advanced Institute of Science", "SKIP_ACCOUNT_KAIST"],
    ["003000000000AAE", "한남대학교 산학협력단 Hannam University", "SKIP_ACCOUNT_HANNAM"],
  ]) {
    const contact={...KNU,contact_id:id,institution_name};
    const selected=selectExistingContact("김민수",[contact],id,contact.account_id);
    assert.equal(selected.ok,false);
    assert.equal(selected.status,status);
    const forged={ok:true,requires_server_identity_recheck:true,contact_id:id,account_id:contact.account_id,korean_name:"김민수",institution_name,email:contact.email,linked_opportunity_ids:contact.linked_opportunity_ids};
    const preview=createContactLinkedNoSaveCommand(baseRequest,forged);
    assert.equal(preview.ok,false);
    assert.equal(preview.error,status);
  }
});
test("Quantity and mode validation remain mandatory after contact selection", () => {
  const selected=selectExistingContact("김민수",[KNU],KNU.contact_id,KNU.account_id);
  assert.equal(createContactLinkedNoSaveCommand({...baseRequest,sample_count:0},selected).ok,false);
  assert.equal(createContactLinkedNoSaveCommand({...baseRequest,depth_unit:"Gb"},selected).ok,false);
});
