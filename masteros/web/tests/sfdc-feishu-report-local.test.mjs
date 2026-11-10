import test from "node:test";
import assert from "node:assert/strict";
import {GET,POST} from "../app/api/sfdc/feishu-report-local/route.js";

function make(method,body,overrides={}){
 const headers={
  "host":"127.0.0.1:3211","origin":"http://127.0.0.1:3211",
  "sec-fetch-site":"same-origin","content-type":"application/json",
  "x-sfdc-command":"1",...overrides
 };
 return new Request("http://127.0.0.1:3211/api/sfdc/feishu-report-local",{
  method,headers,...(method==="POST"?{body:JSON.stringify(body)}:{})
 });
}
async function enabled(fn){
 const original=process.env.SFDC_LOCAL_COMMAND_ENABLED;
 process.env.SFDC_LOCAL_COMMAND_ENABLED="1";
 try{return await fn();}
 finally{
  if(original===undefined)delete process.env.SFDC_LOCAL_COMMAND_ENABLED;
  else process.env.SFDC_LOCAL_COMMAND_ENABLED=original;
 }
}

test("Feishu endpoint blocks off-loopback access",async()=>{
 await enabled(async()=>{
  const r=await GET(make("GET",undefined,{"host":"external.example"}));
  assert.equal(r.status,403);
  assert.equal((await r.json()).code,"LOCAL_ONLY");
 });
});

test("Feishu endpoint rejects cross-origin POST without starting any browser",async()=>{
 await enabled(async()=>{
  const r=await POST(make("POST",{mode:"REFRESH"},{"origin":"http://attacker.example","sec-fetch-site":"cross-site"}));
  assert.equal(r.status,403);
 });
});

test("Feishu endpoint cannot mutate any source records",async()=>{
 await enabled(async()=>{
  for(const mode of ("SAVE","DELETE","UPSERT","WRITE")){
   const r=await POST(make("POST",{mode}));
   assert.equal(r.status,400);
   assert.equal((await r.json()).code,"FEISHU_READ_ONLY_MODE_REQUIRED");
  }
 });
});

test("Account Contact indexed search rejects empty, oversized and unbounded selectors",async()=>{
 await enabled(async()=>{
  for(const body of [
   {mode:"IDENTITY_SEARCH",query:"",limit:20},
   {mode:"IDENTITY_SEARCH",query:"    ",limit:20},
   {mode:"IDENTITY_SEARCH",query:"a".repeat(81),limit:20},
   {mode:"IDENTITY_SEARCH",query:"Kim",limit:500}
  ]){
   const r=await POST(make("POST",body));
   assert.equal(r.status,400);
   assert.equal((await r.json()).code,"IDENTITY_QUERY_INVALID");
  }
 });
});

test("Feishu source query/ID arguments are bounded",async()=>{
 await enabled(async()=>{
  for(const v of [
   {mode:"SEARCH",query:"a".repeat(81),limit:25},
   {mode:"SEARCH",query:"",limit:500},
   {mode:"DETAIL",id:"none"},
   {mode:"DETAIL",id:"QID-INVALID"},
  ]){
   const r=await POST(make("POST",v));
   assert.equal(r.status,400);
  }
 });
});

test("Oppo/Quote reference selection is read-only and validates bounded IDs",async()=>{
 await enabled(async()=>{
  for(const body of [
   {mode:"OPPORTUNITY_SEARCH",query:"a".repeat(81),limit:25},
   {mode:"OPPORTUNITY_SEARCH",query:"mRNA",limit:31},
   {mode:"OPPORTUNITY_QUOTES",opportunityExternal:""},
   {mode:"OPPORTUNITY_QUOTES",opportunityExternal:"006' OR 1=1"}
  ]){
   const r=await POST(make("POST",body));
   assert.equal(r.status,400);
  }
  for(const mode of ["SAVE","UPSERT","CREATE_OPPORTUNITY","CREATE_QUOTE"]){
   const r=await POST(make("POST",{mode}));
   assert.equal(r.status,400);
  }
 });
});
