'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const crypto=require('node:crypto');
process.env.VERCEL_ENV='production';
process.env.VERCEL_APP_CLIENT_ID='synthetic-public-client';
process.env.VERCEL_APP_CLIENT_SECRET='synthetic-test-secret';
process.env.CSS_WEB_ACCESS_TOKEN='synthetic-css-owner-api-token';
const callback=require('../api/auth/callback');
const authorize=require('../api/auth/authorize');
const {checkOwner}=require('../lib/lifecycle-owner-auth');
const origin='https://css-sales-workspace-git.vercel.app';
const owner='xSqsomY4s3nWaElLeF9IE89Z';

function request(subject){
 const state='st'.repeat(24),verifier='v'.repeat(48),stamp=String(Math.floor(Date.now()/1000));
 const payload=[state,verifier,stamp].join('.');
 const signature=crypto.createHmac('sha256',process.env.VERCEL_APP_CLIENT_SECRET).update(payload).digest('hex');
 const cookie=Buffer.from(payload).toString('base64url')+'.'+signature;
 return {method:'GET',headers:{host:new URL(origin).host,cookie:'css_oauth_pending='+cookie},
         query:{code:'synthetic-code',state},subject};
}
function response(){
 return {headers:{},setHeader(k,v){this.headers[k]=v;return this},
   status(s){this.statusCode=s;return this},
   json(payload){return {status:this.statusCode||200,json:payload}},
   redirect(code,url){return {status:code,url}},
   end(){return {status:this.statusCode}}};
}

test('Verified owner subject succeeds even without optional email_verified claim',async()=>{
 const old=global.fetch;
 global.fetch=async url=>({
   ok:true,json:async()=>url.includes('/userinfo')?
     {sub:owner}:{access_token:'synthetic-access-token'}
 });
 try{
  const res=response();
  const out=await callback(request(),res);
  assert.equal(out.status,302);
  assert.equal(out.url,origin+'/');
  const cookies=res.headers['Set-Cookie'];
  assert.ok(Array.isArray(cookies));
  const session=cookies.find(x=>x.startsWith('css_oauth_session='));
  assert.ok(session);
  const token=session.match(/^css_oauth_session=([^;]+)/)[1];
  assert.equal(checkOwner({headers:{cookie:'css_oauth_session='+token}},
      process.env.CSS_WEB_ACCESS_TOKEN,process.env.VERCEL_APP_CLIENT_SECRET).oauthValid,true);
 }finally{global.fetch=old}
});
test('Different Vercel subject is denied before owner cookie issuance',async()=>{
 const old=global.fetch;
 global.fetch=async url=>({ok:true,json:async()=>url.includes('/userinfo')?
   {sub:'somebody-else',email_verified:true}:{access_token:'synthetic-token'}});
 try{
  const res=response(),out=await callback(request(),res);
  assert.equal(out.status,302);
  assert.match(out.url,/auth=owner_only/);
  assert.equal(String(res.headers['Set-Cookie']).includes('css_oauth_session'),false);
 }finally{global.fetch=old}
});
test('Provider failure is actionable and never leaks OAuth error_description',async()=>{
 const req={...request(),query:{error:'access_denied',error_description:'private message'}};
 const out=await callback(req,response());
 assert.equal(out.status,302);
 assert.equal(out.url,origin+'/?auth=provider_denied');
});
test('Wrong host canonicalizes before starting OAuth',async()=>{
 const req={method:'GET',headers:{host:'css-sales-workspace-abc123.vercel.app'}};
 const out=await authorize(req,response());
 assert.equal(out.status,302);
 assert.equal(out.url,origin+'/api/auth/authorize');
});
