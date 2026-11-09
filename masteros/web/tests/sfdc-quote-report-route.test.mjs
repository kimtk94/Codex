import test from "node:test";
import assert from "node:assert/strict";
import {GET,POST} from "../app/api/sfdc/report-local/route.js";

function req(method,body,headers={}){
 return new Request("http://127.0.0.1:3211/api/sfdc/report-local",{
  method,
  headers:{
   "host":"127.0.0.1:3211",
   "origin":"http://127.0.0.1:3211",
   "sec-fetch-site":"same-origin",
   "x-sfdc-command":"1",
   "content-type":"application/json",
   ...headers,
  },
  ...(method==="POST"?{body:JSON.stringify(body)}:{})
 });
}
async function enabled(fn){
 const old=process.env.SFDC_LOCAL_COMMAND_ENABLED;
 process.env.SFDC_LOCAL_COMMAND_ENABLED="1";
 try{return await fn();}
 finally{
  if(old===undefined)delete process.env.SFDC_LOCAL_COMMAND_ENABLED;
  else process.env.SFDC_LOCAL_COMMAND_ENABLED=old;
 }
}

test("rejects off-machine Quote report access without reading customer data",async()=>{
 await enabled(async()=>{
  const remote=await GET(req("GET",null,{"host":"example.com"}));
  assert.equal(remote.status,403);
  const cross=await POST(req("POST",{mode:"SEARCH",query:"",limit:25},
   {"origin":"http://other.example","sec-fetch-site":"cross-site"}));
  assert.equal(cross.status,403);
 });
});

test("rejects unsupported report writes and malformed IDs",async()=>{
 await enabled(async()=>{
  for(const body of [
   {mode:"SAVE"},
   {mode:"ISSUE_QUOTE"},
   {mode:"SEARCH",query:"A".repeat(100),limit:25},
   {mode:"SEARCH",query:"",limit:200},
   {mode:"DETAIL",id:"a0P-invented"},
  ]){
   const r=await POST(req("POST",body));
   assert.equal(r.status,400);
   assert.equal((await r.json()).status,"BLOCK");
  }
 });
});

test("disabled local command endpoint cannot serve report contents",async()=>{
 const old=process.env.SFDC_LOCAL_COMMAND_ENABLED;
 process.env.SFDC_LOCAL_COMMAND_ENABLED="0";
 try{
  const r=await POST(req("POST",{mode:"SEARCH",query:"",limit:5}));
  assert.equal(r.status,404);
 }finally{
  if(old===undefined)delete process.env.SFDC_LOCAL_COMMAND_ENABLED;
  else process.env.SFDC_LOCAL_COMMAND_ENABLED=old;
 }
});
