'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const callback=require('../api/auth/callback');
const {sign}=require('../lib/auth-common');
const {checkOwner}=require('../lib/lifecycle-owner-auth');
const host='css-sales-workspace-git.vercel.app';
const owner='xSqsomY4s3nWaElLeF9IE89Z';
function response(){
 return {statusCode:200,headers:{},url:null,body:null,
   setHeader(n,v){this.headers[n.toLowerCase()]=v;return this},
   status(n){this.statusCode=n;return this},
   json(v){this.body=v;return this},
   redirect(n,v){this.statusCode=n;this.url=v;return this},
   end(){return this}};
}
async function environ(run){
 const keys=['VERCEL_ENV','VERCEL_APP_CLIENT_ID','VERCEL_APP_CLIENT_SECRET'];
 const before=keys.map(k=>process.env[k]),originalFetch=global.fetch;
 const originalWarn=console.warn;
 process.env.VERCEL_ENV='production';
 process.env.VERCEL_APP_CLIENT_ID='synthetic-public-id';
 process.env.VERCEL_APP_CLIENT_SECRET='synthetic-secret';
 const captured=[];
 console.warn=(...args)=>captured.push(args.join(' '));
 try{return await run({captured});}
 finally{
  keys.forEach((k,i)=>{if(before[i]===undefined)delete process.env[k];else process.env[k]=before[i]});
  global.fetch=originalFetch;console.warn=originalWarn;
 }
}
function request(){
 const state='safe'.repeat(12),stamp=String(Math.floor(Date.now()/1000));
 const payload=[state,'synthetic-verifier',stamp].join('.');
 const signed=Buffer.from(payload).toString('base64url')+'.'+sign(payload);
 return{method:'GET',headers:{host,cookie:'css_oauth_pending='+signed},
   query:{state,code:'synthetic-code'}};
}

test('callback reports token exchange stage without leaking credentials or original provider error',async()=>{
 await environ(async({captured})=>{
  global.fetch=async()=>({ok:false,status:401,text:async()=>('do-not-log-private-token')});
  const r=response();
  await callback(request(),r);
  assert.equal(r.statusCode,302);
  assert.equal(r.url,'https://'+host+'/?login=failed');
  assert.deepEqual(captured,['CSS_OAUTH_CALLBACK_FAILURE stage=TOKEN_EXCHANGE_FAILED']);
  assert.ok(!JSON.stringify(captured).includes('synthetic-secret'));
  assert.ok(!JSON.stringify(captured).includes('synthetic-code'));
  assert.ok(!JSON.stringify(captured).includes('private-token'));
 });
});
test('callback reports userinfo stage without logging access token',async()=>{
 await environ(async({captured})=>{
  let calls=0;
  global.fetch=async()=>++calls===1?{ok:true,json:async()=>({access_token:'synthetic-access'})}:{ok:false,status:403};
  const r=response();
  await callback(request(),r);
  assert.equal(r.url,'https://'+host+'/?login=failed');
  assert.equal(calls,2);
  assert.deepEqual(captured,['CSS_OAUTH_CALLBACK_FAILURE stage=USERINFO_LOOKUP_FAILED']);
  assert.ok(!JSON.stringify(captured).includes('synthetic-access'));
 });
});
test('missing authorization code has separate safe stage and does not call token provider',async()=>{
 await environ(async({captured})=>{
  global.fetch=async()=>{throw Error('must not call provider')};
  const req=request();delete req.query.code;
  const r=response();
  await callback(req,r);
  assert.equal(r.statusCode,302);
  assert.deepEqual(captured,['CSS_OAUTH_CALLBACK_FAILURE stage=CALLBACK_CODE_STATE_OR_COOKIE_MISSING']);
 });
});
test('valid callback cookie satisfies existing lifecycle owner validation',async()=>{
 await environ(async({captured})=>{
  let calls=0;
  global.fetch=async()=>{
    calls++;
    if(calls===1)return {ok:true,json:async()=>({access_token:'synthetic-access'})};
    return {ok:true,json:async()=>({sub:owner,email_verified:true})};
  };
  const r=response();
  await callback(request(),r);
  assert.equal(r.statusCode,302);
  assert.equal(r.url,'https://'+host+'/');
  assert.equal(calls,2);
  const all=r.headers['set-cookie'];
  assert.ok(Array.isArray(all));
  const session=all.find(c=>c.startsWith('css_oauth_session='));
  assert.ok(session);
  assert.match(session,/Path=\/api\/lifecycle;/);
  const header=session.split(';',1)[0];
  const checked=checkOwner({headers:{cookie:header}},'synthetic-owner-token','synthetic-secret');
  assert.equal(checked.valid,true);
  assert.equal(checked.oauthValid,true);
  assert.deepEqual(captured,[]);
 });
});
