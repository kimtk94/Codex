const {test}=require('node:test');const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');
const source=fs.readFileSync(__dirname+'/api/data.js','utf8');
async function invoke(mode,query={view:'mail_detail',uid:'inbox:123'},env={VERCEL:'1',VERCEL_ENV:'preview',GOOGLE_SERVICE_ACCOUNT_JSON:'{}'}){
 const paths=[];const context={module:{exports:{}},process:{env},Buffer,console,require:()=>({GoogleAuth:class{async getClient(){return {getAccessToken:async()=>({token:'synthetic'})}}}}),fetch:async url=>{
  const range=decodeURIComponent(url.split('/values/')[1]||'');paths.push(range);let values=[];
  if(range.includes("'Unanswered Emails'!I"))values=mode==='unauthorized'?[]:[['inbox:123']];
  else if(range.includes("'Unanswered Emails'!A"))values=[['0','','sender@example.test','Subject','2026-10-27']];
  else if(range.includes("'CSS Mail Inbox Raw'!A2")){if(mode==='missingraw')return {ok:false,status:400};values=mode==='raw'?[['inbox:123']]:[]}
  else if(range.includes("'CSS Mail Inbox Raw'!A2:X2"))values=[['inbox:123','','','date','from','name','to','cc','subject','cached body']];
  else if(range.includes("'All Emails'!R2:T"))values=mode==='pending'?[]:[['123','Inbox','inbox']];
  else if(range.includes("'All Emails'!A2:AG2")){const r=[];r[0]='999';r[16]='first';r[21]='second';r[22]='third';values=[r]}
  return {ok:true,json:async()=>({values})};
 }};
 vm.runInNewContext(source,context);let status,body;const res={setHeader(){},status(s){status=s;return this},json(b){body=b;return this}};
 await context.module.exports({method:'GET',query,headers:{}},res);return {status,body,paths};
}
test('IMAP UID index and all split body fields, independent of local A sequence',async()=>{const r=await invoke('history');assert.equal(r.status,200);assert.equal(r.body.body,'firstsecondthird');assert(r.paths.some(x=>x.includes('R2:T')))});
test('missing raw cache still reads historical mail',async()=>assert.equal((await invoke('missingraw')).body.bodyAvailable,true));
test('pending body is explicit',async()=>{const r=await invoke('pending');assert.equal(r.body.bodyAvailable,false);assert.match(r.body.notice,/대기/)});
test('UID outside current queue rejected before body reads',async()=>{const r=await invoke('unauthorized');assert.equal(r.status,404);assert.equal(r.paths.length,1)});
test('production without access configuration denied',async()=>assert.equal((await invoke('history',undefined,{VERCEL:'1',VERCEL_ENV:'production'})).status,503));
test('malformed UID rejected',async()=>assert.equal((await invoke('history',{view:'mail_detail',uid:'sent:123'})).status,400));
