'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {projectPersonalLeads}=require('../lib/personal-leads');
const head=['Lead ID','Created Date','Institution','Customer','Email','Description',
'Description Class','Lead Status','Opportunity ID','My Sent After Lead',
'My Sent Before Lead','My Sent Ever','Last Sent After Lead','Last Sent Ever',
'My Mail Status','QQ Message-ID (Evidence)','To / CC','QQ Source',
'Latest QQ Outbound Checked','Follow-up Action'];
function data(){
 const out=[head];
 for(let i=0;i<493;i++){
 const r=Array(20).fill('');
 r[0]='L'+i;r[1]='2026-10-25';r[2]='University';r[4]='name'+i+'@university.edu';
 r[5]='RNA-Seq 6Gb';r[6]='PRESENT';r[7]='New';
 r[14]=i<235?'SENT_AFTER_LEAD_CONFIRMED':i<244?'SENT_BEFORE_LEAD_ONLY':'NO_PERSONAL_OUTBOUND_EVIDENCE';
 out.push(r);
 }
 return out;
}
test('personal-sent suppresses 235 and shows only 258 without current reply',()=>{
 const r=projectPersonalLeads(data());assert.equal(r.length,258);
 assert.equal(r.filter(x=>x.personalEvidence==='SENT_BEFORE_LEAD_ONLY').length,9);
 assert.ok(r.every(x=>x.id!=='L0'));
});
test('qualified is excluded from first-contact queue',()=>{
 const d=data();d[245][7]='Qualified';const x=projectPersonalLeads(d);assert.equal(x.length,257);
});
test('schema and duplicate IDs fail closed',()=>{
 assert.throws(()=>projectPersonalLeads([['id']]),/SCHEMA/);
 const d=data();d[246][0]=d[245][0];
 assert.throws(()=>projectPersonalLeads(d),/DUPLICATE/);
});
test('unknown mail status fails closed',()=>{
 const d=data();d[246][14]='UNVERIFIED';
 assert.throws(()=>projectPersonalLeads(d),/UNKNOWN/);
});
