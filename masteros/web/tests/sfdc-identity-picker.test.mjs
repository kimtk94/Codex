import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {normalizeIdentityRows,dedupeAccounts,selectIdentityPair,matchingIdentity}
  from "../lib/sfdc-identity-picker.mjs";

const ref=(institution,accountId,contactId,name="김지훈")=>({
  source_qid:"QID-2026-11-10-001111",account_id:accountId,
  account_name:institution,contact_id:contactId,contact_name:name,
  contact_email:"researcher@university.ac.kr",crm_account_verified:true,
  crm_contact_verified:true
});
const a=ref("연세대학교 산학협력단","001000000000000AAA","003000000000000AAA");
const b=ref("연세대학교 의료원 산학협력단","001000000000000AAB","003000000000000AAB");
const c=ref("인하대학교","001000000000000AAC","003000000000000AAC");

test("homonymous Contacts remain distinct and retain their institution",()=>{
  const rows=normalizeIdentityRows([a,b,a,c,{...c,account_name:""}]);
  assert.equal(rows.length,3);
  assert.deepEqual(rows.map(x=>x.account_name),
    ["연세대학교 산학협력단","연세대학교 의료원 산학협력단","인하대학교"]);
  assert.deepEqual(rows.map(x=>x.contact_name),["김지훈","김지훈","김지훈"]);
  assert.equal(dedupeAccounts(rows).length,3);
});
test("contact selection returns exact paired Account and Contact IDs",()=>{
  const p=selectIdentityPair(b);
  assert.equal(p.ok,true);
  assert.equal(p.account.id,b.account_id);
  assert.equal(p.account.name,b.account_name);
  assert.equal(p.contact.id,b.contact_id);
  assert.equal(p.sourceVerifiedIds,true);
  assert.equal(selectIdentityPair({...b,account_name:""}).ok,false);
  const form={accountId:b.account_id,accountName:b.account_name,
    contactId:b.contact_id,contactName:b.contact_name};
  assert.equal(matchingIdentity(form,p).ok,true);
  assert.equal(matchingIdentity({...form,accountId:a.account_id},p).code,
    "ACCOUNT_CONTACT_SELECTION_CHANGED");
  assert.equal(matchingIdentity({...form,contactName:"동명이인"},p).ok,false);
  assert.equal(matchingIdentity(form,null).ok,false);
});
test("search UI always displays institution alongside Contact, saves nothing",()=>{
  const picker=readFileSync(new URL("../app/sales/commands/IdentityPicker.jsx",import.meta.url),"utf8");
  const main=readFileSync(new URL("../app/sales/commands/page.jsx",import.meta.url),"utf8");
  const pair=readFileSync(new URL("../app/sales/commands/pair/ReportOppoDraft.jsx",import.meta.url),"utf8");
  assert.match(picker,/\{row\.contact_name\} · \{row\.account_name\}/);
  assert.match(picker,/value=\{contactQuery\}/);
  assert.match(picker,/onContact\(selected\)/);
  assert.match(picker,/accountStatus!=="PASS"/);
  assert.match(picker,/contactStatus!=="PASS"/);
  assert.match(main,/matchingIdentity\(form,selectedIdentity\)/);
  assert.match(main,/await hydrateLinkedQuote\(id,next\)/);
  assert.match(main,/unitPriceEdited\?base\.unitPriceNetKrw:checked\.form\.unitPriceNetKrw/);
  assert.match(pair,/onAccount=\{chooseAccount\} onContact=\{chooseContact\}/);
  assert.doesNotMatch(pair,/변경 Contact 이름/);
});
