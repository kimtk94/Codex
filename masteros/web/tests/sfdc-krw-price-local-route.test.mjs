import test from "node:test";
import assert from "node:assert/strict";
import {POST} from "../app/api/sfdc/krw-price-local/route.js";

const host="127.0.0.1:3019";
const url="http://"+host+"/api/sfdc/krw-price-local";
function request(origin=url.replace(/\/api\/.*/,""),body={mode:"READ_LOCAL_PRIVATE_2026_KRW"}){
 return new Request(url,{method:"POST",headers:{
  Host:host,Origin:origin,"Sec-Fetch-Site":"same-origin",
  "X-SFDC-Command":"1","Content-Type":"application/json"
 },body:JSON.stringify(body)});
}

test("private local price index is disabled without separate explicit read-only opt-in",async()=>{
 const previous=process.env.SFDC_KRW_PRICE_LOCAL_READ_ENABLED;
 try{
  process.env.SFDC_KRW_PRICE_LOCAL_READ_ENABLED="0";
  const response=await POST(request());
  const answer=await response.json();
  assert.equal(response.status,404);
  assert.equal(answer.code,"LOCAL_COMMAND_DISABLED");
  assert.equal(answer.salesforce_write,false);
 }finally{
  if(previous===undefined)delete process.env.SFDC_KRW_PRICE_LOCAL_READ_ENABLED;
  else process.env.SFDC_KRW_PRICE_LOCAL_READ_ENABLED=previous;
 }
});

test("private price readback rejects foreign origin and malformed payloads without reading CRM",async()=>{
 const previous=process.env.SFDC_KRW_PRICE_LOCAL_READ_ENABLED;
 try{
  process.env.SFDC_KRW_PRICE_LOCAL_READ_ENABLED="1";
  const wrong=await POST(request("http://evil.example"));
  assert.equal(wrong.status,403);
  assert.equal((await wrong.json()).code,"ORIGIN_REJECTED");
  const bad=await POST(request(undefined,{mode:"SAVE_SFDC"}));
  assert.equal(bad.status,400);
  assert.equal((await bad.json()).code,"INVALID_LOCAL_PRICE_REQUEST");
 }finally{
  if(previous===undefined)delete process.env.SFDC_KRW_PRICE_LOCAL_READ_ENABLED;
  else process.env.SFDC_KRW_PRICE_LOCAL_READ_ENABLED=previous;
 }
});

test("missing private source fails closed and never returns invented prices",async()=>{
 const flag=process.env.SFDC_KRW_PRICE_LOCAL_READ_ENABLED;
 const dir=process.env.LOCALAPPDATA;
 try{
  process.env.SFDC_KRW_PRICE_LOCAL_READ_ENABLED="1";
  process.env.LOCALAPPDATA="/tmp/absent-private-krw-index-tests-no-price";
  const response=await POST(request());
  const answer=await response.json();
  assert.equal(response.status,503);
  assert.equal(answer.code,"PRIVATE_KRW_INDEX_STALE_OR_INVALID");
  assert.equal(answer.salesforce_write,false);
  assert.equal(answer.evidence,undefined);
 }finally{
  if(flag===undefined)delete process.env.SFDC_KRW_PRICE_LOCAL_READ_ENABLED;
  else process.env.SFDC_KRW_PRICE_LOCAL_READ_ENABLED=flag;
  if(dir===undefined)delete process.env.LOCALAPPDATA;
  else process.env.LOCALAPPDATA=dir;
 }
});
