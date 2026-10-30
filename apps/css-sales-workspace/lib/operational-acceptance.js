'use strict';
// Read-only canonical source. A successful CI build is NEVER Production approval.
const HEADER=['Area','Check','Result','Gate','Evidence KST','Observed','Next action','Checked KST'];
const RELEASE_CHECKS=['Owner-authenticated Preview E2E','Production READY SHA parity','Production acceptance'];
const STATUSES=new Set(['PASS','WARN','BLOCK']);
const GATES=new Set(['RELEASE','DATA','FINANCE','INFO']);
function cell(row,index){return String(row?.[index]??'').trim()}
function denied(reason){
 return {available:false,status:'BLOCK',reason,source:'CSS Operational Acceptance',
   releaseApproved:false,rows:[],checked:''};
}
function parseKst(text){
 const m=/^(\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d) KST$/.exec(text);
 if(!m)return NaN;
 const stamp=Date.parse(m[1]+'-'+m[2]+'-'+m[3]+'T'+m[4]+':'+m[5]+':'+m[6]+'+09:00');
 return Number.isFinite(stamp)?stamp:NaN;
}
function projectOperationalAcceptance(rows,now=Date.now()){
 if(!Array.isArray(rows)||HEADER.some((name,i)=>cell(rows[0],i)!==name))
   return denied('ACCEPTANCE_SOURCE_SCHEMA_MISSING');
 const items=[],seen=new Set();
 for(const row of rows.slice(1)){
   const check=cell(row,1);
   if(!check)continue;
   const status=cell(row,2),gate=cell(row,3);
   if(seen.has(check)||!STATUSES.has(status)||!GATES.has(gate))
     return denied('ACCEPTANCE_SOURCE_VALUES_INVALID');
   seen.add(check);
   items.push({
     area:cell(row,0).slice(0,50),check:check.slice(0,100),
     status,gate,checked:cell(row,7),evidence:cell(row,4).slice(0,75),
     observed:cell(row,5).slice(0,180),
     action:cell(row,6).slice(0,260)
   });
 }
 if(!items.length||items.length>30||!RELEASE_CHECKS.every(name=>seen.has(name)))
   return denied('ACCEPTANCE_RELEASE_EVIDENCE_INCOMPLETE');
 const sourceCheck=items.find(x=>x.check==='Production acceptance');
 const browser=items.find(x=>x.check==='Owner-authenticated Preview E2E');
 const production=items.find(x=>x.check==='Production READY SHA parity');
 if(sourceCheck.gate!=='RELEASE'||browser.gate!=='RELEASE'||production.gate!=='RELEASE')
   return denied('ACCEPTANCE_RELEASE_GATE_INVALID');
 const checked=sourceCheck.checked;
 // A pending GitHub Action is not proof the status source is current.
 if(items.some(x=>x.checked!==checked))return denied('ACCEPTANCE_SNAPSHOT_INCONSISTENT');
 const ageHours=(now-parseKst(checked))/3600000;
 const fresh=Number.isFinite(ageHours)&&ageHours>=-0.0834&&ageHours<=8;
 const blockers=items.filter(x=>x.status==='BLOCK');
 const warnings=items.filter(x=>x.status==='WARN');
 const eligible=fresh&&sourceCheck.status==='PASS'&&browser.status==='PASS'&&
   production.status==='PASS'&&blockers.length===0;
 // Separate source readiness from explicit user approval and live deployment.
 return {available:true,source:'CSS Operational Acceptance',
   status:!fresh||!eligible?'BLOCK':'READY_FOR_MANUAL_REVIEW',
   reason:!fresh?'ACCEPTANCE_SNAPSHOT_STALE'
     :eligible?'MANUAL_RELEASE_APPROVAL_STILL_REQUIRED':'SOURCE_BLOCKED',
   checked,ageHours:Number.isFinite(ageHours)?Math.round(ageHours*10)/10:null,
   counts:{pass:items.length-blockers.length-warnings.length,
     warn:warnings.length,block:blockers.length},
   browserE2E:browser.status,productionParity:production.status,
   releaseApproved:false,rows:items
 };
}
module.exports={projectOperationalAcceptance,HEADER};
