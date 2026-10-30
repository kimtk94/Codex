'use strict';
/**
 * Credential-free contract tests for owner-only UID mail-review POST.
 * No live credentials, client mail, Salesforce action, or Google Sheet writes.
 */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const crypto=require('node:crypto');
const realRules=require('../lib/mail-review-decision');

const source=fs.readFileSync(path.join(__dirname,'..','api','lifecycle','review.js'),'utf8');
const HEADER=['Decision (Edit)','Sender Email','When','Age','Mail UID (Key)',
  'Queue','Reviewer Note (Edit)','Decision Sync Status','Snapshot','Subject'];

function loadHarness({flag='true',current='NONE',currentStatus='NOT_SUBMITTED',
                     sender='client@example.edu'}={}){
  const state={
    rows:[HEADER.slice(),[current,sender,'2026-10-30T09:00',1,'inbox:401',
      'REVIEW','',''+currentStatus,'2026-10-30','Private Subject']],
    writes:[],reads:[],authUsed:0,
  };
  class MockGoogleAuth {
    constructor(config){
      assert.deepEqual(config.scopes,['https://www.googleapis.com/auth/spreadsheets']);
    }
    async getClient(){
      state.authUsed++;
      return {
        async request(options){
          const decoded=decodeURIComponent(options.url);
          if(options.method==='POST'){
            assert.match(decoded,/\/values:batchUpdate$/);
            assert.equal(options.data.valueInputOption,'RAW');
            const updates=options.data.data;
            assert.equal(updates.length,2);
            const allow=["'Email Review Decisions'!A2","'Email Review Decisions'!H2"];
            assert.deepEqual(updates.map(u=>u.range),allow);
            state.writes.push(updates);
            state.rows[1][0]=updates[0].values[0][0];
            state.rows[1][7]=updates[1].values[0][0];
            return {data:{}};
          }
          assert.equal(options.method,undefined);
          state.reads.push(decoded);
          if(decoded.includes('!A1:J1300'))return {data:{values:state.rows}};
          if(decoded.includes('!A2:H2'))return {data:{values:[state.rows[1].slice(0,8)]}};
          throw Error('Unexpected lookup '+decoded);
        }
      };
    }
  }
  const moduleObj={exports:{}}, env={
    CSS_WEB_ACCESS_TOKEN:'test_owner_token',
    CSS_WEB_DECISIONS_ENABLED:flag,
    GOOGLE_SERVICE_ACCOUNT_JSON:'{}',
    VERCEL_APP_CLIENT_SECRET:'local_not_live',
  };
  const runner=new vm.Script('(function(require,module,exports,process,Buffer,URL,Date){'+source+'\n})');
  const f=runner.runInNewContext();
  f(name=>{
    if(name==='google-auth-library')return {GoogleAuth:MockGoogleAuth};
    if(name==='../../lib/mail-review-decision')return realRules;
    return require(name);
  },moduleObj,moduleObj.exports,{env},Buffer,URL,Date);
  return {handler:moduleObj.exports,state};
}

function request(body={uid:'inbox:401',action:'EXCLUDE_MAIL',expectedDecision:'NONE'}){
  return {
    method:'POST',
    headers:{
      authorization:'Bearer test_owner_token',
      host:'css-sales-workspace-git.vercel.app',
      origin:'https://css-sales-workspace-git.vercel.app',
      'sec-fetch-site':'same-origin',
      'x-css-review-confirm':'EXPLICIT_USER_APPROVAL',
      'content-type':'application/json'
    },
    body
  };
}
function response(){
  return {headers:{},code:0,body:null,
    setHeader(k,v){this.headers[k]=v;},
    status(code){this.code=code;return this;},
    json(payload){this.body=payload;return this;}
  };
}
async function send(harness,req=request()){
  const res=response();
  await harness.handler(req,res);
  return res;
}

test('unauthenticated clients cannot read/write manual Decisions',async()=>{
  const h=loadHarness();
  const q=request();delete q.headers.authorization;
  const res=await send(h,q);
  assert.equal(res.code,401);
  assert.equal(res.body.error,'OWNER_AUTH_REQUIRED');
  assert.equal(h.state.authUsed,0);
  assert.equal(h.state.writes.length,0);
});

