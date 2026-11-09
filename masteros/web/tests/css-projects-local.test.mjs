import test from "node:test";
import assert from "node:assert/strict";
import {authorizeCssPcRead,summarizeProjects} from "../lib/css-projects-local.mjs";

const permit={enabled:true,method:"GET",host:"127.0.0.1:3000",
              origin:"http://127.0.0.1:3000",fetchSite:"same-origin",header:"1"};
test("local explicit read only",()=>{
  assert.equal(authorizeCssPcRead(permit).ok,true);
  for(const overrides of [
    {enabled:false},{method:"POST"},{host:"evil.example:3000"},
    {host:"localhost:3000"},{origin:"http://attacker.invalid"},
    {fetchSite:"cross-site"},{header:""},{header:undefined},
  ]){
    assert.equal(authorizeCssPcRead({...permit,...overrides}).ok,false);
  }
});
test("valid project stage distribution",()=>{
  const r=summarizeProjects({status:"PASS_MIRROR_ONLY",project_rows:[
    {project_id:"X00000000000001-Z01",stage:"Sequencing"},
    {project_id:"X00000000000002-Z01",stage:"Sequencing"},
    {project_id:"X00000000000003-Z01",stage:"Sample QC"},
  ]});
  assert.equal(r.recordCount,3);
  assert.deepEqual(r.stageCounts,{"Sequencing":2,"Sample QC":1});
});
test("duplicate, unsupported and unverified payload blocked",()=>{
  for(const raw of [
    {status:"PASS",project_rows:[]},
    {status:"PASS_MIRROR_ONLY",project_rows:[{project_id:"A"},{project_id:"A"}]},
    {status:"PASS_MIRROR_ONLY",project_rows:[{project_id:""}]},
    {status:"PASS_MIRROR_ONLY",project_rows:null},
  ])assert.throws(()=>summarizeProjects(raw));
});
