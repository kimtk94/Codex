'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const {projectAutomationConsole}=require('../lib/automation-console');

const MASTER_HEAD=['Task ID','Area','Deliverable','Baseline Status','Acceptance',
  'Evidence URL','Owner','Last Checked KST','Blocker','CI Run','Notes'];
const TRACK_HEAD=['Track','Result','Checked KST','GitHub Run','Checked Scope','Boundary','Run Number'];
function master(){
  return [MASTER_HEAD,...Array.from({length:50},(_,i)=>[
    'A'+String(i+1).padStart(2,'0'),
    i<8?'QQ Mail / CSS':i<15?'SFDC Report':'Revenue / Feishu / Web',
    'Task '+i, i<11?'done':i<38?'partial':'todo','NOT_VERIFIED'
  ])];
}
function parallel(){
  return [TRACK_HEAD,...['A · SFDC Report / Lead','B · Revenue','C · SFDC Desktop','D · Web Dashboard']
    .map((v,i)=>[v,'SUCCESS','2026-10-30 00:30:30 KST',
      'https://github.com/kimtk94/Codex/actions/runs/'+(40902185186+i),
      'Read-only verification','No CRM Save',3])];
}
test('central projector preserves baseline 50, does not invent acceptance',()=>{
  const o=projectAutomationConsole(master(),parallel(),[['Component','Date','State','Detail']]);
  assert.equal(o.progress.total,50);
  assert.deepEqual([o.progress.done,o.progress.partial,o.progress.todo,o.progress.accepted],[11,27,12,0]);
  assert.equal(o.progress.baselineOnly,true);
  assert.equal(o.tracks.items.length,4);
  assert.ok(o.tracks.items.every(t=>t.result==='SUCCESS'&&t.runUrl));
  assert.equal(o.readOnly,true);
});
test('test-success is never official verification or live CRM save',()=>{
  const p=master();const run=parallel();
  const health=[['Component','Date','State','Detail'],
    ['SFDC Quote','2026-10-30','VALIDATED_PARTIAL','partial'],
    ['SFDC 3-Report Email Ingest','2026-10-30','STAGED_NOT_PROMOTED','staged'],
    ['Tax Invoice Due Watch','2026-10-30','REVIEW','one overdue']];
  const o=projectAutomationConsole(p,run,health);
  assert.equal(o.progress.accepted,0);
  assert.ok(o.issues.some(x=>x.includes('STAGED_NOT_PROMOTED')));
  assert.ok(o.issues.some(x=>x.includes('REVIEW')));
});
test('rejects duplicate task IDs and invalid status without silent progress inflation',()=>{
 const p=master();p[2][0]=p[1][0];
 assert.throws(()=>projectAutomationConsole(p,parallel(),[]),/PROGRESS_TASK_ID_INVALID/);
 const t=master();t[1][3]='accepted_by_guess';
 assert.throws(()=>projectAutomationConsole(t,parallel(),[]),/PROGRESS_STATUS_INVALID/);
});
test('prevents run URL open redirect and flags a failed workflow',()=>{
 const p=parallel();p[1][1]='FAILURE';p[1][3]='https://evil.example/steal';
 const a=projectAutomationConsole(master(),p,[]);
 assert.equal(a.tracks.items[0].runUrl,null);
 assert.ok(a.issues.includes('PARALLEL_TRACKS_NOT_ALL_SUCCESSFUL'));
});
test('missing / incomplete master and parallel source stays visible, not fabricated',()=>{
 const r=projectAutomationConsole([MASTER_HEAD,['A01','Area','task','done','VERIFIED_ACCEPTED']],
   [TRACK_HEAD],[]);
 assert.equal(r.progress.available,false);
 assert.equal(r.progress.accepted,0);
 assert.equal(r.tracks.available,false);
 assert.ok(r.issues.length>=2);
});
test('dashboard inline script parses; central UI IDs exist and no write calls introduced',()=>{
 const page=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
 const code=page.match(/<script>([\s\S]*?)<\/script>/);
 assert.ok(code,'inline script required');
 assert.doesNotThrow(()=>new vm.Script(code[1]));
 for(const id of ['automationKpi','trackRows','areaRows','automationIssues','healthRows'])
   assert.ok(page.includes('id="'+id+'"'),id);
 assert.ok(page.includes('run-link'));
 assert.equal(page.includes("fetch('/api/save'"),false);
});
test('lifecycle remains owner-authenticated and uses only central read-only tabs',()=>{
 const api=fs.readFileSync(path.join(__dirname,'..','api','lifecycle.js'),'utf8');
 assert.ok(api.includes('if(!sessionValid&&!bearerValid&&!oauthValid)'));
 assert.ok(api.includes("'Automation Master Progress'!A5:K55"));
 assert.ok(api.includes("'Parallel Track Status'!A1:G5"));
 assert.ok(api.includes('projectAutomationConsole('));
 assert.ok(!api.includes('spreadsheets.values.update('));
});
