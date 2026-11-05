/** Synthetic-only safety gates for a user's own loopback Salesforce preflight. */
import test from "node:test";
import assert from "node:assert/strict";
import {authorizePcReadOnlyReview} from "../lib/sfdc-local-review-gate.mjs";

const good=()=>({
  enabled:true,platform:"win32",method:"POST",
  host:"127.0.0.1:31889",origin:"http://127.0.0.1:31889",
  fetchSite:"same-origin",localHeader:"1",
  contentType:"application/json",
});

test("explicit workstation opt-in is required",()=>{
  assert.equal(authorizePcReadOnlyReview({...good(),enabled:false}).status,404);
});
test("hosted Linux Next.js cannot enable a workstation route",()=>{
  assert.equal(authorizePcReadOnlyReview({...good(),platform:"linux"}).status,404);
});
test("valid PC same-origin JSON POST is authorized for read-only preflight",()=>{
  assert.deepEqual(authorizePcReadOnlyReview(good()),{ok:true});
});
test("no GET/PUT/PATCH/DELETE allowed",()=>{
  for(const method of ["GET","PUT","PATCH","DELETE"])
    assert.equal(authorizePcReadOnlyReview({...good(),method}).status,403);
});
test("remote and DNS-rebound Host blocked",()=>{
  for(const host of ["example.org","0.0.0.0:31889","localhost:31889","127.0.0.1.attacker:31889","[::1]:31889"])
    assert.equal(authorizePcReadOnlyReview({...good(),host}).status,403);
});
test("mandatory exact Origin",()=>{
  for(const origin of [null,"http://localhost:31889","https://bad.example"])
    assert.equal(authorizePcReadOnlyReview({...good(),origin}).status,403);
});
test("cross-site Fetch Metadata rejected",()=>{
  for(const fetchSite of ["cross-site","same-site","none",null])
    assert.equal(authorizePcReadOnlyReview({...good(),fetchSite}).status,403);
});
test("no unauthenticated browser-style form POST without custom header",()=>{
  assert.equal(authorizePcReadOnlyReview({...good(),localHeader:null}).status,403);
});
test("JSON body only",()=>{
  for(const contentType of ["text/plain","application/x-www-form-urlencoded",null])
    assert.equal(authorizePcReadOnlyReview({...good(),contentType}).status,415);
});
test("repeat safe gate three times",()=>{
  const values=Array.from({length:3},()=>authorizePcReadOnlyReview(good()));
  assert.deepEqual(values[0],values[1]);
  assert.deepEqual(values[1],values[2]);
});
