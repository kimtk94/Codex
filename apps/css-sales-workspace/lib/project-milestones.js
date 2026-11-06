'use strict';

// Source-backed project cards. Identity joins use exact AMEA or exact X subproject.
const clean=v=>String(v??'').trim();
const upper=v=>clean(v).toUpperCase();
const asRows=matrix=>{
  if(!Array.isArray(matrix)||!matrix.length)return [];
  const h=matrix[0].map(clean);
  return matrix.slice(1).map(row=>Object.fromEntries(h.map((name,i)=>[name,clean(row[i])])));
};
const percent=value=>{
  if(clean(value)==='')return null;
  const n=Number(clean(value).replace(/%$/,''));
  return Number.isFinite(n)&&n>=0&&n<=100?Math.round(n):null;
};
const hasPhysicalStage=stage=>/sample|\bqc\b|library|sequenc|production|data ready|final report|sif|completed|settled/i.test(clean(stage))
   &&!/invoice|statement|not_in_css_snapshot/i.test(clean(stage));
const statusFromStage=(stage,status)=>{
  const text=clean(stage)+' '+clean(status);
  return /final report|statement ready|statement confirmation|statement confirmed/i.test(text)?'INFERRED_FROM_REPORT_OR_STATEMENT':'NOT_VERIFIED';
};
const exactList=(list,key)=>list.filter(r=>upper(r[key]));
const distinct=(values)=>[...new Set(values.map(clean).filter(Boolean))];

