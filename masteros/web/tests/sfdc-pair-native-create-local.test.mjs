import test from "node:test";
import assert from "node:assert/strict";
import {mkdtemp,mkdir,writeFile,rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {createHash} from "node:crypto";
import {POST} from "../app/api/sfdc/pair-native-create-local/route.js";

const request=(mode,id,extra={})=>new Request(
 "http://127.0.0.1:3101/api/sfdc/pair-native-create-local",{
 method:"POST",headers:{"Host":"127.0.0.1:3101",
 "Origin":"http://127.0.0.1:3101","Sec-Fetch-Site":"same-origin",
 "Content-Type":"application/json","X-SFDC-Command":"1"},
 body:JSON.stringify({mode,requestId:id,...extra})});
const id="OPPOQUOTE-"+"0".repeat(24);
test("live native paired Save never runs without an immutable local approved request",async()=>{
 const home=await mkdtemp(join(tmpdir(),"paired-save-deny-"));
 const oldHome=process.env.LOCALAPPDATA;
 const oldEnabled=process.env.SFDC_LOCAL_COMMAND_ENABLED;
 const oldWrite=process.env.SFDC_PAIR_NATIVE_SAVE_ENABLED;
 process.env.LOCALAPPDATA=home;process.env.SFDC_LOCAL_COMMAND_ENABLED="1";
 delete process.env.SFDC_PAIR_NATIVE_SAVE_ENABLED;
 try{
  const s=await POST(request("STATUS",id));
  const summary=await s.json();
  assert.equal(s.status,200);
  assert.equal(summary.journalState,"NOT_STARTED");
  assert.equal(summary.automaticRetryAllowed,false);
  const bad=await POST(request("COMMIT",id,{
    confirmation:"CREATE 12345678",nonce:"a".repeat(48),
    approvalDigest:"PAIR-SAVE-"+"a".repeat(24)}));
  assert.ok([403,503].includes(bad.status));
  assert.equal((await bad.json()).salesforceWrite,false);
  const forged=await POST(request("COMMIT",id,{writeEnabled:true}));
  assert.equal(forged.status,400);
  const noQueue=await POST(request("PRECHECK",id));
  assert.ok([422,503].includes(noQueue.status));
  assert.equal((await noQueue.json()).status,"HOLD");
 }finally{
  if(oldHome===undefined)delete process.env.LOCALAPPDATA;
  else process.env.LOCALAPPDATA=oldHome;
  if(oldEnabled===undefined)delete process.env.SFDC_LOCAL_COMMAND_ENABLED;
  else process.env.SFDC_LOCAL_COMMAND_ENABLED=oldEnabled;
  if(oldWrite===undefined)delete process.env.SFDC_PAIR_NATIVE_SAVE_ENABLED;
  else process.env.SFDC_PAIR_NATIVE_SAVE_ENABLED=oldWrite;
  await rm(home,{recursive:true,force:true});
 }
});
