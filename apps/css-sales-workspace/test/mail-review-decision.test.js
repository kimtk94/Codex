'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {validateAction,locateTarget}=require('../lib/mail-review-decision');
const head=['Decision (Edit)','Sender Email','When','Age','Mail UID (Key)','Queue',
            'Reviewer Note (Edit)','Decision Sync Status','Snapshot','Subject'];
function row(uid,decision='NONE',sender='client@example.edu',sync='NOT_SUBMITTED'){
 return [decision,sender,'','',''+uid,'','',''+sync,'','a subject'];
}
const rows=()=>[head,row('inbox:401','NONE'),row('inbox:402','EXCLUDE_MAIL','client@example.edu','SYNCED:EXCLUDE_MAIL')];
const request={uid:'inbox:401',action:'EXCLUDE_MAIL',expectedDecision:'NONE'};
test('allows explicit valid UID-only action without client data in body',()=>{
 assert.deepEqual(validateAction(request),request);
 assert.equal(locateTarget(rows(),request).rowIndex,2);
});
test('rejects automatic unknown actions, extra fields and non-UID identifiers',()=>{
 for(const candidate of [
   {...request,action:'SEND_EMAIL'},
   {...request,recipient:'private@example.com'},
   {...request,uid:'../../admin'},
   {...request,expectedDecision:'UNKNOWN'}
 ])assert.throws(()=>validateAction(candidate));
});
test('rejects race against a prior exclusion or an unsynced manual review',()=>{
 assert.throws(()=>locateTarget(rows(),{...request,expectedDecision:'RESTORE_MAIL'}),/REVIEW_DECISION_CHANGED/);
});
test('rejects duplicated or missing UIDs without choosing an arbitrary row',()=>{
 const duplicate=rows();duplicate.push(row('inbox:401'));
 assert.throws(()=>locateTarget(duplicate,request),/DUPLICATE_MAIL_UID/);
 assert.throws(()=>locateTarget(rows(),{...request,uid:'inbox:999'}),/MAIL_UID_NOT_FOUND/);
});
test('sender exclusions require verified sender address',()=>{
 const data=[head,row('inbox:401','NONE','not-an-email')];
 assert.throws(()=>locateTarget(data,{...request,action:'EXCLUDE_SENDER'}),/SENDER_ADDRESS_NOT_VERIFIED/);
});
test('review API requires explicit owner, same-origin and feature gate',()=>{
 const code=fs.readFileSync(path.join(__dirname,'..','api','lifecycle','review.js'),'utf8');
 assert.ok(code.includes("process.env.CSS_WEB_DECISIONS_ENABLED!=='true'"));
 assert.ok(code.includes("if(!isOwner(req))"));
 assert.ok(code.includes("if(!sameOriginRequest(req))"));
 assert.ok(code.includes("EXPLICIT_USER_APPROVAL"));
 assert.ok(code.includes('locateTarget(rows,request)'));
 assert.ok(code.includes("range:TAB+'!H'+target.rowIndex"));
 assert.ok(!code.includes('sendMail('));
 assert.ok(!code.includes('SFDC_SAVE'));
});
test('central run monitor now includes BI Mail Review Sync',()=>{
 const ops=fs.readFileSync(path.join(__dirname,'..','..','..','automation','ops',
   'publish_central_workflow_health.py'),'utf8');
 assert.ok(ops.includes('bi-mail-review-sync.yml'));
 const web=fs.readFileSync(path.join(__dirname,'..','lib','automation-console.js'),'utf8');
 assert.ok(web.includes('items.length===17'));
});
