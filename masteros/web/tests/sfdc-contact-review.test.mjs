/** Synthetic Contact identity and No-Save command packet tests. */
import test from "node:test";
import assert from "node:assert/strict";
import { buildContactReviewPacket, CONTACT_REVIEW_VERSION } from "../lib/sfdc-contact-review.mjs";
import { DEFAULT_REQUEST } from "../lib/sfdc-oppo-quote.mjs";

function contact() {
  return { name:"김민수", institution:"연세대학교",
    contact_id:"003000000000001AAA",
    account_id:"001000000000001AAA",
    contact_email:"synthetic@example.org",
    opportunity_ids:["006000000000001AAA"] };
}
function request() { return {...DEFAULT_REQUEST, contact_email:contact().contact_email}; }

test("Contact-bound packet strictly contains native Contact Account and Oppo IDs",()=>{
  const packet=buildContactReviewPacket(request(),contact());
  assert.equal(packet.version,CONTACT_REVIEW_VERSION);
  assert.equal(packet.selected_contact.contact_id,contact().contact_id);
  assert.equal(packet.selected_contact.account_id,contact().account_id);
  assert.deepEqual(packet.selected_contact.opportunity_ids,contact().opportunity_ids);
  assert.equal(packet.draft.request.contact_email,contact().contact_email);
  assert.equal(packet.gate.salesforce_save_allowed,false);
  assert.equal(packet.gate.contact_identity_live_verified,false);
  assert.equal(packet.draft.salesforce_save_allowed,false);
});

test("email hand edit invalidates native Contact selection",()=>{
  assert.throws(()=>buildContactReviewPacket({...request(),contact_email:"other@example.org"},contact()),
    /이메일/);
});
test("missing Contact identity fails closed",()=>{
  assert.throws(()=>buildContactReviewPacket(request(),null),/선택/);
});
test("excluded institution may never be exported",()=>{
  assert.throws(()=>buildContactReviewPacket(request(),{...contact(),institution:"KAIST"}),/ID/);
});
test("candidate without an existing Opportunity is rejected",()=>{
  assert.throws(()=>buildContactReviewPacket(request(),{...contact(),opportunity_ids:[]}),/ID/);
});
test("malformed Salesforce IDs fail closed",()=>{
  assert.throws(()=>buildContactReviewPacket(request(),{...contact(),contact_id:"fake"}),/ID/);
});
test("English-only names must not invent a Korean identity",()=>{
  assert.throws(()=>buildContactReviewPacket(request(),{...contact(),name:"KimMinSu"}),/한글/);
});
test("no amount, price, created flags, or live verification claim",()=>{
  const packet=buildContactReviewPacket(request(),contact());
  const raw=JSON.stringify(packet);
  assert.equal(raw.includes('"opportunity_created":true'),false);
  assert.equal(raw.includes('"quotation_created":true'),false);
  assert.equal(raw.includes('"salesforce_save_allowed":true'),false);
  assert.equal(Object.keys(packet.gate).every(k=>packet.gate[k]===false),true);
});
test("three-round review packets are deterministic and immutable by caller",()=>{
  const selected=contact();
  const copies=Array.from({length:3},()=>buildContactReviewPacket(request(),selected));
  assert.deepEqual(copies[0],copies[1]);
  assert.deepEqual(copies[1],copies[2]);
  copies[0].selected_contact.opportunity_ids.push("006000000000002AAA");
  assert.deepEqual(selected.opportunity_ids,contact().opportunity_ids);
});
