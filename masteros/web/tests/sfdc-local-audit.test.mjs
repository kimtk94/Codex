import test from "node:test";
import assert from "node:assert/strict";
import {authorizeAuditRead,projectPrivateAudit} from "../lib/sfdc-local-audit.mjs";

const good=()=>({enabled:true,platform:"win32",method:"GET",
  host:"127.0.0.1:31889",origin:"http://127.0.0.1:31889",
  fetchSite:"same-origin",header:"1"});

const fixtures=()=>[
  {scope:"PRIVATE_PREVIOUSLY_ENUMERATED_SNAPSHOT_NOT_LIVE_FULL_RECORD_RECHECK",
    full_quotation_count:862,one_product_manifest_count:412,
    non_one_product_or_unclassified_quote_count:450,
    opportunity_relation_counts:{parent_not_in_in_scope_opportunity_snapshot:22},
    name_comparison_counts:{contact_label_mismatch_or_missing:9},
    pii:"not for display"},
  {scope:"IN_SCOPE_OPPORTUNITY_SNAPSHOT_NOT_FULL_LIVE_RECHECK",
    opportunity_inventory_count:1013,approved_native_opportunity_ids_in_manifest:132},
  {summary:{structurally_one_to_one_candidates:177},
    candidates:[
      {quote_id:"a0P000000000001AAA",opportunity_id:"006000000000001AAA",
       known_contact_opportunity_live_evidence:true,salesforce_save_allowed:false},
      ...Array.from({length:176},(_,i)=>({
        quote_id:"a0P"+String(i+2).padStart(12,"0")+"AAA",
        opportunity_id:"006"+String(i+2).padStart(12,"0")+"AAA",
        known_contact_opportunity_live_evidence:false,salesforce_save_allowed:false
      }))
    ]},
  [{quote_id:"a0P000000000001AAA",opportunity_id:"006000000000001AAA",
    native_relation_status:"PASS_NATIVE_QUOTE_AND_PARENT_IDS",save_clicked:false}],
  [{name:"synthetic forbidden customer",contact_id:"003000000000001AAA"}],
];

test("local workstation opt-in required",()=>{
  assert.equal(authorizeAuditRead({...good(),enabled:false}).status,404);
});
test("hosted Linux cannot read private local metrics",()=>{
  assert.equal(authorizeAuditRead({...good(),platform:"linux"}).status,404);
});
test("same-origin strict loopback GET works",()=>{
  assert.deepEqual(authorizeAuditRead(good()),{ok:true});
});
test("remote DNS-rebound hosts rejected",()=>{
  for(const host of ["localhost:31889","127.0.0.1.bad:31889","example.org","10.0.0.2:31889"])
    assert.equal(authorizeAuditRead({...good(),host}).status,403);
});
test("cross-origin or missing custom header fails",()=>{
  assert.equal(authorizeAuditRead({...good(),origin:"https://bad.example"}).status,403);
  assert.equal(authorizeAuditRead({...good(),header:null}).status,403);
  assert.equal(authorizeAuditRead({...good(),fetchSite:"cross-site"}).status,403);
});
test("read-only metrics are strictly aggregated with no customer or native ID",()=>{
  const result=projectPrivateAudit(...fixtures());
  assert.equal(result.snapshot_quotations,862);
  assert.equal(result.one_to_one_name_candidates,177);
  assert.equal(result.verified_quote_native_parents,1);
  assert.equal(result.parent_verified_with_contact,1);
  assert.equal(result.parent_verified_contact_pending,0);
  assert.equal(result.approved_contact_aliases,1);
  assert.equal(result.save_allowed,false);
  assert.equal(JSON.stringify(result).includes("synthetic forbidden customer"),false);
  assert.equal(JSON.stringify(result).includes("a0P000000000001AAA"),false);
});
test("native linked pairs count deduplicated",()=>{
  const args=fixtures();
  args[3].push({...args[3][0]});
  assert.equal(projectPrivateAudit(...args).verified_quote_native_parents,1);
});
test("native parent verification without Contact never upgrades training evidence",()=>{
  const args=fixtures();
  args[3].push({quote_id:"a0P000000000002AAA",
                opportunity_id:"006000000000002AAA",
                native_relation_status:"PASS_NATIVE_QUOTE_AND_PARENT_IDS",
                save_clicked:false});
  // Historical record must also explicitly state no Save before counting.
  args[3][0].save_clicked=false;
  const result=projectPrivateAudit(...args);
  assert.equal(result.verified_quote_native_parents,2);
  assert.equal(result.parent_verified_with_contact,1);
  assert.equal(result.parent_verified_contact_pending,1);
  assert.equal(result.save_allowed,false);
});
test("native parent record with a Save flag cannot be verified",()=>{
  const args=fixtures();
  args[3][0].save_clicked=true;
  assert.equal(projectPrivateAudit(...args).verified_quote_native_parents,0);
});
test("snapshot cohort drift fails closed",()=>{
  const args=fixtures();
  args[0].non_one_product_or_unclassified_quote_count=444;
  assert.throws(()=>projectPrivateAudit(...args),/PARTITION/);
});
test("no missing private files silently treated as complete",()=>{
  const args=fixtures();
  args[2]=null;
  assert.throws(()=>projectPrivateAudit(...args),/INVALID/);
});
test("repeat three times deterministic",()=>{
  const results=Array.from({length:3},()=>projectPrivateAudit(...fixtures()));
  assert.deepEqual(results[0],results[1]);
  assert.deepEqual(results[1],results[2]);
});
