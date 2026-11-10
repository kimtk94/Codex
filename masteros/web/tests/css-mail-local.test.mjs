import test from "node:test";
import assert from "node:assert/strict";
import {authorizeCssMailLocal,parseLocalMailAction,validateLocalMailResult} from "../lib/css-mail-local.mjs";

const base={enabled:true,method:"GET",host:"127.0.0.1:3000",
  origin:"http://127.0.0.1:3000",fetchSite:"same-origin",header:"1"};

test("loopback mail reading requires explicit header and same origin",()=>{
  assert.equal(authorizeCssMailLocal(base).ok,true);
  for(const bad of [{enabled:false},{host:"localhost:3000"},{host:"evil.com:3000"},
    {header:""},{fetchSite:"cross-site"},{origin:"http://evil.com:3000"},
    {method:"PUT"}])assert.equal(authorizeCssMailLocal({...base,...bad}).ok,false);
});
test("POST requires same-origin JSON",()=>{
  assert.equal(authorizeCssMailLocal({...base,method:"POST",contentType:"application/json"}).ok,true);
  for(const bad of [{origin:null},{contentType:"text/plain"},{fetchSite:"cross-site"}])
    assert.equal(authorizeCssMailLocal({...base,method:"POST",
      contentType:"application/json",...bad}).ok,false);
});
test("only known actions, no user controlled code arguments",()=>{
  const input={mode:"decision",action:"SKIP_CC_TO",key:"INBOX|123|456",
    uid:"inbox:456",target:"colleague@novogene.com"};
  assert.deepEqual(parseLocalMailAction(input),input);
  for(const change of [{action:"SEND_MAIL"},{extra:"arbitrary"},{note:"x".repeat(301)}])
    assert.throws(()=>parseLocalMailAction({...input,...change}));
});
test("response needs list counts and rejects misleading PASS",()=>{
  assert.deepEqual(validateLocalMailResult({status:"PASS",result:"MAIL_SKIPPED"},"decision"),
    {status:"PASS",result:"MAIL_SKIPPED"});
  assert.throws(()=>validateLocalMailResult({status:"PASS",mail:[],leads:[]},"snapshot"));
  const good={status:"STALE",mail:[],leads:[],rules:[],skippedMails:[],
    mailCount:0,leadCount:0};
  assert.equal(validateLocalMailResult(good,"snapshot").status,"STALE");
});
