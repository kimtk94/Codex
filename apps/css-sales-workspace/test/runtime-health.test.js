'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const script=fs.readFileSync(path.join(__dirname,'..','api','health.js'),'utf8');
const S={VERCEL_APP_CLIENT_ID:'only-fixture-client',VERCEL_APP_CLIENT_SECRET:'only-fixture-secret',GOOGLE_SERVICE_ACCOUNT_JSON:'only-fixture-json',CSS_WEB_ACCESS_TOKEN:'only-fixture-owner-token'};
function run(method='GET',env=S){
 const module={exports:{}};
 vm.runInNewContext(script,{module,exports:module.exports,process:{env}}, {filename:'health.js'});
 const res={statusCode:200,headers:{},body:null,
  setHeader(k,v){this.headers[k.toLowerCase()]=v;return this},
  status(s){this.statusCode=s;return this},
  json(b){this.body=b;return this},
  end(){return this}
 };
 module.exports({method,headers:{authorization:'Bearer NEVER_LOOK_AT_REQUEST'}},res);
 return res;
}
test('runtime presence check returns neither secrets nor live-data approval',()=>{
 const r=run();
 assert.equal(r.statusCode,200);
 assert.equal(r.body.status,'RUNTIME_CONFIG_PRESENT');
 assert.equal(r.body.ownerAuthenticated,false);
 assert.equal(r.body.liveSheetsVerified,false);
 assert.equal(r.body.releaseApproved,false);
 assert.equal(r.body.dataAccessRequiresOwner,true);
 for(const value of Object.values(S))assert.ok(!JSON.stringify(r.body).includes(value));
 assert.equal(r.headers['cache-control'],'no-store');
});
test('missing protected auth or Sheets credentials fails closed',()=>{
 for(const key of Object.keys(S)){
  const env={...S};delete env[key];
  const r=run('GET',env);
  assert.equal(r.statusCode,503,key);
  assert.equal(r.body.status,'RUNTIME_CONFIG_INCOMPLETE');
  assert.equal(r.body.releaseApproved,false);
 }
});
test('POST cannot hit health runtime and HEAD reveals no body',()=>{
 const post=run('POST');
 assert.equal(post.statusCode,405);
 assert.equal(post.body.state,'METHOD_NOT_ALLOWED');
 assert.equal(post.headers.allow,'GET, HEAD');
 const head=run('HEAD');
 assert.equal(head.statusCode,200);
 assert.equal(head.body,null);
});
test('health check never authenticates owner, reads Sheets, or writes financial source',()=>{
 assert.ok(!script.includes('fetch('));
 assert.ok(!script.includes('GoogleAuth'));
 assert.ok(!script.includes('productionPromotion:true'));
 assert.ok(!script.includes('Set-Cookie'));
});
