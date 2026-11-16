import test from "node:test";
import assert from "node:assert/strict";
import {validKrwNativeContactQuery,validateLiveKrwContactSearch}
 from "../lib/sfdc-krw-native-contact-lookup.mjs";
const item={
 korean_name:"김지훈",institution_name:"합성대학교",
 account_id:"001000000000AAA",contact_id:"003000000000AAA",
 email:"synthetic@example.org",linked_opportunity_ids:["006000000000AAA"],
 source_qid:"QID-2026-11-16-414586",
};
const result=(rows=[item])=>({
 status:"PASS",local_only:true,salesforce_write:false,
 coverage:"VERIFIED_2026_KRW_QUOTE_CONTACTS_ONLY",
 candidates:rows,unresolved_matches:0
});

test("Korean query is scoped to the operator-selected native Contact identity only",()=>{
 const q=validKrwNativeContactQuery({query:"김지훈",limit:10});
 assert.equal(q.ok,true);
 assert.deepEqual(q.request,{query:"김지훈",limit:10});
 assert.equal(validKrwNativeContactQuery({query:"Kim Jihoon",limit:10}).ok,false);
 assert.equal(validKrwNativeContactQuery({query:"김지훈",limit:11}).ok,false);
 assert.equal(validKrwNativeContactQuery({query:"김지훈",limit:10,accountId:"001x"}).ok,false);
 assert.equal(validKrwNativeContactQuery({query:"김지훈",limit:10,save:true}).ok,false);
});

test("live proof requires exact Korean name, native account/contact/opportunity, no Save",()=>{
 const selected=validateLiveKrwContactSearch(result(),"김지훈");
 assert.equal(selected.ok,true);
 assert.equal(selected.exact_match_count,1);
 assert.equal(selected.candidates[0].account_id,item.account_id);
 assert.equal(selected.candidates[0].contact_id,item.contact_id);
 assert.equal(selected.salesforce_save_allowed,false);
 assert.equal(selected.status,"LIVE_QUOTE_LINKS_RECHECKED");
 for(const bad of [
  {...item,account_id:"CP202604123456"},
  {...item,contact_id:"CP202604123456"},
  {...item,linked_opportunity_ids:["Opp-2026-01"]},
  {...item,korean_name:"다른사람"},
  {...item,email:"unknown"},
 ]){
  assert.equal(validateLiveKrwContactSearch(result([bad]),"김지훈").ok,false);
 }
});

test("partial, stale, duplicate, or foreign-origin candidate sets fail closed",()=>{
 assert.equal(validateLiveKrwContactSearch({...result(),unresolved_matches:1},"김지훈").ok,false);
 assert.equal(validateLiveKrwContactSearch({...result(),coverage:"ALL_CRM"},"김지훈").ok,false);
 assert.equal(validateLiveKrwContactSearch({...result(),salesforce_write:true},"김지훈").ok,false);
 assert.equal(validateLiveKrwContactSearch(result([item,item]),"김지훈").ok,false);
 assert.equal(validateLiveKrwContactSearch({status:"BLOCK"},"김지훈").ok,false);
 const none=validateLiveKrwContactSearch(result([]),"김지훈");
 assert.equal(none.ok,true);
 assert.equal(none.exact_match_count,0);
 assert.equal(none.salesforce_save_allowed,false);
});

test("homonyms in distinct institutions remain independent candidates",()=>{
 const other={...item,institution_name:"가상대학교",
  account_id:"001000000000AAB",contact_id:"003000000000AAB",
  email:"other@example.org",linked_opportunity_ids:["006000000000AAB"]};
 const got=validateLiveKrwContactSearch(result([item,other]),"김지훈");
 assert.equal(got.ok,true);
 assert.equal(got.requires_institution_choice,true);
 assert.equal(got.exact_match_count,2);
 assert.notEqual(got.candidates[0].account_id,got.candidates[1].account_id);
});
