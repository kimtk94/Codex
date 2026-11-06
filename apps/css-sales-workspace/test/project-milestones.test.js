'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {buildProjectCards,percent}=require('../lib/project-milestones');
const id='AMEA2026100751', x='X209SC26102746-Z01';
const cssHeader=['project_id','institution','customer_name','service','project_description','current_stage','progress_percent','latest_action_required'];
const sifHeader=['project_id','Prepayment','Status','workflow_status','sif_first_seen_at','contract_created_at','AMEA Full Name'];
const quoteHeader=['Approved AMEA ID','Quote Name','Active','Approval Match'];
const preHeader=['Quotation Number','Project Number'];
const matrix=(headers,rows)=>[headers,...rows];
const css=(rows=[])=>matrix(cssHeader,rows);
const sif=(rows=[])=>matrix(sifHeader,rows);
const quotes=(rows=[])=>matrix(quoteHeader,rows);
const pre=(rows=[])=>matrix(preHeader,rows);
const base=(opts={})=>({
  project:x,amea:id,institution:'Yonsei Univ.',customer:'Researcher',service:'RNA-Seq',
  stage:'SIF requested',status:'Running',progress:10,expectedMonth:'2026-12',billing:'PROJECT FORECAST',
  next:'SIF 제출 확인',...opts
});
const project=(lifecycles,sources={})=>buildProjectCards(lifecycles,sources).projects;

test('Prepayment listed: SIF request excluded but project progress remains visible',()=>{
  const [p]=project([base()],{
    cssProjects:css([[id,'Yonsei','Researcher','RNA-Seq','CSS exact project','SIF requested','10','Please submit SIF']]),
    sifRecords:sif([[id,'TRUE','SIF requested','SIF requested','','2026-11-01','Full quoted CSS name']]),
    quoteRecords:quotes([[id,'Korea-Yonsei-5-mRNA-Seq-AMEA2026100751','ACTIVE','APPROVED']])
  });
  assert.equal(p.prepayment,true);
  assert.equal(p.sifFollowup,'EXEMPT');
  assert.equal(p.sifState,'WAIVED_PREPAYMENT');
  assert.match(p.next,/SIF 제출 필수 아님/);
  assert.equal(p.progress,10);
  assert.equal(p.quoteFullName,'Korea-Yonsei-5-mRNA-Seq-AMEA2026100751');
  assert.equal(p.quoteNameState,'SFDC_VERIFIED');
});

test('Prepayment ledger exact X base applies to matching X-Z subproject only',()=>{
  const [p]=project([base()],{prepaymentRecords:pre([['AMEA2026100751-01','X209SC26102746']])});
  assert.equal(p.prepayment,true);
  assert.equal(p.prepaymentEvidence,'FEISHU_PROJECT');
});

test('Submitted SIF advances followup; no repeated SIF request',()=>{
  const [p]=project([base({stage:'Sample received',progress:40})],{
    sifRecords:sif([[id,'FALSE','SIF received','SIF received','2026-11-01','2026-10-15','']])
  });
  assert.equal(p.sifState,'SUBMITTED');
  assert.equal(p.sifFollowup,'NEXT_STAGE');
  assert.doesNotMatch(p.next,/제출 확인$/);
  assert.equal(p.progress,40);
});

test('Report or Statement proves inferred PO, not an original PO mail',()=>{
  const [p]=project([base({stage:'Final report ready',progress:95})]);
  assert.equal(p.poState,'INFERRED_FROM_REPORT_OR_STATEMENT');
  const [invoice]=project([base({stage:'Invoice issued [QQ confirmed]',progress:100})]);
  assert.equal(invoice.poState,'NOT_VERIFIED');
  assert.equal(invoice.progress,null,'Invoice alone cannot prove physical completion');
});

test('Multiple SFDC quote names stay visible and marked for review',()=>{
  const [p]=project([base()],{
    quoteRecords:quotes([
      [id,'Korea-Yonsei-Quote A','ACTIVE','APPROVED'],
      [id,'Korea-Yonsei-Quote B','ACTIVE','APPROVED'],
      [id,'Old Quote','INACTIVE','APPROVED']
    ])
  });
  assert.equal(p.quoteNameState,'MULTIPLE_REVIEW');
  assert.match(p.quoteFullName,/Quote A/);
  assert.match(p.quoteFullName,/Quote B/);
  assert.doesNotMatch(p.quoteFullName,/Old Quote/);
});

test('No Quote identity: never substitute CSS project description as SFDC quote name',()=>{
  const [p]=project([base()],{
    cssProjects:css([[id,'Y','C','S','Korea-CSS-LONG-PROJECT','Sample QC','55','']]),
    quoteRecords:quotes([['AMEA2026999999','Wrong Quote','ACTIVE','APPROVED']])
  });
  assert.equal(p.quoteFullName,'');
  assert.equal(p.quoteNameState,'NOT_LINKED');
  assert.equal(p.cssProjectDescription,'Korea-CSS-LONG-PROJECT');
});

test('CSS-only projects are shown individually, not removed by absence from Feishu',()=>{
  const other='AMEA2026110001';
  const results=buildProjectCards([],{cssProjects:css([
    [other,'KIST','Kim','WGS','Korea-KIST-WGS-100Gb-Kim','Library preparation','70','']
  ])});
  assert.equal(results.projects.length,1);
  assert.equal(results.projects[0].project,other);
  assert.equal(results.projects[0].progress,70);
  assert.equal(results.coverage.progressVerified,1);
});

test('Two subprojects sharing AMEA do not inherit AMEA-wide CSS progress',()=>{
  const xs=[base({project:'X209SC26102746-Z01',stage:'NOT_IN_CSS_SNAPSHOT',progress:0}),
            base({project:'X209SC26102746-Z02',stage:'NOT_IN_CSS_SNAPSHOT',progress:0})];
  const ps=project(xs,{cssProjects:css([
    [id,'Y','C','S','Description','Sequencing','85','']
  ])});
  assert.equal(ps.length,2);
  assert.equal(ps[0].progress,null);
  assert.equal(ps[1].progress,null);
});

test('Unverified quote rows, unsafe percent and prepayment of other project fail closed',()=>{
  const [p]=project([base({stage:'NOT_IN_CSS_SNAPSHOT',progress:100})],{
    quoteRecords:quotes([[id,'Unapproved Quote','ACTIVE','NOT_APPROVED']]),
    cssProjects:css([[id,'Y','C','S','Description','Invoice issued','100','']]),
    prepaymentRecords:pre([['AMEA2026119999','X209SC26109999']])
  });
  assert.equal(p.quoteNameState,'NOT_LINKED');
  assert.equal(p.prepayment,false);
  assert.equal(p.progress,null);
  assert.equal(percent('101'),null);
  assert.equal(percent(''),null);
});
