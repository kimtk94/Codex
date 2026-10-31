'use strict';

// Owner-only, read-only presentation. Crosswalk X is a source candidate, NEVER a
// certified contract, invoiced amount, paid balance or Salesforce join key.
const HEAD=['AMEA','Project / Institution','Watch Quote KRW','Watch X (unsafe)',
  'Online H Candidate','Online X Candidate','Online Stage Candidate',
  'Finance Base X Candidate','Evidence State','Online Rows','Outstanding Rows',
  'eTax Rows','Outstanding Gross KRW','eTax Gross KRW','Source Date Online',
  'Source Date Finance','Attribution Gate','Review Instruction','Checked KST','GitHub Run'];
const STATES=new Set(['FINANCE_AMEA_CANDIDATE','ONLINE_AMEA_CANDIDATE',
  'ONLINE_FINANCE_SAME_X_CANDIDATE','NO_AMEA_SOURCE_CANDIDATE',
  'MULTIPLE_FINANCE_X_REVIEW','AMBIGUOUS_ONLINE_CONTRACT_REVIEW',
  'ONLINE_FINANCE_X_CONFLICT','X_REFERENCES_MULTIPLE_AMEAS']);
const CANDIDATES=new Set(['FINANCE_AMEA_CANDIDATE','ONLINE_AMEA_CANDIDATE',
  'ONLINE_FINANCE_SAME_X_CANDIDATE']);
const UNKNOWN=()=>({available:false,status:'SOURCE_NOT_VERIFIED',verified:false,
  candidateCount:0,missingCount:0,items:[]});
function cell(row,i){return String(row?.[i]??'').trim();}
function dateAge(yyyymmdd,now){
  if(!/^20\d{2}-\d{2}-\d{2}$/.test(yyyymmdd))return null;
  const stamp=Date.parse(yyyymmdd+'T00:00:00Z');
  if(!Number.isFinite(stamp)||new Date(stamp).toISOString().slice(0,10)!==yyyymmdd)return null;
  const kstDay=new Date(now+9*3600*1000).toISOString().slice(0,10);
  return Math.round((Date.parse(kstDay+'T00:00:00Z')-stamp)/86400000);
}
function checkedAgeHours(stamp,now){
  const m=/^(20\\d{2})-(\\d{2})-(\\d{2}) (\\d{2}):(\\d{2}):(\\d{2}) KST$/.exec(stamp);
  if(!m)return null;
  const time=Date.parse(m[1]+'-'+m[2]+'-'+m[3]+'T'+m[4]+':'+m[5]+':'+m[6]+'+09:00');
  if(!Number.isFinite(time))return null;
  const rendered=new Date(time+9*3600000).toISOString().slice(0,19).replace('T',' ');
  if(rendered!==stamp.slice(0,19))return null;
  return (now-time)/3600000;
}
function projectUnissuedContracts(rows,now=Date.now()){
  const fallback=UNKNOWN();
  if(!Array.isArray(rows)||!rows.length||HEAD.some((h,i)=>cell(rows[0],i)!==h))return fallback;
  const seen=new Set(),contractOwners=new Map(),items=[];let financeStale=false;
  for(const r of rows.slice(1)){
    const amea=cell(r,0);
    if(!amea)continue;
    const state=cell(r,8),gate=cell(r,16);
    if(!/^AMEA20\d{8}$/.test(amea)||seen.has(amea)||!STATES.has(state))return fallback;
    const candidate=CANDIDATES.has(state);
    if(gate!==(candidate?'CANDIDATE_ONLY_REQUIRES_ORIGINAL_CONTRACT_REVIEW':
      'QUARANTINE_NO_CONTRACT_ATTRIBUTION'))return fallback;
    const ageOnline=dateAge(cell(r,14),now),ageFinance=dateAge(cell(r,15),now);
    const checkedAge=checkedAgeHours(cell(r,18),now);
    // The generated crosswalk must be fresh, even if its underlying payment
    // source is older. Old payment evidence can remain as a labeled review.
    if(checkedAge===null||checkedAge<0||checkedAge>36)return fallback;
    if(ageOnline===null||ageFinance===null||ageOnline<0||ageFinance<0)return fallback;
    const onlineX=cell(r,5),financeX=cell(r,7);
    if(candidate&&state==='FINANCE_AMEA_CANDIDATE'&&!/^X[A-Z0-9]{10,30}$/.test(financeX))return fallback;
    if(candidate&&state!=='FINANCE_AMEA_CANDIDATE'&&!/^X[A-Z0-9]{10,30}-Z\d{2}$/.test(onlineX))return fallback;
    if(state==='ONLINE_FINANCE_SAME_X_CANDIDATE'&&onlineX.split('-')[0]!==financeX)return fallback;
    const x=candidate?(onlineX||financeX):'';
    if(x){
      const ownerKey=x.split('-')[0];
      if(contractOwners.has(ownerKey)&&contractOwners.get(ownerKey)!==amea)return fallback;
      contractOwners.set(ownerKey,amea);
    }
    seen.add(amea); financeStale ||=ageFinance>2||ageOnline>2;
    items.push({amea,project:cell(r,1),quoteKrw:cell(r,2),unsafeWatchX:cell(r,3),
      candidateX:x,onlineH:candidate?cell(r,4):'',onlineStage:candidate?cell(r,6):'',
      source:state==='FINANCE_AMEA_CANDIDATE'?'FINANCE':candidate?'ONLINE':'NONE',
      state,gate,financeSourceDate:cell(r,15),onlineSourceDate:cell(r,14),
      financeStale:ageFinance>2,attributionVerified:false,issuanceVerified:false,
      paymentVerified:false,revenueActualApproved:false});
  }
  if(!items.length)return fallback;
  return {available:true,status:financeStale?'REVIEW_SOURCE_STALE':'REVIEW_ONLY',
    verified:false,financeStale,items,candidateCount:items.filter(v=>v.candidateX).length,
    missingCount:items.filter(v=>!v.candidateX).length,
    source:'CSS AMEA Contract Candidate Crosswalk; AMEA-keyed only'};
}
module.exports={projectUnissuedContracts,HEAD};