function buildProjectCards(lifecycles,{cssProjects=[],sifRecords=[],quoteRecords=[],prepaymentRecords=[]}={}){
  const cssRows=asRows(cssProjects),sifRows=asRows(sifRecords),qRows=asRows(quoteRecords),preRows=asRows(prepaymentRecords);
  const cssIndex=new Map(),sifIndex=new Map(),quoteIndex=new Map(),prepQuoteIndex=new Map(),prepXIndex=new Map();
  for(const r of cssRows){
    const id=upper(r.project_id);
    if(!/^AMEA\d{7,}(?:-\d{1,3})?$/.test(id))continue;
    (cssIndex.get(id)||cssIndex.set(id,[]).get(id)).push(r);
  }
  for(const r of sifRows){
    const id=upper(r.project_id);
    if(!/^AMEA\d{7,}(?:-\d{1,3})?$/.test(id))continue;
    (sifIndex.get(id)||sifIndex.set(id,[]).get(id)).push(r);
  }
  for(const r of qRows){
    const id=upper(r['Approved AMEA ID']);
    if(!id||upper(r.Active)!=='ACTIVE'||upper(r['Approval Match'])!=='APPROVED'||!clean(r['Quote Name']))continue;
    (quoteIndex.get(id)||quoteIndex.set(id,[]).get(id)).push(r);
  }
  for(const r of preRows){
    const id=upper(r['Quotation Number']),x=upper(r['Project Number']);
    if(id)(prepQuoteIndex.get(id)||prepQuoteIndex.set(id,[]).get(id)).push(r);
    if(/^X\d+SC\d+$/.test(x))(prepXIndex.get(x)||prepXIndex.set(x,[]).get(x)).push(r);
  }
  const lifeCount=new Map();
  for(const p of lifecycles){
    const id=upper(p.amea);
    if(id)lifeCount.set(id,(lifeCount.get(id)||0)+1);
  }
  function enrich(base){
    const p={...base},id=upper(p.amea),cssMatches=cssIndex.get(id)||[],sifMatches=sifIndex.get(id)||[];
    const css=cssMatches.length===1?cssMatches[0]:null,sif=sifMatches.length===1?sifMatches[0]:null;
    const names=distinct((quoteIndex.get(id)||[]).map(r=>r['Quote Name']));
    p.quoteFullName=names.join('\n');
    p.quoteNameState=names.length===1?'SFDC_VERIFIED':names.length>1?'MULTIPLE_REVIEW':'NOT_LINKED';
    p.cssProjectDescription=clean(css?.project_description)||clean(sif?.['AMEA Full Name'])||'';
    p.projectIdentity=id||upper(p.project);
    const xMatch=upper(p.project).match(/^(X\d+SC\d+)(?:-Z\d+)?$/);
    const hasPrepayment=!!sif&&/^(?:TRUE|YES|1)$/i.test(clean(sif.Prepayment));
    const exactPrepay=(prepQuoteIndex.get(id)||[]).length>0;
    const xPrepay=!!xMatch&&(prepXIndex.get(xMatch[1])||[]).length>0;
    p.prepayment=hasPrepayment||exactPrepay||xPrepay;
    p.prepaymentEvidence=hasPrepayment?'CSS_SIF_TRACKER':exactPrepay?'FEISHU_QUOTE':xPrepay?'FEISHU_PROJECT':'NOT_VERIFIED';
    const words=clean(sif?.Status)+' '+clean(sif?.workflow_status);
    const approved=/sif\s*(?:approved|승인)/i.test(words);
    const submitted=approved||/sif\s*(?:submitted|received|제출|접수)/i.test(words)||!!clean(sif?.sif_first_seen_at);
    p.sifState=approved?'APPROVED':submitted?'SUBMITTED':p.prepayment?'WAIVED_PREPAYMENT':/sif\s*(?:requested|요청)/i.test(words)?'REQUESTED':'NOT_VERIFIED';
    p.contractEvidence=!!sif&&!!clean(sif.contract_created_at);
    p.poState=statusFromStage(p.stage,p.status);
    const csv=css?percent(css.progress_percent):null;
    const lv=percent(p.progress);
    const safeLife=hasPhysicalStage(p.stage)?lv:null;
    const sourceSingle=(lifeCount.get(id)||0)<=1;
    const physicalCss=!!css&&hasPhysicalStage(css.current_stage);
    if(safeLife!==null&&(!physicalCss||!sourceSingle||safeLife>=csv)){
      p.progress=safeLife;p.progressEvidence='EXACT_X_CSS_NOTICE';
    }else if(physicalCss&&csv!==null&&sourceSingle){
      p.progress=csv;p.progressEvidence='CSS_PROJECT_CHECKPOINT';
    }else if(!p.project.startsWith('X')&&physicalCss&&csv!==null){
      p.progress=csv;p.progressEvidence='CSS_PROJECT_CHECKPOINT';
    }else{
      p.progress=null;p.progressEvidence='NOT_VERIFIED';
    }
    if(!p.stage||p.stage==='NOT_IN_CSS_SNAPSHOT')p.stage=clean(css?.current_stage)||clean(p.status)||'단계 미확인';
    p.sifFollowup=p.prepayment?'EXEMPT':submitted?'NEXT_STAGE':
      (p.progress!==null&&p.progress>=40)?'NEXT_STAGE':
      (p.contractEvidence&&(/sif\s*(?:requested|요청)/i.test(words)||/sif\s*(?:requested|요청)/i.test(p.stage)))?'FOLLOWUP_SIF':'NOT_VERIFIED';
    if(p.sifFollowup==='EXEMPT'){
      p.next='Prepayment · SIF 제출 필수 아님. '+(p.progress!==null&&p.progress>=40?'현재 생산 단계 확인': '샘플 입고 및 후속 진행 확인');
    }else if(p.sifFollowup==='NEXT_STAGE'&&/sif/i.test(clean(p.next))){
      p.next='SIF 단계 완료/통과 · 샘플 입고 및 이후 진행 확인';
    }else if(p.sifFollowup==='FOLLOWUP_SIF'){
      p.next='SIF 제출/접수 확인';
    }else{
      p.next=clean(p.next)||clean(css?.latest_action_required)||'진행 단계 확인';
    }
    return p;
  }
  const cards=lifecycles.map(enrich);
  const known=new Set(lifecycles.map(p=>upper(p.amea)));
  for(const [id,rows] of cssIndex){
    if(known.has(id)||rows.length!==1)continue;
    const c=rows[0];
    cards.push(enrich({
      project:id,amea:id,institution:clean(c.institution),customer:clean(c.customer_name),
      service:clean(c.service),stage:clean(c.current_stage),
      status:clean(c.current_stage),progress:percent(c.progress_percent),
      billing:'CSS SOURCE ONLY',expectedMonth:'',next:clean(c.latest_action_required),
      invoiceCount:0,actual:0,forecast:0,pendingStatement:'',noticeAt:'',
      pendingVerified:0,pendingEvidence:'',projectSource:'CSS_PROJECT_ONLY'
    }));
  }
  return {
    projects:cards,
    coverage:{
      total:cards.length,
      quoteVerified:cards.filter(p=>p.quoteNameState==='SFDC_VERIFIED').length,
      quoteReview:cards.filter(p=>p.quoteNameState==='MULTIPLE_REVIEW').length,
      progressVerified:cards.filter(p=>p.progress!==null).length,
      prepayment:cards.filter(p=>p.prepayment).length,
      sifExempt:cards.filter(p=>p.sifFollowup==='EXEMPT').length
    }
  };
}
module.exports={buildProjectCards,hasPhysicalStage,percent};
