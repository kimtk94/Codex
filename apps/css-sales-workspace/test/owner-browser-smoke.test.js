'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const crypto=require('node:crypto');
const ROOT=path.join(__dirname,'..');
const OWNER='xSqsomY4s3nWaElLeF9IE89Z';
const SECRET='unit-only-vercel-app-secret';
const TOKEN='unit-only-web-owner-token';
const UID='inbox:12345';
function oauthCookie(){
 const expires=String(Math.floor(Date.now()/1000)+3600);
 const hmac=crypto.createHmac('sha256',SECRET)
   .update('oauth-session:'+OWNER+':'+expires).digest('hex');
 return 'css_oauth_session='+OWNER+'.'+expires+'.'+hmac;
}
function response(){
 return {headers:{},statusCode:200,data:null,
  setHeader(k,v){this.headers[k.toLowerCase()]=v;return this},
  status(s){this.statusCode=s;return this},
  json(data){this.data=data;return this},
  end(){return this}
 };
}
function harness({verified=true,brokenBody=false,deniedSource=false}={}){
 let lifecycleCalls=0,bodyCalls=0,googleCalls=0;
 const state={};
 class GoogleAuth{async getClient(){googleCalls++;return{getAccessToken:async()=>({token:'mock-google-access'})}}}
 const lifecycle=async(req,res)=>{
   lifecycleCalls++;
   if(req.headers.authorization)throw Error('Bearer header must not be present');
   return res.status(200).json({revenueNetStatus:verified?'VERIFIED':'NOT_VERIFIED',
     months:[{month:'2026-10',netRevenue:144129000}]});
 };
 const bodyHandler=async(req,res)=>{
   bodyCalls++;
   return res.status(brokenBody?404:200).json(
     brokenBody?{error:'BODY_NOT_AVAILABLE'}:
     {uid:req.query.uid,body:'private customer text never returned to caller',
      classification:'WEB_REVIEW_CACHE'});
 };
 const fetch=async url=>{
   if(deniedSource)return{ok:false,status:503};
   assert.ok(String(url).includes('/values:batchGet?'));
   return {ok:true,json:async()=>({valueRanges:[
     {values:[['Mail UID'],[UID]]},
     {values:[['Classification'],['WEB_REVIEW_CACHE']]}
   ]})};
 };
 const raw=fs.readFileSync(path.join(ROOT,'api/lifecycle/owner-smoke.js'),'utf8');
 const module={exports:{}};
 const sandbox={module,exports:module.exports,process:{env:{
    CSS_WEB_ACCESS_TOKEN:TOKEN,VERCEL_APP_CLIENT_SECRET:SECRET,
    GOOGLE_SERVICE_ACCOUNT_JSON:'{}'
   }},fetch,AbortSignal,Buffer,console,Date,
   require(x){
     if(x==='google-auth-library')return {GoogleAuth};
     if(x==='../../lib/lifecycle-owner-auth')return require('../lib/lifecycle-owner-auth');
     if(x==='../lifecycle.js')return lifecycle;
     if(x==='./mail-body.js')return bodyHandler;
     throw Error('Forbidden import '+x);
   }
 };
 vm.runInNewContext(raw,sandbox,{filename:'owner-smoke.js'});
 state.handler=module.exports;
 state.calls=()=>({lifecycleCalls,bodyCalls,googleCalls});
 return state;
}
async function invoke(h,cookie,method='GET',headers={}){
 const r=response();
 await h.handler({method,headers:{...headers,...(cookie?{cookie}:{})}},r);
 return r;
}
test('browser smoke accepts signed Vercel owner OAuth and returns no customer metadata',async()=>{
 const x=harness();
 const r=await invoke(x,oauthCookie());
 assert.equal(r.statusCode,200);
 assert.equal(r.data.state,'PASS');
 assert.equal(r.data.auth,'VERCEL_OWNER_OAUTH');
 assert.equal(r.data.lifecycle,'LIVE_SHEETS_VERIFIED');
 assert.equal(r.data.revenue,'VAT_EXCLUDED_PARITY_VERIFIED');
 assert.equal(r.data.mailBody,'EXACT_UID_BODY_VERIFIED');
 assert.equal(r.data.productionPromotion,false);
 assert.equal(r.headers['cache-control'],'private, no-store');
 assert.equal(r.headers['x-content-type-options'],'nosniff');
 const serialized=JSON.stringify(r.data);
 assert.ok(!serialized.includes(UID));
 assert.ok(!serialized.includes('private customer text'));
 assert.ok(!serialized.includes(TOKEN));
 assert.deepEqual(x.calls(),{lifecycleCalls:1,bodyCalls:1,googleCalls:1});
});
test('bearer-only, unsigned cookie and anonymous calls cannot run smoke',async()=>{
 const x=harness();
 for(const [cookie,headers] of [[null,{authorization:'Bearer '+TOKEN}],['css_oauth_session=invalid',{}],[null,{}]]){
   const r=await invoke(x,cookie,'GET',headers);
   assert.equal(r.statusCode,401);
   assert.equal(r.data.error,'VERCEL_OWNER_OAUTH_REQUIRED');
 }
 assert.deepEqual(x.calls(),{lifecycleCalls:0,bodyCalls:0,googleCalls:0});
});
test('only GET is permitted; source failures hide internal data',async()=>{
 const x=harness({deniedSource:true});
 assert.equal((await invoke(x,oauthCookie(),'POST')).statusCode,405);
 const r=await invoke(x,oauthCookie());
 assert.equal(r.statusCode,503);
 assert.equal(r.data.error,'OWNER_LIVE_DIAGNOSTIC_FAILED');
 assert.equal(r.data.productionPromotion,false);
 assert.ok(!JSON.stringify(r.data).includes(UID));
});
test('stale net revenue or missing MIME fails closed',async()=>{
 const missingRevenue=await invoke(harness({verified:false}),oauthCookie());
 assert.equal(missingRevenue.statusCode,503);
 const missingBody=await invoke(harness({brokenBody:true}),oauthCookie());
 assert.equal(missingBody.statusCode,503);
});
test('UID selection relies on exact source classification and verified schema',()=>{
 const x=harness();
 const pick=x.handler.findCachedUid;
 assert.equal(pick([['Mail UID'],[UID]],[['Classification'],['WEB_REVIEW_CACHE']]),UID);
 assert.throws(()=>pick([['Mail UID'],[UID]],[['Bad Header'],['WEB_REVIEW_CACHE']]),/SCHEMA/);
 assert.throws(()=>pick([['Mail UID'],[UID]],[['Classification'],['BODY_EMPTY_MIME']]),/NO_VERIFIED_BODY/);
});
test('button is OAuth-only, no browser bearer, no writing or release promotion',()=>{
 const html=fs.readFileSync(path.join(ROOT,'index.html'),'utf8');
 const source=fs.readFileSync(path.join(ROOT,'api/lifecycle/owner-smoke.js'),'utf8');
 assert.ok(html.includes('id="ownerSmoke" type="button" disabled'));
 assert.ok(html.includes("fetch('/api/lifecycle/owner-smoke',{credentials:'same-origin',cache:'no-store'})"));
 assert.ok(source.includes("if(!owner.oauthValid)"));
 assert.ok(!source.includes('sheets.googleapis.com/v4/spreadsheets/'+ 'x:batchUpdate'));
 assert.ok(!source.includes('request_promote'));
});
