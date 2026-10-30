'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {oauthOrigin,matchesOriginHost,sign}=require('../lib/auth-common');
const authorize=require('../api/auth/authorize');
const callback=require('../api/auth/callback');

const PROD='https://css-sales-workspace-git.vercel.app';
const PREVIEW='css-sales-workspace-az0arelhv-insk1285-9320s-projects.vercel.app';

function withEnv(pairs,body){
 const names=Object.keys(pairs),previous=Object.fromEntries(names.map(k=>[k,process.env[k]]));
 for(const k of names)if(pairs[k]===null)delete process.env[k];else process.env[k]=pairs[k];
 const restore=()=>{for(const k of names)if(previous[k]===undefined)delete process.env[k];else process.env[k]=previous[k]};
 try{
   const answer=body();
   return answer&&typeof answer.then==='function'?answer.finally(restore):(restore(),answer);
 }catch(err){restore();throw err}
}
function response(){
 return {statusCode:200,headers:{},url:null,data:null,
   setHeader(name,value){this.headers[name.toLowerCase()]=value;return this},
   status(code){this.statusCode=code;return this},
   json(data){this.data=data;return this},
   redirect(code,url){this.statusCode=code;this.url=url;return this},
   end(){return this},
 };
}
test('production uses canonical registered callback, not an arbitrary VERCEL_URL',()=>{
 assert.equal(oauthOrigin({VERCEL_ENV:'production',VERCEL_URL:'evil.vercel.app'}),PROD);
 assert.equal(oauthOrigin({VERCEL_ENV:'preview',VERCEL_URL:PREVIEW}),'https://'+PREVIEW);
 assert.equal(oauthOrigin({VERCEL_ENV:'preview',VERCEL_URL:'evil.vercel.app'}),null);
 assert.equal(oauthOrigin({VERCEL_ENV:'preview',VERCEL_URL:'css-sales-workspace-abc.vercel.app.evil.test'}),null);
 assert.equal(oauthOrigin({VERCEL_ENV:'preview',VERCEL_URL:'https://'+PREVIEW}),null);
 assert.equal(oauthOrigin({VERCEL_ENV:'preview',VERCEL_URL:PREVIEW+'/unexpected'}),null);
 assert.equal(matchesOriginHost({headers:{host:PREVIEW}},'https://'+PREVIEW),true);
 assert.equal(matchesOriginHost({headers:{host:'attacker.vercel.app'}},'https://'+PREVIEW),false);
});
test('preview authorization has same-deployment callback and secure scoped pending cookie',async()=>{
 await withEnv({VERCEL_ENV:'preview',VERCEL_URL:PREVIEW,VERCEL_APP_CLIENT_ID:'fake-public-client',VERCEL_APP_CLIENT_SECRET:'unit-only-secret'},async()=>{
   const r=response();
   await authorize({method:'GET',headers:{host:PREVIEW}},r);
   assert.equal(r.statusCode,302);
   const dest=new URL(r.url);
   assert.equal(dest.hostname,'vercel.com');
   assert.equal(dest.searchParams.get('redirect_uri'),'https://'+PREVIEW+'/api/auth/callback');
   assert.match(r.headers['set-cookie'],/^css_oauth_pending=/);
   assert.match(r.headers['set-cookie'],/HttpOnly; Secure; SameSite=Lax/);
   assert.match(r.headers['set-cookie'],/Path=\/api\/auth/);
 });
});
test('preview OAuth is refused when deployment hostname unavailable or request host mismatched',async()=>{
 await withEnv({VERCEL_ENV:'preview',VERCEL_URL:null},async()=>{
   let r=response();
   await authorize({method:'GET',headers:{host:PREVIEW}},r);
   assert.equal(r.statusCode,503);
   assert.equal(r.data.error,'PREVIEW_ORIGIN_UNAVAILABLE');
   assert.equal(r.url,null);
 });
 await withEnv({VERCEL_ENV:'preview',VERCEL_URL:PREVIEW},async()=>{
   let r=response();
   await authorize({method:'GET',headers:{host:'attacker.vercel.app'}},r);
   assert.equal(r.statusCode,409);
   assert.equal(r.data.error,'OAUTH_ORIGIN_MISMATCH');
   r=response();
   await callback({method:'GET',headers:{host:'attacker.vercel.app'},query:{}},r);
   assert.equal(r.statusCode,409);
   assert.equal(r.data.error,'OAUTH_ORIGIN_MISMATCH');
 });
});
test('preview callback issues owner cookie for same deployment and keeps code/verifier tied to URI',async()=>{
 await withEnv({VERCEL_ENV:'preview',VERCEL_URL:PREVIEW,VERCEL_APP_CLIENT_ID:'fake-public-client',VERCEL_APP_CLIENT_SECRET:'unit-only-secret'},async()=>{
   const state='abc'.repeat(16),verifier='unit-verifier',issued=String(Math.floor(Date.now()/1000));
   const payload=[state,verifier,issued].join('.');
   const pending=Buffer.from(payload).toString('base64url')+'.'+sign(payload);
   const orig=global.fetch,requests=[];
   global.fetch=async(url,opts)=>{
     requests.push({url:String(url),body:String(opts?.body||'')});
     if(String(url).endsWith('/oauth/token'))
       return {ok:true,json:async()=>({access_token:'synthetic-test-access'})};
     if(String(url).endsWith('/oauth/userinfo'))
       return {ok:true,json:async()=>({sub:'xSqsomY4s3nWaElLeF9IE89Z',email_verified:true})};
     throw new Error('UNEXPECTED_OAUTH_URL');
   };
   try{
     const r=response();
     await callback({method:'GET',headers:{host:PREVIEW,cookie:'css_oauth_pending='+pending},query:{code:'fake-test-code',state}},r);
     assert.equal(r.statusCode,302);
     assert.equal(r.url,'https://'+PREVIEW+'/');
     assert.match(requests[0].body,/redirect_uri=https%3A%2F%2Fcss-sales-workspace-/);
     assert.equal(new URLSearchParams(requests[0].body).get('redirect_uri'),'https://'+PREVIEW+'/api/auth/callback');
     assert.ok(Array.isArray(r.headers['set-cookie']));
     assert.ok(r.headers['set-cookie'].some(x=>x.startsWith('css_oauth_session=')&&x.includes('Path=/api/lifecycle')&&x.includes('HttpOnly')));
   }finally{global.fetch=orig;}
 });
});
test('production authorize still uses canonical callback',async()=>{
 await withEnv({VERCEL_ENV:'production',VERCEL_URL:PREVIEW,VERCEL_APP_CLIENT_ID:'fake-public-client',VERCEL_APP_CLIENT_SECRET:'unit-only-secret'},async()=>{
   const r=response();await authorize({method:'GET',headers:{host:'css-sales-workspace-git.vercel.app'}},r);
   assert.equal(r.statusCode,302);
   assert.equal(new URL(r.url).searchParams.get('redirect_uri'),PROD+'/api/auth/callback');
 });
});
