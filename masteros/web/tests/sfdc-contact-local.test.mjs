import test from "node:test";
import assert from "node:assert/strict";
import {parseLocalContacts, lookupLocalContacts} from "../lib/sfdc-contact-local.mjs";
const row=(name="김민수",institution="서울대학교",contact_id="003000000000001AAA",account_id="001000000000001AAA",opps=["006000000000001AAA"]) => ({
  name,institution,contact_id,account_id,contact_email:"researcher@example.org",opportunity_ids:opps
});
test("Korean exact name + homonym institution selection",()=>{
  const rows=parseLocalContacts(JSON.stringify([row(),row("김민수","연세대학교","003000000000002AAA","001000000000002AAA")]));
  assert.equal(lookupLocalContacts(" 김민수 ", rows).length,2);
  assert.equal(lookupLocalContacts("민수",rows).length,0);
});
test("no opportunity or invalid identity never eligible",()=>{
  assert.equal(parseLocalContacts(JSON.stringify([row("김민수","서울대학교",undefined,undefined,[])] )).length,0);
  assert.equal(parseLocalContacts(JSON.stringify([{...row(),contact_id:"bad"}])).length,0);
});
test("KAIST and Hannam excluded",()=>{
  const rows=parseLocalContacts(JSON.stringify(["KAIST","한국과학기술원","한남대","한남대학교","서울대학교"].map(x=>row("김민수",x))));
  assert.equal(rows.length,1);
  assert.equal(rows[0].institution,"서울대학교");
});
test("dedupe duplicate rows but never collapse distinct Contacts at one institution",()=>{
  const a=row();
  const b=row("김민수","서울대학교","003000000000002AAA");
  const rows=parseLocalContacts(JSON.stringify([a,a,b]));
  assert.equal(lookupLocalContacts("김민수",rows).length,2);
});
test("reject wrong JSON and oversized local export",()=>{
  for(const source of ["{}", "null", "broken", JSON.stringify({rows:[row()]})]) {
    assert.throws(()=>parseLocalContacts(source));
  }
  assert.throws(()=>parseLocalContacts(" ".repeat(2_000_001)));
});
test("repeat matches are deterministic and contain no automatic save flag",()=>{
  const rows=parseLocalContacts(JSON.stringify([row()]));
  const results=Array.from({length:3},()=>lookupLocalContacts("김민수",rows));
  assert.deepEqual(results[0],results[1]);
  assert.deepEqual(results[1],results[2]);
  assert.equal("save_allowed" in results[0][0],false);
});
