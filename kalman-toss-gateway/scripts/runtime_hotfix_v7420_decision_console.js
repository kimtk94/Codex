/* KALMAN_DECISION_CONSOLE_HOTFIX_V7422
 * Runtime-only UI hotfix for production v7.4.20 loader.
 * Does not submit orders or modify server/Neon state.
 */
;(() => {
  if (window.__KALMAN_DECISION_CONSOLE_HOTFIX_V7422__) return;
  window.__KALMAN_DECISION_CONSOLE_HOTFIX_V7422__ = true;

  const UI_VOCAB_VERSION = 'kalman-ui-v1.1';

  const BENCH = {
    asOf: '2026-09-18T14:30:00Z',
    snapshots: 27,
    top1: {avg: -0.0011658402045675545, std: 0.026154211365843665, compounded: -0.03946636494305267},
    top6: {avg: -0.0013610641064273172, std: 0.011488256024007317, compounded: -0.03775952338499344}
  };

  function E(v){return String(v == null ? '' : v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
  function P(v){const x=Number(v);return Number.isFinite(x)?(x*100).toFixed(2)+'%':'—'}
  function M(v){return new Intl.NumberFormat('ko-KR',{style:'currency',currency:'KRW',maximumFractionDigits:0}).format(v)}
  function T(v){const d=new Date(v);return Number.isNaN(d.getTime())?'—':d.toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}
  function pill(text,kind){return '<span class="pill '+(kind||'')+'">'+E(text)+'</span>'}

  function addStyle(){
    if(document.getElementById('kalmanDecisionHotfixStyle'))return;
    const s=document.createElement('style');
    s.id='kalmanDecisionHotfixStyle';
    s.textContent=[
      '.command-grid.kalman-decision-grid{grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);align-items:stretch}',
      '.kalman-execution-panel{grid-row:span 2;grid-column:auto!important}',
      '.kalman-execution-hero{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;padding:8px 0 12px}',
      '.kalman-execution-hero>div{display:flex;flex-direction:column}.kalman-execution-hero small{font-size:10px;color:#8293b2;font-weight:850;letter-spacing:.06em}',
      '.kalman-execution-hero strong{font-size:34px;line-height:1.05;margin:3px 0}.kalman-execution-hero span:not(.pill){font-size:12px;color:#a8b5cc}',
      '.kalman-rule-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px}.kalman-rule-grid>div,.kalman-bench-col{background:#0e182a;border:1px solid #24334f;border-radius:10px;padding:9px;display:flex;flex-direction:column}',
      '.kalman-rule-grid span,.kalman-bench-col span{font-size:9px;color:#8293b2;font-weight:850;letter-spacing:.05em}.kalman-rule-grid b{font-size:14px;margin-top:2px}.kalman-rule-grid small,.kalman-bench-col small{font-size:9px;color:#72819e}',
      '.kalman-gates{display:flex;gap:5px;flex-wrap:wrap;margin-top:10px}.kalman-bench-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:8px}.kalman-bench-col b{font-size:20px;margin:2px 0}',
      '.kalman-bench-foot{display:flex;justify-content:space-between;gap:12px;padding:8px 2px 5px;font-size:10px;color:#8293b2}.kalman-bench-foot b{color:#d7e0f2}',
      '.kalman-exec-ledger{margin-top:18px}.kalman-offline{display:flex;justify-content:space-between;align-items:center;gap:14px;background:#0e1729;border:1px dashed #3a4864;border-radius:12px;padding:14px}.kalman-offline b{color:var(--warn)}.kalman-offline span{display:block;color:var(--muted);font-size:11px;margin-top:3px}',
      '@media(max-width:900px){.command-grid.kalman-decision-grid{grid-template-columns:1fr}.kalman-execution-panel{grid-row:auto}}',
      '@media(max-width:520px){.kalman-rule-grid,.kalman-bench-grid{grid-template-columns:1fr}.kalman-execution-hero strong{font-size:28px}}',
      '#accountSectionK23,#kalmanExecutionLedger{display:none}',
      '.operations-mode #accountSectionK23,.operations-mode #kalmanExecutionLedger{display:block}',
      '.operations-mode #accountSectionK23{order:3}.operations-mode #kalmanExecutionLedger{order:4}',
      '.operations-mode #content{display:none}',
      '.primary-tabs{flex-wrap:nowrap!important;overflow-x:auto;overflow-y:hidden;scrollbar-width:none;-webkit-overflow-scrolling:touch}',
      '.primary-tabs::-webkit-scrollbar{display:none}.primary-tabs .tab{flex:0 0 auto;white-space:nowrap}',
      '@media(max-width:430px){.product-head{display:block}.header-status{margin-top:10px;justify-content:flex-start;flex-wrap:wrap}}'
    ].join('');
    document.head.appendChild(s);
  }

  function state(){try{return typeof kalmanCommandState==='object'&&kalmanCommandState?kalmanCommandState:{}}catch(_){return {}}}

  function snapshotValidity(j){
    const dataTs=Date.parse(j&&j.data_as_of||''),staleTs=Date.parse(j&&j.stale_after||'');
    const age=Number.isFinite(dataTs)?Math.max(0,(Date.now()-dataTs)/60000):Infinity;
    const expired=(j&&typeof j.effective_stale==='boolean')?j.effective_stale:(Number.isFinite(staleTs)?Date.now()>=staleTs:true);
    return {valid:expired===false,expired:expired!==false,ageMinutes:age};
  }
  function entryFreshness(j){
    const sv=snapshotValidity(j);
    return {fresh:sv.valid&&Number.isFinite(sv.ageMinutes)&&sv.ageMinutes<=90,ageMinutes:sv.ageMinutes,snapshotValid:sv.valid};
  }
  function dotLabel(valid){
    return '<span class="health-dot '+(valid?'good-dot':'warn-dot')+'"></span>'+(valid?'스냅샷 유효':'스냅샷 만료');
  }
  try{
    staleBadge=function(x){return x?badge('스냅샷 만료','warn'):badge('스냅샷 유효','ok');};
    executionFreshness=function(j){return entryFreshness(j);};
  }catch(_){}

  function brokerOnline(){
    const s=state();
    if(s.account)return s.account.status!=='OFFLINE';
    const a=document.querySelector('#account');
    if(!a)return false;
    const txt=(a.textContent||'').toUpperCase();
    return txt.includes('TOSS 연결') && !txt.includes('실패') && !txt.includes('OFFLINE');
  }

  function latestSignal(){
    const s=state(),us=s.us||{},p=us.payload||{};
    const sel=(p.source_payload&&p.source_payload.today_selector)||p.today_selector||(p.summary&&p.summary.today_selector)||{};
    const assets=p.assets||p.top3||[];
    const symbol=String(sel.selected_symbol||(assets[0]&&assets[0].symbol)||'—').toUpperCase();
    return {
      symbol,
      asOf:us.data_as_of||null,
      canary:sel.allow_trade_shadow===true&&sel.shadow_entry_this_signal===true
    };
  }

  function ensureShell(){
    const footer=document.querySelector('footer');
    if(footer){footer.textContent='Production v7.4.20 · UI v7.4.23 · 조회 전용';footer.dataset.uiVocab=UI_VOCAB_VERSION;}
    const header=document.querySelector('.header-status');
    if(header&&!document.querySelector('#headerServerState')){
      const p=document.createElement('span');
      p.id='headerServerState';p.className='pill warn';p.textContent='SERVER —';
      header.insertBefore(p,header.lastElementChild);
      if(header.lastElementChild)header.lastElementChild.textContent='조회 전용';
    }

    const grid=document.querySelector('.command-grid');
    if(!grid)return;
    grid.classList.add('kalman-decision-grid');

    const panels=Array.from(grid.querySelectorAll('.command-panel'));
    const model=panels.find(x=>x.querySelector('#commandModel'));
    const health=panels.find(x=>x.querySelector('#commandHealth'));
    const next=panels.find(x=>x.querySelector('#commandNextActions'));

    if(next){
      next.classList.add('kalman-execution-panel');
      const k=next.querySelector('.panel-kicker');if(k)k.textContent='자동매매 · 실행 조건';
      grid.insertBefore(next,grid.firstChild);
    }
    if(model){const k=model.querySelector('.panel-kicker');if(k)k.textContent='R5.1 · 모델 순위';}

    if(!document.querySelector('#commandBenchmark')){
      const a=document.createElement('article');
      a.className='command-panel';
      a.innerHTML='<div class="panel-kicker">연구 벤치마크 · TOP-1 vs TOP-6</div><div id="commandBenchmark"></div>';
      if(health)grid.insertBefore(a,health);else grid.appendChild(a);
    }
    if(health){const k=health.querySelector('.panel-kicker');if(k)k.textContent='시스템 · Toss';}

    const accountSection=document.querySelector('.account');
    if(accountSection)accountSection.id='accountSectionK23';
    const sub=document.querySelector('.account .muted');
    if(sub&&sub.parentElement&&sub.parentElement.querySelector('h2'))sub.textContent='Toss Securities · 서버 연결 시 실계좌 표시';

    const tabs=document.querySelector('.primary-tabs');
    if(tabs&&!document.querySelector('#operationsTab')){
      const op=document.createElement('button');
      op.id='operationsTab';op.type='button';op.className='tab';op.textContent='운영';
      tabs.appendChild(op);
      op.addEventListener('click',()=>{
        document.body.classList.remove('universe-mode');
        document.body.classList.add('operations-mode');
        tabs.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===op));
        history.replaceState(null,'','?view=operations');
      });
      tabs.querySelectorAll('.tab[data-m]').forEach(x=>x.addEventListener('click',()=>document.body.classList.remove('operations-mode')));
      const u=document.querySelector('#universeTab');if(u)u.addEventListener('click',()=>document.body.classList.remove('operations-mode'));
    }
    if(tabs&&!document.querySelector('#kalmanExecutionLedger')){
      const sec=document.createElement('section');
      sec.id='kalmanExecutionLedger';
      sec.className='card section kalman-exec-ledger';
      sec.innerHTML='<div class="section-head"><div><div class="eyebrow">실매매 기록 · NEON MIRROR</div><h2>실매매 기록</h2><div class="muted">실제 자동매매 주문·체결만 표시 · Shadow/연구 결과와 분리</div></div><span class="pill">미러 연결 대기</span></div><div class="kalman-offline"><div><b>Neon 실매매 미러 연결 대기</b><span>현재 Production hotfix에는 실매매 미러 API가 아직 연결되지 않았습니다. Toss 전체 거래내역 상태는 여기서 판단하지 않습니다.</span></div></div>';
      tabs.parentNode.insertBefore(sec,tabs);
    }
  }

  function renderBenchmark(){
    const box=document.querySelector('#commandBenchmark');if(!box)return;
    const d=BENCH.top6.avg-BENCH.top1.avg;
    box.innerHTML=
      '<div class="kalman-bench-grid">'+
        '<div class="kalman-bench-col"><span>TOP-1 · 4B 기준</span><b>평균 '+P(BENCH.top1.avg)+'</b><small>변동성 '+P(BENCH.top1.std)+' · 표본 '+BENCH.snapshots+'</small></div>'+
        '<div class="kalman-bench-col"><span>TOP-6 동일비중 · 4B 기준</span><b>평균 '+P(BENCH.top6.avg)+'</b><small>변동성 '+P(BENCH.top6.std)+' · 표본 '+BENCH.snapshots+'</small></div>'+
      '</div>'+
      '<div class="kalman-bench-foot"><span>왕복비용 10bp 가정 · 4시간 구간 중첩 · 기준 '+T(BENCH.asOf)+'</span><b>평균 차이 '+P(d)+'</b></div>'+
      '<div class="small"><b>연구용 벤치마크:</b> -3% 손절, +20% 익절, 모델 교체는 포함하지 않습니다. 구간이 서로 겹치므로 연속 복리값은 포트폴리오 누적수익으로 표시하지 않습니다.</div>';
  }

  function renderPlan(){
    const box=document.querySelector('#commandNextActions');if(!box)return;
    const sig=latestSignal(),s=state();
    const tossOnline=brokerOnline();
    const sv=snapshotValidity(s.us||{data_as_of:sig.asOf});
    const ef=entryFreshness(s.us||{data_as_of:sig.asOf});
    const signalTimeFresh=ef.fresh;
    const canaryShape=sig.canary===true;
    let headline='실행 판정 확인 불가';
    if(!sv.valid)headline='스냅샷 만료';
    else if(!signalTimeFresh)headline='진입 신호 만료';
    else if(!canaryShape)headline='CANARY 조건 미충족';
    else if(!tossOnline)headline='Toss 오프라인';

    box.className='';
    box.innerHTML=
      '<div class="kalman-execution-hero"><div><small>'+headline+'</small><strong>'+E(sig.symbol)+'</strong><span>최근 모델 신호 · '+T(sig.asOf)+'</span></div>'+pill('대기','warn')+'</div>'+
      '<div class="kalman-rule-grid">'+
        '<div><span>실매매 정책</span><b>SHADOW_CANARY</b><small>서버 readiness 기준</small></div>'+
        '<div><span>진입 금액</span><b>'+M(5000)+'</b><small>신규 진입 1회 기준</small></div>'+
        '<div><span>손절 / 익절</span><b>-3% / +20%</b><small>실매매 청산 규칙</small></div>'+
        '<div><span>교체 / 최대 보유</span><b>ROTATE ON</b><small>4 canonical bucket 최대</small></div>'+
      '</div>'+
      '<div class="kalman-gates">'+
        pill(sv.valid?'스냅샷 유효':'스냅샷 만료',sv.valid?'ok':'warn')+
        pill(signalTimeFresh?'진입 신호 유효 (<90분)':'진입 신호 만료',signalTimeFresh?'ok':'warn')+
        pill(canaryShape?'CANARY 조건 충족':'CANARY 조건 미충족',canaryShape?'ok':'warn')+
        pill(tossOnline?'Toss 연결됨':'Toss 오프라인',tossOnline?'ok':'warn')+
        pill('실행 판정 확인 불가','')+
      '</div>'+
      '<div class="next-actions-note"><b>구분:</b> 현재 Production hotfix는 서버 readiness API가 아직 정식 배포되지 않아 진입 후보를 추정하지 않습니다. 정식 v7.4.23에서 실제 auto-trade와 동일한 읽기 전용 판정을 사용합니다.</div>';
  }

  function renderServerState(){
    const online=brokerOnline();
    const h=document.querySelector('#headerServerState');
    if(h){h.className='pill '+(online?'ok':'warn');h.textContent=online?'Toss 연결됨':'Toss 오프라인';}

    if(!online){
      const account=document.querySelector('#account');
      if(account){
        const txt=(account.textContent||'').toLowerCase();
        if(txt.includes('불러오지 못')||txt.includes('실패')||txt.includes('gateway')){
          account.innerHTML='<div class="kalman-offline"><div><b>Toss 오프라인</b><span>Toss 계좌/주문 링크가 오프라인입니다. 모델·신호 화면은 계속 사용할 수 있습니다.</span></div>'+pill('NO BROKER DATA','warn')+'</div>';
        }
      }
    }
  }

  // Research universe is not the live auto-trade selector.
  try{
    universeActionFor=function(asset,held,fx,fresh){
      var rank=Number(asset&&asset.rank||999),isTop=rank<=UNIVERSE_TOP_COUNT;
      var currentKrw=(held&&fx)?marketValueUsd(held)*n(fx.rate||0):0;
      var gap=Math.max(0,UNIVERSE_TARGET_KRW-currentKrw);
      if(isTop){
        if(held&&gap<UNIVERSE_MIN_ORDER_KRW)return{label:'목표 도달',kind:'hold',detail:'연구 Top-6 #'+rank};
        return{label:held?'추가 미리보기':'편입 미리보기',kind:'watch',detail:(gap>=UNIVERSE_MIN_ORDER_KRW?M(Math.min(UNIVERSE_TARGET_KRW,Math.floor(gap)))+' · ':'')+'연구 Top-6 #'+rank};
      }
      if(held)return{label:'제외 미리보기',kind:'watch',detail:'OUTSIDE 연구 Top-6'};
      return{label:'관찰',kind:'watch',detail:'RANK #'+rank};
    };
  }catch(_){}

  try{
    universeFilteredRows=function(){
      var rows=universeState.rows.slice();
      var q=String($('#universeSearch')&&$('#universeSearch').value||'').trim().toUpperCase();
      var f=String($('#universeFilter')&&$('#universeFilter').value||'ALL');
      var sort=String($('#universeSort')&&$('#universeSort').value||'RANK');
      rows=rows.filter(function(x){return !q||x.symbol.includes(q);});
      if(f==='TOP6')rows=rows.filter(function(x){return x.top6;});
      if(f==='HELD')rows=rows.filter(function(x){return !!x.held;});
      if(f==='ACTION')rows=rows.filter(function(x){return String(x.action&&x.action.label||'').includes('미리보기');});
      if(f==='WATCH')rows=rows.filter(function(x){return String(x.action&&x.action.label||'')==='관찰';});
      rows.sort(function(a,b){
        if(sort==='SCORE')return (n(b.model_score)||-Infinity)-(n(a.model_score)||-Infinity);
        if(sort==='SYMBOL')return a.symbol.localeCompare(b.symbol);
        if(sort==='WEIGHT')return (n(b.position_weight_r4_vol_target)||0)-(n(a.position_weight_r4_vol_target)||0);
        return Number(a.rank||999)-Number(b.rank||999);
      });
      return rows;
    };
  }catch(_){}

  // Shadow/model-evaluation ledger labels must not look like broker execution.
  try{
    const originalUsLedgerTable=usLedgerTable;
    usLedgerTable=function(j){
      return originalUsLedgerTable(j)
        .replace('2026 R5.1 Ledger','R5.1 SHADOW · 모델 평가 기록')
        .replace(/>FORWARD</g,'>모델 Forward<').replace(/>FORWARD<\/span>/g,'>모델 Forward</span>');
    };
  }catch(_){}

  try{
    renderGlobal=function(j){
      const s=state(),p=j&&j.payload||{},sum=p.summary||{},direct={KR:s.kr,US:s.us,CRYPTO:s.crypto};
      const cards=['KR','US','CRYPTO'].map(k=>{
        const x=direct[k]||{},xp=x.payload||{},sm=xp.summary||{},assets=xp.assets||xp.top3||[];
        const lead=k==='KR'?(sm.overall_action_label||sm.regime||(assets[0]&&assets[0].name)):k==='US'?(sm.selected_symbol||(assets[0]&&assets[0].symbol)||sm.market_risk):(sm.model_version||sm.regime||(assets[0]&&assets[0].symbol)||'Crypto');
        const sv=snapshotValidity(x);
        return '<div class="card"><div class="section-title"><h3>'+(k==='KR'?'한국장':k==='US'?'미국장':'Crypto')+'</h3>'+pill(sv.valid?'스냅샷 유효':'스냅샷 만료',sv.valid?'ok':'warn')+'</div><div class="kpi">'+E(lead||'—')+'</div><div class="small">'+T(x.data_as_of)+'</div></div>';
      }).join('');
      return '<div class="summary">'+pill('최신 시장 스냅샷','')+' '+pill(sum.state||'GLOBAL','')+' '+(sum.trade_signal?pill('거래 신호','warn'):pill('거래 신호 없음',''))+'</div><div class="grid">'+cards+'</div>';
    };
  }catch(_){}

  let snapshotRefreshBusy=false;
  async function refreshSnapshotPanels(){
    if(snapshotRefreshBusy)return;
    snapshotRefreshBusy=true;
    try{
      const [us,kr,cr]=await Promise.all([
        fetch('/api/dashboard?market=US',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(Error('US '+r.status))),
        fetch('/api/dashboard?market=KR',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(Error('KR '+r.status))),
        fetch('/api/dashboard?market=CRYPTO',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(Error('CRYPTO '+r.status)))
      ]);
      const s=state();s.us=us;s.kr=kr;s.crypto=cr;
      const model=document.querySelector('#commandModel');
      if(model){
        const p=us.payload||{},a=(p.assets||p.top3||[]).slice(0,6),sv=snapshotValidity(us),ef=entryFreshness(us);
        const ranks=a.map((x,i)=>'<div class="command-rank"><span>'+(i+1)+'</span><b>'+E(x.symbol||'—')+'</b><small>'+((Number(x.model_score)||0)*10000).toFixed(2)+' bp</small></div>').join('');
        model.className='';
        model.innerHTML='<div class="command-model-head"><div><small>TOP RANK</small><strong>'+E(a[0]&&a[0].symbol||'—')+'</strong></div><div class="right">'+dotLabel(sv.valid)+'<small>'+T(us.data_as_of)+' · '+(ef.fresh?'진입 신호 유효 (&lt;90분)':'진입 신호 만료')+'</small></div></div><div class="command-ranks">'+ranks+'</div>';
      }
      const health=document.querySelector('#commandHealth');
      if(health){
        const uv=snapshotValidity(us),kv=snapshotValidity(kr),cv=snapshotValidity(cr);
        const account=s.account||null,bot=account&&account.trading_status||null;
        const known=Boolean(bot&&typeof bot.usFractionalOrderWindowOpen==='boolean');
        const open=known&&bot.usFractionalOrderWindowOpen===true;
        const row=(label,valid,j)=>'<div class="health-row"><span>'+label+'</span><b>'+dotLabel(valid)+'</b><small>'+T(j&&j.data_as_of)+' · 유효기한 '+T(j&&j.stale_after)+'</small></div>';
        health.className='';
        health.innerHTML=
          row('US 데이터',uv.valid,us)+row('KR 데이터',kv.valid,kr)+row('Crypto 데이터',cv.valid,cr)+
          '<div class="health-row"><span>미국 주문시간</span><b><span class="health-dot '+(open?'good-dot':'warn-dot')+'"></span>'+(known?(open?'주문 가능':'마감'):'확인 불가')+'</b><small>'+(known?'Toss 시장 캘린더':'Toss 연결 필요')+'</small></div>';
        const head=document.querySelector('#headerDataState');
        if(head){const ok=uv.valid&&kv.valid&&cv.valid;head.className='pill '+(ok?'ok':'warn');head.textContent=ok?'데이터 정상':'데이터 확인 필요';}
      }
      renderPlan();
      try{
        const activeGlobal=document.querySelector('.tab[data-m="GLOBAL"].active');
        const content=document.querySelector('#content');
        if(activeGlobal&&content&&typeof renderGlobal==='function'){
          const g=(typeof marketCache==='object'&&marketCache&&marketCache.GLOBAL)||s.global||{};
          content.innerHTML=renderGlobal(g);
        }
      }catch(_){}
    }catch(e){
      const h=document.querySelector('#headerDataState');
      if(h){h.className='pill warn';h.textContent='데이터 확인 필요';}
    }finally{snapshotRefreshBusy=false;}
  }

  let scheduled=false;
  function apply(){
    scheduled=false;
    addStyle();ensureShell();
    if(new URLSearchParams(location.search).get('view')==='operations')document.body.classList.add('operations-mode');
    renderBenchmark();renderPlan();renderServerState();refreshSnapshotPanels();
    const content=document.querySelector('#content');
    if(content){
      content.querySelectorAll('th').forEach(th=>{
        const t=th.textContent.trim();
        if(t==='Model Plan')th.textContent='연구 미리보기';
        if(t==='4h Target')th.textContent='모델 4h 목표';
        if(t==='Δ Target')th.textContent='모델 Δ';
      });
      content.querySelectorAll('.universe-title .muted').forEach(x=>{if(x.textContent.includes('예정 액션'))x.textContent='전체 후보 · R5.1 점수 · Top-6 연구 미리보기 · 실제 주문과 분리';});
      content.querySelectorAll('.u-kpi span').forEach(x=>{if(x.textContent.trim()==='MODEL PLAN')x.textContent='연구 미리보기';});
      const uf=document.querySelector('#universeFilter option[value="ACTION"]');if(uf)uf.textContent='미리보기';
      content.querySelectorAll('.universe-title .pill').forEach(x=>{const sv=snapshotValidity(state().us||{});x.textContent=sv.valid?'스냅샷 유효':'스냅샷 만료';x.className='pill '+(sv.valid?'ok':'warn');});
    }
  }
  function schedule(){
    if(scheduled)return;
    scheduled=true;
    requestAnimationFrame(apply);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',schedule,{once:true});else schedule();
  [250,900,2000,4000].forEach(ms=>setTimeout(schedule,ms));
  setTimeout(() => {
    const refresh=document.querySelector('#accountRefresh');
    if(refresh&&!refresh.dataset.kalmanDecisionBound){
      refresh.dataset.kalmanDecisionBound='1';
      refresh.addEventListener('click',()=>setTimeout(schedule,1200));
    }
  },1200);
  window.addEventListener('focus',schedule);
})();
