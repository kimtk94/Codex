import test from "node:test";
import assert from "node:assert/strict";
import {GET,POST} from "../app/api/sfdc/cache-local/route.js";

function req(method,body,overrides={}){
  const headers={
    "host":"127.0.0.1:3211",
    "origin":"http://127.0.0.1:3211",
    "sec-fetch-site":"same-origin",
    "x-sfdc-command":"1",
    "content-type":"application/json",
    ...overrides
  };
  return new Request("http://127.0.0.1:3211/api/sfdc/cache-local",{
    method,headers,...(method==="POST"?{body:JSON.stringify(body)}:{})
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

test("cache status refuses non-loopback hosts and missing auth header",async()=>{
  await enabled(async()=>{
    const bad=await GET(req("GET",null,{"host":"example.com"}));
    assert.equal(bad.status,403);
    assert.equal((await bad.json()).code,"LOCAL_ONLY");
    const noHeader=await GET(req("GET",null,{"x-sfdc-command":""}));
    assert.equal(noHeader.status,403);
  });
});

test("cache prefetch refuses cross-site calls before starting Python",async()=>{
  await enabled(async()=>{
    const bad=await POST(req("POST",{mode:"WARM",limit:3,offset:0},{
      "origin":"http://attacker.example","sec-fetch-site":"cross-site"}));
    assert.equal(bad.status,403);
  });
});

test("cache prefetch cannot be used to request a Salesforce SAVE",async()=>{
  await enabled(async()=>{
    for(const b of [
      {mode:"SAVE",limit:3,offset:0},
      {mode:"WARM",limit:100,offset:0},
      {mode:"WARM",limit:3,offset:-1},
      {mode:"WARM",limit:3,offset:0.25},
    ]){
      const r=await POST(req("POST",b));
      assert.equal(r.status,400);
      assert.equal((await r.json()).status,"BLOCK");
    }
  });
});

test("cache API is disabled unless the local Salesforce gate is enabled",async()=>{
  const old=process.env.SFDC_LOCAL_COMMAND_ENABLED;
  process.env.SFDC_LOCAL_COMMAND_ENABLED="0";
  try{
    const r=await POST(req("POST",{mode:"WARM",limit:3,offset:0}));
    assert.equal(r.status,404);
  }finally{
    if(old===undefined)delete process.env.SFDC_LOCAL_COMMAND_ENABLED;
    else process.env.SFDC_LOCAL_COMMAND_ENABLED=old;
  }
});
