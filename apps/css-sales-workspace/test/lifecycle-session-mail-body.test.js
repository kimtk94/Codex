'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const crypto=require('node:crypto');
const root=path.join(__dirname,'..');
const {checkOwner,ownerSessionCookie}=require('../lib/lifecycle-owner-auth');

const SECRET='test-owner-secret';
const OWNER='xSqsomY4s3nWaElLeF9IE89Z';
const NOW=1919650000;

function sign(value,key){
 return crypto.createHmac('sha256',key).update(value).digest('hex');
}
test('owner session cookie signed by server survives round trip',()=>{
 const cookie=ownerSessionCookie(SECRET,NOW).split(';')[0];
 assert.equal(checkOwner({headers:{cookie}},SECRET,null,NOW+120).valid,true);
 assert.equal(checkOwner({headers:{cookie:cookie.replace(/.$/,'f')}},SECRET,null,NOW+120).valid,false);
 assert.equal(checkOwner({headers:{cookie}},SECRET,null,NOW+86401).valid,false);
});
test('Vercel OAuth callback cookie authenticates only expected owner',()=>{
 const expiry=String(NOW+3600),key='test-vercel-secret';
 const cookie='css_oauth_session='+OWNER+'.'+expiry+'.'+sign('oauth-session:'+OWNER+':'+expiry,key);
 assert.equal(checkOwner({headers:{cookie}},SECRET,key,NOW).valid,true);
 assert.equal(checkOwner({headers:{cookie}},SECRET,'wrong-secret',NOW).valid,false);
 assert.equal(checkOwner({headers:{cookie}},SECRET,key,NOW+3700).valid,false);
 const outsider=cookie.replace(OWNER,'differentowner');
 assert.equal(checkOwner({headers:{cookie:outsider}},SECRET,key,NOW).valid,false);
});
test('bearer header remains separate; missing, empty and incorrect fail closed',()=>{
 assert.equal(checkOwner({headers:{authorization:'Bearer '+SECRET}},SECRET,null,NOW).valid,true);
 assert.equal(checkOwner({headers:{authorization:'Bearer wrong'}},SECRET,null,NOW).valid,false);
 assert.equal(checkOwner({headers:{}},SECRET,null,NOW).valid,false);
});

function harness(sourcePath,{uids=[],body='Read-only personal mail body',classification='WEB_REVIEW_CACHE',badRow=false,broken=false}={}){
 const source=fs.readFileSync(path.join(root,sourcePath),'utf8');
 const row=new Array(22).fill('');
 row[0]=badRow?'inbox:99':'inbox:40123';
 row[9]=body;row[21]=classification;
 const uidRows=[['Mail UID'],...Array.from({length:1050},()=>[])];
 for(const [i,id] of uids)uidRows[i-1]=[id];
 const reads=[];
 class MockAuth{
   async getClient(){return {getAccessToken:async()=>({token:'fake-mock-token'})}}
 }
 const mockFetch=async url=>{
   const range=decodeURIComponent(url.split('/values/')[1]||'');
   reads.push(range);
   if(broken)return {ok:false,status:503};
   if(range==="'CSS Mail Inbox Raw'!A1:A10000")return {ok:true,json:async()=>({values:uidRows})};
   if(range==="'CSS Mail Inbox Raw'!A1050:V1050")return {ok:true,json:async()=>({values:[row]})};
   throw Error('Unexpected Sheets range '+range);
 };
 const moduleObj={exports:{}},sandbox={
   require:p=>{
     if(p==='google-auth-library')return {GoogleAuth:MockAuth};
     if(p==='../../lib/lifecycle-owner-auth')return require('../lib/lifecycle-owner-auth');
     throw Error('Unexpected import '+p);
   },module:moduleObj,exports:moduleObj.exports,process:{
     env:{CSS_WEB_ACCESS_TOKEN:SECRET,VERCEL_APP_CLIENT_SECRET:'test-vercel-secret',
       GOOGLE_SERVICE_ACCOUNT_JSON:'{}'}
   },fetch:mockFetch,URL,Buffer,AbortSignal,console,Date,
 };
 vm.runInNewContext(source,sandbox,{filename:sourcePath});
 return {handler:moduleObj.exports,reads};
}
function res(){
 return {headers:{},statusCode:0,body:null,setHeader(k,v){this.headers[k]=v},
   status(v){this.statusCode=v;return this},json(obj){this.body=obj;return this}};
}
async function invoke(h,{uid='inbox:40123',cookie=null,method='GET'}={}){
 const reply=res();
 await h.handler({method,headers:cookie?{cookie}:{authorization:'Bearer '+SECRET},query:{uid}},reply);
 return reply;
}
test('single UID beyond 1000 is resolved with two read-only Sheets lookups',async()=>{
 const h=harness('api/lifecycle/mail-body.js',{uids:[[1050,'inbox:40123']]});
 const out=await invoke(h);
 assert.equal(out.statusCode,200);
 assert.equal(out.body.uid,'inbox:40123');
 assert.equal(out.body.body,'Read-only personal mail body');
 assert.deepEqual(h.reads,["'CSS Mail Inbox Raw'!A1:A10000","'CSS Mail Inbox Raw'!A1050:V1050"]);
 assert.equal(out.headers['Cache-Control'],'private, no-store');
});
test('noncached, duplicate, and changed UID fail closed',async()=>{
 const missing=harness('api/lifecycle/mail-body.js');
 assert.equal((await invoke(missing)).statusCode,404);
 const dupe=harness('api/lifecycle/mail-body.js',{uids:[[500,'inbox:40123'],[1050,'inbox:40123']]});
 assert.equal((await invoke(dupe)).body.error,'DUPLICATE_MAIL_UID');
 const changed=harness('api/lifecycle/mail-body.js',{uids:[[1050,'inbox:40123']],badRow:true});
 assert.equal((await invoke(changed)).body.error,'SOURCE_ROW_CHANGED');
});
test('GET-only endpoint denies unauthorized, invalid UID and Sheets errors',async()=>{
 const h=harness('api/lifecycle/mail-body.js',{uids:[[1050,'inbox:40123']]});
 const invalid=await invoke(h,{uid:'../secret'});
 assert.equal(invalid.statusCode,400);
 assert.equal((await invoke(h,{method:'POST'})).statusCode,405);
 const out=res();
 await h.handler({method:'GET',headers:{},query:{uid:'inbox:40123'}},out);
 assert.equal(out.statusCode,401);
 assert.equal(h.reads.length,0);
 const failing=harness('api/lifecycle/mail-body.js',{uids:[[1050,'inbox:40123']],broken:true});
 assert.equal((await invoke(failing)).body.error,'MAIL_BODY_SOURCE_UNAVAILABLE');
});
test('body is unavailable without inventing empty original text',async()=>{
 const h=harness('api/lifecycle/mail-body.js',{uids:[[1050,'inbox:40123']],body:'',classification:'BODY_EMPTY_MIME'});
 const out=await invoke(h);
 assert.equal(out.statusCode,404);
 assert.equal(out.body.classification,'BODY_EMPTY_MIME');
});
test('main lifecycle no longer downloads full mail body table for list rendering',()=>{
 const life=fs.readFileSync(path.join(root,'api/lifecycle.js'),'utf8');
 const page=fs.readFileSync(path.join(root,'index.html'),'utf8');
 assert.ok(life.includes("bodyStatus:'FETCH_ON_DEMAND'"));
 assert.ok(!life.includes("'CSS Mail Inbox Raw'!A1:V1000"));
 assert.ok(page.includes("'/api/lifecycle/mail-body?uid='+encodeURIComponent(r.uid)"));
});
