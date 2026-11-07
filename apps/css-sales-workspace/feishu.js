'use strict';
(function(){
  const BASE_URL='https://ocnz4cb25scn.feishu.cn/base/IpMkbUD0vaFqtYs93a3csXtdn1b?table=tblTZe5tkRUeOHM8&view=vewwsXuLY6';
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const sourceValue=(record,field)=>String(record?.[field]??'').trim();
  function stageGroup(record){
    const stage=sourceValue(record,'Current Stage').toLowerCase();
    if(/data ready|final report|statement ready|report ready/.test(stage))return 'REPORT';
    if(/sequenc|production/.test(stage))return 'SEQUENCING';
    if(/library/.test(stage))return 'LIBRARY';
    if(/sample|\bqc\b/.test(stage))return 'SAMPLE';
    if(/sif|contract/.test(stage))return 'SIF';
    return 'OTHER';
  }
  const verifiedQuote=r=>sourceValue(r,'Quote Match State')==='SFDC_EXACT_VERIFIED';
  const missingSif=r=>!['YES'].includes(sourceValue(r,'Prepayment'))
      && ['NOT_VERIFIED','NUMBER_ONLY_REVIEW','REQUESTED'].includes(sourceValue(r,'SIF State'));
  const missingProgress=r=>r.progress===null||r.progress===undefined||!Number.isFinite(Number(r.progress));
  const quoteName=r=>sourceValue(r,'Quote Full Name')||'Quote 이름 미확인';
  const showProgress=r=>missingProgress(r)?'미확인':Number(r.progress).toLocaleString('ko-KR',{maximumFractionDigits:1})+'%';
  function stats(rows){
    const total=rows.length,hasProgress=rows.filter(x=>!missingProgress(x)).length;
    const verified=rows.filter(verifiedQuote).length,prepaid=rows.filter(x=>sourceValue(x,'Prepayment')==='YES').length;
    return {total,hasProgress,verified,prepaid,progressPct:total?Math.round(hasProgress/total*100):0,
      quotePct:total?Math.round(verified/total*100):0};
  }
  function filterRows(rows,{query='',stage='',filter='all',sort='name'}={}){
    const q=query.trim().toLocaleLowerCase();
    const out=rows.filter(r=>{
      const text=['Quote Full Name','AMEA','Institution','Customer','Service','Current Stage','Next Action']
        .map(k=>sourceValue(r,k)).join(' ').toLocaleLowerCase();
      if(q&&!text.includes(q))return false;
      if(stage&&stageGroup(r)!==stage)return false;
      if(filter==='prepay'&&sourceValue(r,'Prepayment')!=='YES')return false;
      if(filter==='sif'&&!missingSif(r))return false;
      if(filter==='quote'&&verifiedQuote(r))return false;
      if(filter==='progress'&&!missingProgress(r))return false;
      return true;
    });
    out.sort((a,b)=>{
      const first=Number(a.progress),second=Number(b.progress);
      if(sort==='low')return (missingProgress(a)?101:first)-(missingProgress(b)?101:second);
      if(sort==='high')return (missingProgress(b)?-1:second)-(missingProgress(a)?-1:first);
      if(sort==='attention')return (missingSif(b)?1:0)-(missingSif(a)?1:0)
        ||(verifiedQuote(a)?1:0)-(verifiedQuote(b)?1:0);
      return quoteName(a).localeCompare(quoteName(b),'ko');
    });
    return out;
  }
  async function collectPages(fetcher=fetch){
    const collected=[],seen=new Set(),cursors=new Set();
    let cursor='',time='';
    for(let n=0;n<30;n++){
      const url='/api/feishu/projects'+(cursor?'?cursor='+encodeURIComponent(cursor):'');
      const res=await fetcher(url,{credentials:'same-origin',cache:'no-store'});
      if(!res.ok){
        let error={};try{error=await res.json()}catch(_){}
        const e=new Error(error.error||'FEISHU_API_HTTP_'+res.status);e.status=res.status;throw e;
      }
      const payload=await res.json();
      if(payload.source!=='FEISHU_BASE'||!Array.isArray(payload.items))
        throw new Error('FEISHU_SOURCE_SCHEMA_MISMATCH');
      for(const r of payload.items){
        if(!r||!r.id)continue;
        if(seen.has(r.id))throw new Error('FEISHU_DUPLICATE_RECORD_ID');
        seen.add(r.id);collected.push(r);
      }
      time=payload.generatedAt||time;
      if(!payload.hasMore)return {rows:collected,generatedAt:time};
      const next=payload.nextCursor;
      if(!next||next===cursor||cursors.has(next))throw new Error('FEISHU_BAD_PAGINATION');
      cursors.add(next);cursor=next;
    }
    throw new Error('FEISHU_PAGINATION_LIMIT');
  }
  function card(r,i){
    const p=missingProgress(r)?null:Math.max(0,Math.min(100,Number(r.progress)));
    const state=sourceValue(r,'Quote Match State');
    const type=verifiedQuote(r)?'SFDC Quote Full Name · 검증됨':
      state==='MULTIPLE_QUOTE_REVIEW'?'다수 SFDC Quote · 확인 필요':
      state==='CSS_ORIGINAL_UNVERIFIED'?'CSS 프로젝트 원문 · SFDC Quote 미연결':'Quote 이름 미확인';
    const stage=sourceValue(r,'Current Stage')||'현재 단계 미확인';
    const badge=missingSif(r)?'<span class="state-tag pending">SIF 확인 필요</span>':
      sourceValue(r,'Prepayment')==='YES'?'<span class="state-tag">Prepayment</span>':
      sourceValue(r,'SIF State')==='SUBMITTED'||sourceValue(r,'SIF State')==='APPROVED'?
        '<span class="state-tag">SIF 제출·승인</span>':'<span class="state-tag muted">일정 확인</span>';
    return `<article class="project-card" aria-label="${esc(sourceValue(r,'AMEA'))}">
      <div>
        <div class="project-topline"><span class="code">${esc(sourceValue(r,'AMEA'))}</span><span class="service-tag">${esc(sourceValue(r,'Service')||'서비스 미확인')}</span></div>
        <p class="quote-name">${esc(quoteName(r))}</p>
        <div class="quote-label">${esc(type)}</div>
        <div class="customer">${esc(sourceValue(r,'Institution')||'기관 미확인')} · ${esc(sourceValue(r,'Customer')||'고객 미확인')}</div>
      </div>
      <div>
        <div class="progress-head"><span>프로젝트 진행률</span><span class="percent">${esc(showProgress(r))}</span></div>
        <div class="progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" ${p===null?'':`aria-valuenow="${p}"`} aria-label="프로젝트 진행률">
          <div class="progress-fill" style="width:${p===null?0:p}%"></div>
        </div>
        <div class="progress-note">${esc(stage)}</div>
      </div>
      <div class="project-side">
        ${badge}
        <span class="soft-tag">${esc(sourceValue(r,'PO Evidence')==='REPORT_STATEMENT_INFERRED'?'PO 제출 간주 · 증빙':'PO 원본 확인 필요')}</span>
        <button class="detail-button" type="button" data-detail="${i}">상세 보기 →</button>
      </div>
    </article>`;
  }
  if(typeof module!=='undefined'&&module.exports){
    module.exports={esc,sourceValue,stageGroup,verifiedQuote,missingSif,missingProgress,
      quoteName,showProgress,stats,filterRows,collectPages,card};
  }
  if(typeof document==='undefined')return;
  const $=id=>document.getElementById(id);
  const state={rows:[],filter:'all',visible:35,ready:false,generatedAt:''};
  const apiError=error=>{
    const code=String(error.message||'');
    if(error.status===401||/LOGIN_REQUIRED/.test(code))
      return ['로그인이 필요합니다.','Vercel 계정 소유자로 로그인한 뒤 Feishu 데이터를 다시 확인하세요.',
        '<a href="/api/auth/authorize" class="link">Vercel 계정으로 로그인 →</a>'];
    if(/FEISHU_CREDENTIALS_MISSING/.test(code))
      return ['Feishu Base 서버 연결이 설정되지 않았습니다.',
        'Vercel Production에 FEISHU_APP_ID와 FEISHU_APP_SECRET이 설정되어야 합니다. 브라우저에 비밀키를 입력하지 마세요.',''];
    if(error.status===503)return ['서버 설정을 확인해야 합니다.',esc(code),''];
    return ['Feishu Base 읽기에 실패했습니다.',esc(code)+'. 새로고침 후에도 동일하면 GitHub Actions와 Base 권한을 점검하세요.',''];
  };
  function setNotice(title,detail,action=''){
    $('notice').hidden=false;
    $('notice').innerHTML='<strong>'+esc(title)+'</strong><div>'+esc(detail)+'</div>'+action;
  }
  function clearNotice(){$('notice').hidden=true;$('notice').textContent=''}
  function chartHtml(rows,labelKey,valueKey,kind){
    const records=rows.slice(-8);
    if(!records.length)return '<div class="metric-warning">Feishu Base에 검증된 통계가 없습니다.</div>';
    const maximum=Math.max(1,...records.map(r=>Math.max(0,Number(r[valueKey])||0)));
    const fmt=n=>kind==='quote'?Number(n).toLocaleString('ko-KR'):
      (Number(n)>=1000000?(Number(n)/1000000).toFixed(1)+'M':
       Number(n)>=1000?(Number(n)/1000).toFixed(0)+'K':Number(n).toLocaleString('ko-KR'));
    return '<div class="mini-bars" role="img" aria-label="'+esc(kind==='quote'?'주간 승인 Quote':'월별 Revenue')+'">'
      +records.map(r=>{
        const v=Math.max(0,Number(r[valueKey])||0);
        const height=Math.max(2,Math.round(v/maximum*110));
        const label=kind==='quote'?String(r[labelKey]||'').slice(5):
          String(r[labelKey]||'').slice(5);
        return '<div class="mini-bar-item" title="'+esc(String(r[labelKey])+' : '+fmt(v))+'">'
           +'<span class="mini-value">'+esc(fmt(v))+'</span>'
           +'<div class="mini-column '+(kind==='quote'?'quote':'')+'" style="height:'+height+'px"></div>'
           +'<span class="mini-label">'+esc(label)+'</span></div>';
      }).join('')+'</div>';
  }
  async function loadMetrics(){
    try{
      const response=await fetch('/api/feishu/kpis',{cache:'no-store',credentials:'same-origin'});
      if(!response.ok)throw new Error('HTTP_'+response.status);
      const values=await response.json();
      if(values.source!=='FEISHU_BASE'||!Array.isArray(values.monthly)||!Array.isArray(values.weekly))
        throw new Error('FEISHU_METRICS_INVALID');
      $('monthlyChart').innerHTML=chartHtml(values.monthly,'month','revenueNet','revenue');
      $('weeklyChart').innerHTML=chartHtml(values.weekly,'week','approved','quote');
      $('monthlySource').textContent=values.monthly.length+'개월 검증';
      $('weeklySource').textContent=values.weekly.length+'주 검증';
    }catch(error){
      const msg='Feishu Base 직접 연결 확인 필요 ('+esc(error.message||'API unavailable')+')';
      $('monthlyChart').innerHTML='<div class="metric-warning">'+msg+'</div>';
      $('weeklyChart').innerHTML='<div class="metric-warning">'+msg+'</div>';
      $('monthlySource').textContent='미검증';$('weeklySource').textContent='미검증';
    }
  }
  function renderMetrics(){
    const s=stats(state.rows);
    $('kTotal').textContent=s.total.toLocaleString('ko-KR');
    $('kProgress').textContent=s.hasProgress.toLocaleString('ko-KR');
    $('kQuote').textContent=s.verified.toLocaleString('ko-KR');
    $('kPrepaid').textContent=s.prepaid.toLocaleString('ko-KR');
    $('quoteRate').textContent=s.quotePct+'%';$('progressRate').textContent=s.progressPct+'%';
    $('quoteFill').style.width=s.quotePct+'%';$('progressFill').style.width=s.progressPct+'%';
    $('updated').textContent=state.generatedAt?
      '조회: '+new Date(state.generatedAt).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}):'';
  }
  let shown=[];
  function render(){
    const rows=filterRows(state.rows,{query:$('search').value,stage:$('stage').value,
      filter:state.filter,sort:$('sort').value});
    shown=rows.slice(0,state.visible);
    $('displayCount').textContent=rows.length.toLocaleString('ko-KR')+'개 프로젝트';
    $('projects').innerHTML=shown.length?shown.map(card).join(''):
      '<div class="empty"><strong>표시할 프로젝트가 없습니다</strong>검색어나 필터를 변경해 주세요.</div>';
    $('more').hidden=state.visible>=rows.length;
    $('more').textContent='프로젝트 더 보기 ('+Math.min(rows.length-state.visible,35)+'개)';
  }
  function openDrawer(record){
    $('detailQuote').textContent=quoteName(record);
    $('detailMeta').textContent=sourceValue(record,'AMEA')+' · '+sourceValue(record,'Quote Match State');
    const values=[
      ['기관',sourceValue(record,'Institution')],['고객',sourceValue(record,'Customer')],
      ['서비스',sourceValue(record,'Service')],['현재 진행 단계',sourceValue(record,'Current Stage')],
      ['진행률',showProgress(record)],['Prepayment',sourceValue(record,'Prepayment')],
      ['Prepayment 증빙',sourceValue(record,'Prepayment Evidence')],
      ['SIF 상태',sourceValue(record,'SIF State')],['PO 상태',sourceValue(record,'PO Evidence')],
      ['다음 조치',sourceValue(record,'Next Action')],['근거',sourceValue(record,'Evidence')],
    ];
    $('detailFields').innerHTML=values.map(([k,v])=>'<div class="field"><label>'+esc(k)+
      '</label><div>'+esc(v||'미확인')+'</div></div>').join('');
    $('shade').classList.add('open');$('drawer').classList.add('open');
    $('drawerClose').focus();
  }
  function closeDrawer(){$('drawer').classList.remove('open');$('shade').classList.remove('open')}
  async function refresh(){
    $('refresh').disabled=true;
    $('sourceDot').classList.remove('ready');$('sourceStatus').textContent='Feishu Base 조회 중';
    clearNotice();
    try{
      const result=await collectPages();
      state.rows=result.rows;state.generatedAt=result.generatedAt;state.visible=35;state.ready=true;
      $('sourceDot').classList.add('ready');
      $('sourceStatus').textContent='Feishu Base 연결됨 · '+result.rows.length+'건';
      renderMetrics();render();
    }catch(e){
      state.rows=[];state.ready=false;shown=[];state.visible=35;
      $('sourceStatus').textContent='연결 확인 필요';
      const [title,detail,action]=apiError(e);setNotice(title,detail,action);
      $('projects').innerHTML='<div class="empty"><strong>Feishu Base에서 데이터를 읽지 못했습니다</strong>실제 Base 데이터 연결이 확인되면 프로젝트 카드가 표시됩니다.</div>';
      for(const k of ['kTotal','kProgress','kQuote','kPrepaid','quoteRate','progressRate'])$(k).textContent='—';
      $('quoteFill').style.width='0';$('progressFill').style.width='0';$('displayCount').textContent='';
      $('more').hidden=true;
    }finally{$('refresh').disabled=false}
  }
  $('refresh').addEventListener('click',refresh);
  $('search').addEventListener('input',()=>{state.visible=35;render()});
  for(const id of ['sort','stage'])$(id).addEventListener('change',()=>{state.visible=35;render()});
  for(const btn of document.querySelectorAll('.chip[data-filter]'))btn.addEventListener('click',()=>{
    state.filter=btn.dataset.filter;state.visible=35;
    document.querySelectorAll('.chip[data-filter]').forEach(b=>b.classList.toggle('active',b===btn));
    render();
  });
  $('more').addEventListener('click',()=>{state.visible+=35;render()});
  $('projects').addEventListener('click',event=>{
    const btn=event.target.closest('button[data-detail]');
    if(btn&&shown[Number(btn.dataset.detail)])openDrawer(shown[Number(btn.dataset.detail)]);
  });
  $('drawerClose').addEventListener('click',closeDrawer);
  $('shade').addEventListener('click',closeDrawer);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')closeDrawer()});
  refresh();
  loadMetrics();
})();
