(()=>{'use strict';
const $=id=>document.getElementById(id);
const SHEET='https://docs.google.com/spreadsheets/d/1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI/edit';
const PAGE_LIMIT=100;
const ACTIONS=new Set(['EXCLUDE_MAIL','EXCLUDE_SENDER','RESTORE_MAIL','RESTORE_SENDER']);
let snapshot=null,page=0,selection=null,busy=false;
const el=(tag,value,cls)=>{
 const e=document.createElement(tag);
 if(value!==undefined)e.textContent=String(value??'');
 if(cls)e.className=cls;
 return e;
};
function placeRows(id,rows,emptyText){
 const parent=$(id);parent.replaceChildren();
 if(!rows.length){const tr=el('tr'),td=el('td',emptyText||'표시할 메일이 없습니다.');
 td.colSpan=7;tr.appendChild(td);parent.appendChild(tr);return;}
 for(const cells of rows){const tr=el('tr');
  for(const value of cells){const td=el('td');if(value?.nodeType)td.appendChild(value);else td.textContent=String(value??'');
   tr.appendChild(td);}
  parent.appendChild(tr);
 }
}
function showState(message){$('syncState').textContent=message;}
function queueButton(text,callback){
 const b=el('button',text);b.type='button';b.addEventListener('click',callback);return b;
}
async function copyUid(uid){
 try{if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(uid);}catch(_e){}
}
function openLedger(uid){
 copyUid(uid);
 window.open(SHEET,'_blank','noopener,noreferrer');
 showState('원본 시트가 열렸습니다. UID 검색: '+uid);
}
function reviewFor(uid,action){
 const ref=(snapshot?.reviews||[]).find(r=>r.uid===uid);
 if(snapshot?.capabilities?.manualMailReview!==true){openLedger(uid);return;}
 selection={uid,expectedDecision:ref?.decision||'NONE'};
 const descriptions={EXCLUDE_MAIL:'해당 UID 메일만 제외',EXCLUDE_SENDER:'해당 발신자 메일 전체 제외',
 RESTORE_MAIL:'기존 메일 제외 복구',RESTORE_SENDER:'기존 발신자 제외 복구'};
 $('reviewDescription').textContent='UID: '+uid+' / 현재 선택: '+selection.expectedDecision;
 $('choice').value=ACTIONS.has(action)?action:'EXCLUDE_MAIL';
 $('confirmReview').disabled=false;
 $('reviewDialog').showModal();
}
async function showBody(mail){
 $('bodySubject').textContent=mail.subject||'제목 미확인';
 $('bodyMeta').textContent=[mail.sender,mail.received].filter(Boolean).join(' · ');
 $('bodyText').textContent='QQ 원본 본문 확인 중';
 $('bodyDialog').showModal();
 if(!mail.body&&mail.bodyStatus!=='BODY_EMPTY_MIME'&&mail.bodyStatus!=='BODY_OVERSIZE_MIME'){
   try{
     const response=await fetch('/api/lifecycle/mail-body?uid='+encodeURIComponent(mail.uid),
       {credentials:'same-origin',cache:'no-store'});
     let result={};try{result=await response.json()}catch(_){}
     if(response.ok){mail.body=result.body||'';mail.bodyStatus=result.classification||'BODY_VERIFIED'}
     else if(response.status===404){
       mail.bodyStatus=result.classification||'NOT_CACHED';
     }else if(response.status===401){
       $('bodyText').textContent='로그인 만료 · 대시보드에서 다시 로그인하세요.';
       return;
     }else{
       $('bodyText').textContent='본문 조회 실패: '+(result.error||response.status);
       return;
     }
   }catch(e){$('bodyText').textContent='본문 조회 실패: '+e.message;return;}
 }
 $('bodyText').textContent=mail.body||(mail.bodyStatus==='BODY_EMPTY_MIME'
  ? 'QQ 원본은 확인했으나 텍스트 본문이 없는 첨부파일형/시스템 메일입니다. 원본 첨부파일은 별도로 확인해야 합니다.'
  : mail.bodyStatus==='BODY_OVERSIZE_MIME'
  ? '원본 MIME이 12MiB 안전 제한을 초과하여 본문을 저장하지 않았습니다. 원본 메일에서 확인하세요.'
  : '본문이 원본에서 아직 수집되지 않았습니다.');
}
function display(){
 if(!snapshot)return;
 const q=$('search').value.trim().toLowerCase(),sort=$('sort').value;
 const inbox=(snapshot.inbox||[]).filter(m=>
   !q||[m.uid,m.sender,m.subject,m.project].some(v=>String(v||'').toLowerCase().includes(q)));
 inbox.sort((a,b)=>sort==='new'
   ? String(b.received||'').localeCompare(String(a.received||''))
   : Number(b.days||0)-Number(a.days||0));
 const excluded=(snapshot.reviews||[]).filter(r=>['EXCLUDE_MAIL','EXCLUDE_SENDER'].includes(r.decision));
 const reviews=new Map((snapshot.reviews||[]).map(r=>[r.uid,r]));
 const count=Math.min(PAGE_LIMIT,Math.max(1,Number($('pageSize').value)||25));
 const maxPage=Math.max(0,Math.ceil(inbox.length/count)-1);
 page=Math.min(page,maxPage);
 const start=page*count,shown=inbox.slice(start,start+count);
 $('unansweredCount').textContent=(snapshot.inbox||[]).length.toLocaleString('ko-KR');
 $('excludedCount').textContent=excluded.length.toLocaleString('ko-KR');
 $('selectedCount').textContent=shown.length.toLocaleString('ko-KR');
 $('range').textContent=inbox.length?start+1+'–'+Math.min(start+count,inbox.length)+' / '+inbox.length:'0 / 0';
 $('prev').disabled=page===0;$('next').disabled=page===maxPage;
 const enabled=snapshot.capabilities?.manualMailReview===true;
 $('mode').textContent=enabled?'수동 Decision 접수 가능 · 동기화 대기':'읽기 전용 · UID 복사 및 원본에서 처리';
 placeRows('rows',shown.map(m=>{
   const buttons=el('div');buttons.style.display='grid';buttons.style.gap='5px';
   buttons.append(queueButton(m.body?'본문 보기':'본문 조회',()=>showBody(m)));
   buttons.append(queueButton(enabled?'메일 검토':'UID 복사 · 결정 시트',()=>reviewFor(m.uid,'EXCLUDE_MAIL')));
   const r=reviews.get(m.uid);
   return [[m.priority,(m.days||0)+'일'].filter(Boolean).join(' · '),
      [m.sender,m.subject].filter(Boolean).join(' · '),m.project||'',m.uid,
      r?.decision||'NONE',buttons];
 }),q?'검색에 일치하는 메일이 없습니다.':'현재 미응답 메일이 없습니다.');
 // Excluded review decisions are not inferred as active source exclusions;
 // display only the explicit reviewer ledger and its sync state.
 placeRows('excludedRows',excluded.slice(-120).reverse().map(r=>{
   const isSender=r.decision==='EXCLUDE_SENDER';
   return [r.uid,[r.sender,r.subject].filter(Boolean).join(' · '),
     r.decision,r.sync,
     queueButton(enabled?'복구 검토':'UID 복사 · 결정 시트',
      ()=>reviewFor(r.uid,isSender?'RESTORE_SENDER':'RESTORE_MAIL'))];
 }), '기존 제외 결정이 없거나 아직 원본이 연결되지 않았습니다.');
}
async function load(){
 if(busy)return;busy=true;$('reload').disabled=true;showState('데이터 조회 중');
 try{
   const response=await fetch('/api/lifecycle',{credentials:'same-origin',cache:'no-store'});
   if(response.status===401){showState('인증 필요 — 전체 대시보드에서 로그인 후 다시 시도하세요.');return;}
   if(!response.ok)throw Error('조회 HTTP '+response.status);
   const data=await response.json();
   if(!Array.isArray(data.inbox)||!Array.isArray(data.reviews))throw Error('메일 원본 구조 불일치');
   snapshot=data;
   showState('동기화 조회 완료 · '+(data.refreshed||'조회 시점 미확인'));
   display();
 }catch(e){showState('조회 실패: '+e.message+' · 기존 데이터는 유지됩니다.');}
 finally{busy=false;$('reload').disabled=false;}
}
async function submitReview(){
 if(!selection||snapshot?.capabilities?.manualMailReview!==true)return;
 const action=$('choice').value;if(!ACTIONS.has(action))return;
 const scope=action.endsWith('SENDER')
   ? '발신자 전체의 다른 메일까지 제외/복구할 수 있습니다.'
   : '현재 메일 UID 한 건에 적용하는 결정입니다.';
 if(!window.confirm('선택을 접수하시겠습니까?\n'+selection.uid+'\n'+scope))return;
 const button=$('confirmReview');button.disabled=true;
 try{
   const response=await fetch('/api/lifecycle/review',{
     method:'POST',credentials:'same-origin',
     headers:{'Content-Type':'application/json','X-CSS-Review-Confirm':'EXPLICIT_USER_APPROVAL'},
     body:JSON.stringify({uid:selection.uid,action,expectedDecision:selection.expectedDecision})
   });
   const json=await response.json().catch(()=>({error:'BAD_RESPONSE'}));
   if(!response.ok)throw Error(json.error||'REVIEW_NOT_SUBMITTED');
   $('reviewDialog').close();selection=null;
   showState(json.status==='ALREADY_SELECTED'?'이미 선택된 결정입니다.':'접수됨 · 기존 GitHub Decision Sync가 후속 반영합니다.');
   await load();
 }catch(e){showState('결정 접수 실패: '+e.message+' · 기존 선택을 다시 확인하세요.');}
 finally{button.disabled=false;}
}
$('reload').addEventListener('click',load);
$('search').addEventListener('input',()=>{page=0;display()});
$('sort').addEventListener('change',()=>{page=0;display()});
$('pageSize').addEventListener('change',()=>{page=0;display()});
$('prev').addEventListener('click',()=>{page=Math.max(0,page-1);display()});
$('next').addEventListener('click',()=>{page++;display()});
$('cancelReview').addEventListener('click',()=>{$('reviewDialog').close();selection=null});
$('confirmReview').addEventListener('click',submitReview);
$('closeBody').addEventListener('click',()=>$('bodyDialog').close());
load();
})();