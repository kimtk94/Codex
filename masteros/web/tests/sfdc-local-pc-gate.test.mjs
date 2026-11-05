/** Synthetic request gating for localhost-only Contact snapshots. */
import test from "node:test";
import assert from "node:assert/strict";
import {authorizePcLocalLookup} from "../lib/sfdc-local-pc-gate.mjs";

function request(extra={}) {
  return {enabled:true,method:"GET",host:"127.0.0.1:31889",
    origin:"http://127.0.0.1:31889",fetchSite:"same-origin",
    localHeader:"1",name:"김민수",...extra};
}
test("requires explicit enable flag",()=>{
  assert.equal(authorizePcLocalLookup(request({enabled:false})).status,404);
});
test("same origin localhost request with explicit header is allowed",()=>{
  const a=authorizePcLocalLookup(request());
  assert.equal(a.ok,true);
  assert.equal(a.name,"김민수");
});
test("reject remote or DNS-rebound hosts",()=>{
  for(const host of ["example.com","localhost:31889","127.0.0.1.evil:31889","10.0.0.3:31889","127.0.0.1","[::1]:31889"]){
    assert.equal(authorizePcLocalLookup(request({host})).ok,false);
  }
});
test("deny mismatched Origin",()=>{
  assert.equal(authorizePcLocalLookup(request({origin:"https://untrusted.example"})).status,403);
});
test("deny cross-site browser",()=>{
  assert.equal(authorizePcLocalLookup(request({fetchSite:"cross-site"})).status,403);
});
test("deny missing user-initiated custom header",()=>{
  assert.equal(authorizePcLocalLookup(request({localHeader:null})).status,403);
});
test("GET only; no POST or CRM mutation",()=>{
  for(const method of ["POST","PUT","PATCH","DELETE"]){
    assert.equal(authorizePcLocalLookup(request({method})).status,403);
  }
});
test("exact Korean name, no broad enumeration",()=>{
  for(const name of ["","김","KimMinSu","김민수*","김민수 OR 1","김 민수","김민수".repeat(4)]){
    assert.equal(authorizePcLocalLookup(request({name})).ok,false);
  }
});
test("three deterministic loopback-only checks",()=>{
  const runs=Array.from({length:3},()=>authorizePcLocalLookup(request()));
  assert.deepEqual(runs[0],runs[1]);
  assert.deepEqual(runs[1],runs[2]);
});
