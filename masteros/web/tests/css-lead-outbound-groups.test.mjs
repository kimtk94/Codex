import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {leadOutboundGroup,leadOutboundSummary,leadGroupMatches}
  from "../lib/css-lead-outbound-groups.mjs";

const sentAfter={id:"A",evidence:"SENT_AFTER_LEAD_CONFIRMED",afterCount:"3",everCount:"4",
  firstAfter:"2026-11-09 11:30",lastAfter:"2026-11-11 09:30"};
const sentBefore={id:"B",evidence:"SENT_BEFORE_LEAD_ONLY",afterCount:"0",everCount:"2",
  firstEver:"2026-10-20 09:20"};
const none={id:"C",evidence:"NO_PERSONAL_OUTBOUND_EVIDENCE",afterCount:"0",everCount:"0"};
const unknown={id:"D",evidence:"CREATED_DATE_UNVERIFIED",afterCount:"0",everCount:"1"};
const contradiction={id:"E",evidence:"NO_PERSONAL_OUTBOUND_EVIDENCE",afterCount:"0",everCount:"5"};

test("Lead sends are separated by personal outbound evidence, not by Lead creation alone",()=>{
  assert.equal(leadOutboundGroup(sentAfter),"SENT");
  assert.equal(leadOutboundGroup(sentBefore),"SENT");
  assert.equal(leadOutboundGroup(none),"NO_EVIDENCE");
  assert.equal(leadOutboundGroup(unknown),"REVIEW");
  assert.equal(leadOutboundGroup(contradiction),"REVIEW");
  const counts=leadOutboundSummary([sentAfter,sentBefore,none,unknown,contradiction]);
  assert.deepEqual(counts,{all:5,sent:2,sentAfter:1,sentBeforeOnly:1,noEvidence:1,review:2});
  assert.equal(counts.sent+counts.noEvidence+counts.review,counts.all);
});
test("Missing or inconsistent counts cannot be mislabelled 'no emails sent'",()=>{
  for(const row of [
    {...none,everCount:""}, {...sentAfter,everCount:"abc"},
    {...sentBefore,afterCount:"1"}, {...sentAfter,afterCount:"5",everCount:"2"},
    {...none,evidence:"LEAD_EMAIL_MISSING"},
    {...none,evidence:"UNKNOWN_CODE"}
  ])assert.equal(leadOutboundGroup(row),"REVIEW");
});
test("Group filter and detailed selection require consistent classification",()=>{
  assert.equal(leadGroupMatches(sentAfter,"SENT"),true);
  assert.equal(leadGroupMatches(sentBefore,"SENT"),true);
  assert.equal(leadGroupMatches(none,"SENT"),false);
  assert.equal(leadGroupMatches(none,"NO_EVIDENCE"),true);
  assert.equal(leadGroupMatches(sentBefore,"SENT","SENT_AFTER_LEAD_CONFIRMED"),false);
  assert.equal(leadGroupMatches(sentBefore,"SENT","SENT_BEFORE_LEAD_ONLY"),true);
});
test("UI exposes direct sent/not-found/review group buttons with exact Lead details",()=>{
  const view=readFileSync(new URL("../app/sales/mail/page.jsx",import.meta.url),"utf8");
  const css=readFileSync(new URL("../app/sales/mail/page.module.css",import.meta.url),"utf8");
  assert.match(view,/data-testid=\{"lead-group-"\+item\.id\}/);
  assert.match(view,/내 발송 이력 있음/);
  assert.match(view,/내 발송 증거 없음/);
  assert.match(view,/생성 전만 발송/);
  assert.match(view,/setLeadState\("ALL"\)/);
  assert.match(view,/leadOutboundSummary\(data\?\.leads\|\|\[\]\)/);
  assert.match(view,/미발송 확정 아님/);
  assert.match(css,/\.leadGroups/);
});