test('disabled-by-default safety flag blocks even valid owner',async()=>{
  const h=loadHarness({flag:'false'});
  const res=await send(h);
  assert.equal(res.code,503);
  assert.equal(res.body.error,'MANUAL_DECISIONS_NOT_ENABLED');
  assert.equal(h.state.authUsed,0);
});

test('cross-origin and missing manual approval fail closed',async()=>{
  const h=loadHarness();
  const cross=request();cross.headers.origin='https://attacker.example';
  assert.equal((await send(h,cross)).code,403);
  const missing=request();delete missing.headers['x-css-review-confirm'];
  assert.equal((await send(h,missing)).code,403);
  assert.equal(h.state.authUsed,0);
  assert.equal(h.state.writes.length,0);
});

test('GET is rejected before source access',async()=>{
  const h=loadHarness();const q=request();q.method='GET';
  const res=await send(h,q);
  assert.equal(res.code,405);
  assert.equal(res.body.error,'METHOD_NOT_ALLOWED');
  assert.equal(h.state.authUsed,0);
});

test('stale existing action refuses overwrite of reviewer Choice',async()=>{
  const h=loadHarness({current:'EXCLUDE_MAIL',currentStatus:'SYNCED:EXCLUDE_MAIL'});
  const res=await send(h);
  assert.equal(res.code,409);
  assert.equal(res.body.error,'REVIEW_DECISION_CHANGED');
  assert.equal(h.state.writes.length,0);
});

test('owner explicit review writes only A and H, then verifies readback',async()=>{
  const h=loadHarness();
  const res=await send(h);
  assert.equal(res.code,200);
  assert.equal(res.body.status,'QUEUED_FOR_EXISTING_GITHUB_SYNC');
  assert.equal(res.body.uid,'inbox:401');
  assert.equal(res.body.decision,'EXCLUDE_MAIL');
  assert.equal(res.body.synced,false);
  assert.equal(h.state.writes.length,1);
  assert.equal(h.state.rows[1][0],'EXCLUDE_MAIL');
  assert.equal(h.state.rows[1][7],'NOT_SUBMITTED');
  assert.equal(h.state.rows[1][6],'');
  assert.equal(h.state.rows[1][9],'Private Subject');
  assert.equal(h.state.reads.length,2);
});

test('unchanged explicit decision is idempotent, never re-queued',async()=>{
  const h=loadHarness({current:'EXCLUDE_MAIL',currentStatus:'SYNCED:EXCLUDE_MAIL'});
  const res=await send(h,request({uid:'inbox:401',action:'EXCLUDE_MAIL',
    expectedDecision:'EXCLUDE_MAIL'}));
  assert.equal(res.code,200);
  assert.equal(res.body.status,'ALREADY_SELECTED');
  assert.equal(res.body.synced,true);
  assert.equal(h.state.writes.length,0);
});

test('invalid arbitrary action and extra payload cannot trigger any write',async()=>{
  const h=loadHarness();
  for(const body of [
    {uid:'inbox:401',action:'SEND_MAIL',expectedDecision:'NONE'},
    {uid:'inbox:401',action:'EXCLUDE_MAIL',expectedDecision:'NONE',recipient:'x@example.edu'},
    {uid:'../../etc',action:'EXCLUDE_MAIL',expectedDecision:'NONE'},
  ]){
    const res=await send(h,request(body));
    assert.equal(res.code,400);
  }
  assert.equal(h.state.authUsed,0);
  assert.equal(h.state.writes.length,0);
});

test('sender-wide action fails when address is not a verified sender',async()=>{
  const h=loadHarness({sender:'unknown'});
  const res=await send(h,request({uid:'inbox:401',action:'EXCLUDE_SENDER',
     expectedDecision:'NONE'}));
  assert.equal(res.code,409);
  assert.equal(res.body.error,'SENDER_ADDRESS_NOT_VERIFIED');
  assert.equal(h.state.writes.length,0);
});
