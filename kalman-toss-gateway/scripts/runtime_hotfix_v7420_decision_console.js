/* KALMAN_DECISION_CONSOLE_HOTFIX_V7422
 * Runtime-only UI hotfix for production v7.4.20 loader.
 * Does not submit orders or modify server/Neon state.
 */
;(() => {
  if (window.__KALMAN_DECISION_CONSOLE_HOTFIX_V7422__) return;
  window.__KALMAN_DECISION_CONSOLE_HOTFIX_V7422__ = true;

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
      '@media(max-width:520px){.kalman-rule-grid,.kalman-bench-grid{grid-template-columns:1fr}.kalman-execution-hero strong{font-size:28px}}'
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
    return '<span class="health-dot '+(valid?'good-dot':'warn-dot')+'"></span>'+(valid?'VALID':'EXPIRED');
  }
  try{
    staleBadge=function(x){return x?badge('SNAPSHOT EXPIRED','warn'):badge('SNAPSHOT VALID','ok');};
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
    if(footer)footer.textContent='Production runtime v7.4.20 · UI contract v7.4.22 · READ ONLY';
    const header=document.querySelector('.header-status');
    if(header&&!document.querySelector('#headerServerState')){
      const p=document.createElement('span');
      p.id='headerServerState';p.className='pill warn';p.textContent='SERVER —';
      header.insertBefore(p,header.lastElementChild);
      if(header.lastElementChild)header.lastElementChild.textContent='READ ONLY';
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
      const k=next.querySelector('.panel-kicker');if(k)k.textContent='AUTO-TRADE · SERVER CONTRACT';
      grid.insertBefore(next,grid.firstChild);
    }
    if(model){const k=model.querySelector('.panel-kicker');if(k)k.textContent='R5.1 · MODEL RANKING';}

    if(!document.querySelector('#commandBenchmark')){
      const a=document.createElement('article');
      a.className='command-panel';
      a.innerHTML='<div class="panel-kicker">RESEARCH BENCHMARK · TOP1 vs TOP6</div><div id="commandBenchmark"></div>';
      if(health)grid.insertBefore(a,health);else grid.appendChild(a);
    }
    if(health){const k=health.querySelector('.panel-kicker');if(k)k.textContent='SYSTEM / BROKER';}

    const sub=document.querySelector('.account .muted');
    if(sub&&sub.parentElement&&sub.parentElement.querySelector('h2'))sub.textContent='Toss Securities · 서버 연결 시 실계좌 표시';

    const tabs=document.querySelector('.primary-tabs');
    if(tabs&&!document.querySelector('#kalmanExecutionLedger')){
      const sec=document.createElement('section');
      sec.id='kalmanExecutionLedger';
      sec.className='card section kalman-exec-ledger';
      sec.innerHTML='<div class="section-head"><div><div class="eyebrow">LIVE EXECUTION MIRROR · NEON</div><h2>실매매 체결 미러</h2><div class="muted">Shadow/model 평가와 분리 · 실제 bot 주문/체결 mirror</div></div><span class="pill">MIRROR PENDING</span></div><div class="kalman-offline"><div><b>Neon execution mirror 미연결</b><span>현재 Production hotfix에는 execution mirror API가 아직 연결되지 않았습니다. Broker 전체 거래내역 상태는 여기서 판단하지 않습니다.</span></div></div>';
      tabs.parentNode.insertBefore(sec,tabs);
    }
  }

  function renderBenchmark(){
    const box=document.querySelector('#commandBenchmark');if(!box)return;
    const d=BENCH.top6.avg-BENCH.top1.avg;
    box.innerHTML=
      '<div class="kalman-bench-grid">'+
        '<div class="kalman-bench-col"><span>TOP-1 · 4B ONLY</span><b>avg '+P(BENCH.top1.avg)+'</b><small>σ '+P(BENCH.top1.std)+' · n='+BENCH.snapshots+'</small></div>'+
        '<div class="kalman-bench-col"><span>TOP-6 EQUAL · 4B ONLY</span><b>avg '+P(BENCH.top6.avg)+'</b><small>σ '+P(BENCH.top6.std)+' · n='+BENCH.snapshots+'</small></div>'+
      '</div>'+
      '<div class="kalman-bench-foot"><span>10bp round-trip approximation · overlapping 4h windows · through '+T(BENCH.asOf)+'</span><b>Δ avg '+P(d)+'</b></div>'+
      '<div class="small"><b>Research benchmark only:</b> -3% stop, +20% take-profit, model rotation은 포함하지 않습니다. sequence compounded는 겹치는 window 때문에 포트폴리오 누적수익으로 표시하지 않습니다.</div>';
  }

  function renderPlan(){
    const box=document.querySelector('#commandNextActions');if(!box)return;
    const sig=latestSignal(),online=brokerOnline();
    const ef=entryFreshness(state().us||{data_as_of:sig.asOf});
    const modelEligible=ef.fresh&&sig.canary;
    let headline='TRADING LINK OFFLINE',status='NOT EXECUTABLE',kind='warn';
    if(online&&!modelEligible)headline='ENTRY SIGNAL EXPIRED';
    if(online&&modelEligible){headline='BROKER CONNECTED';status='SERVER GATES UNKNOWN';}

    box.className='';
    box.innerHTML=
      '<div class="kalman-execution-hero"><div><small>'+headline+'</small><strong>'+E(sig.symbol)+'</strong><span>last canary candidate · '+T(sig.asOf)+'</span></div>'+pill(status,kind)+'</div>'+
      '<div class="kalman-rule-grid">'+
        '<div><span>LIVE POLICY</span><b>SHADOW_CANARY</b><small>SHADOW signal is expected</small></div>'+
        '<div><span>TARGET SIZE</span><b>'+M(5000)+'</b><small>per new entry</small></div>'+
        '<div><span>LIVE EXITS</span><b>-3% / +20%</b><small>stop loss · take profit</small></div>'+
        '<div><span>EARLY / MAX EXIT</span><b>ROTATE ON</b><small>4 canonical buckets max</small></div>'+
      '</div>'+
      '<div class="kalman-gates">'+
        pill(modelEligible?'ENTRY SIGNAL <90M':'ENTRY SIGNAL EXPIRED',modelEligible?'ok':'warn')+
        pill(online?'TRADING LINK ONLINE':'TRADING LINK OFFLINE',online?'ok':'warn')+
        pill('SERVER LIVE GATES NOT CONFIRMED','warn')+
        pill('EXECUTION MIRROR PENDING','')+
      '</div>'+
      '<div class="next-actions-note"><b>구분:</b> Top-6는 research benchmark/portfolio preview이며 실제 자동매매 selector가 아닙니다. 실제 신규 진입 후보는 SHADOW_CANARY 조건을 통과한 단일 R5.1 signal입니다. 웹은 주문을 제출하지 않습니다.</div>';
  }

  function renderServerState(){
    const online=brokerOnline();
    const h=document.querySelector('#headerServerState');
    if(h){h.className='pill '+(online?'ok':'warn');h.textContent=online?'TRADING LINK ONLINE':'TRADING LINK OFFLINE';}

    if(!online){
      const account=document.querySelector('#account');
      if(account){
        const txt=(account.textContent||'').toLowerCase();
        if(txt.includes('불러오지 못')||txt.includes('실패')||txt.includes('gateway')){
          account.innerHTML='<div class="kalman-offline"><div><b>TRADING LINK OFFLINE</b><span>Toss 계좌/주문 링크가 오프라인입니다. 모델·신호 화면은 계속 사용할 수 있습니다.</span></div>'+pill('NO BROKER DATA','warn')+'</div>';
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
        if(held&&gap<UNIVERSE_MIN_ORDER_KRW)return{label:'AT TARGET',kind:'hold',detail:'RESEARCH TOP-6 #'+rank};
        return{label:held?'TOP-UP PREVIEW':'ADD PREVIEW',kind:'watch',detail:(gap>=UNIVERSE_MIN_ORDER_KRW?M(Math.min(UNIVERSE_TARGET_KRW,Math.floor(gap)))+' · ':'')+'RESEARCH TOP-6 #'+rank};
      }
      if(held)return{label:'EXIT PREVIEW',kind:'watch',detail:'OUTSIDE RESEARCH TOP-6'};
      return{label:'WATCH',kind:'watch',detail:'RANK #'+rank};
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
      if(f==='ACTION')rows=rows.filter(function(x){return String(x.action&&x.action.label||'').includes('PREVIEW');});
      if(f==='WATCH')rows=rows.filter(function(x){return String(x.action&&x.action.label||'')==='WATCH';});
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
        .replace('2026 R5.1 Ledger','R5.1 SHADOW / MODEL EVALUATION LEDGER')
        .replace(/>FORWARD</g,'>MODEL FORWARD<').replace(/>FORWARD<\/span>/g,'>MODEL FORWARD</span>');
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
        model.innerHTML='<div class="command-model-head"><div><small>TOP RANK</small><strong>'+E(a[0]&&a[0].symbol||'—')+'</strong></div><div class="right">'+dotLabel(sv.valid)+'<small>'+T(us.data_as_of)+' · entry signal '+(ef.fresh?'&lt;90m':'expired')+'</small></div></div><div class="command-ranks">'+ranks+'</div>';
      }
      const health=document.querySelector('#commandHealth');
      if(health){
        const uv=snapshotValidity(us),kv=snapshotValidity(kr),cv=snapshotValidity(cr);
        const account=s.account||null,bot=account&&account.trading_status||null;
        const known=Boolean(bot&&typeof bot.usFractionalOrderWindowOpen==='boolean');
        const open=known&&bot.usFractionalOrderWindowOpen===true;
        const row=(label,valid,j)=>'<div class="health-row"><span>'+label+'</span><b>'+dotLabel(valid)+'</b><small>'+T(j&&j.data_as_of)+' · valid until '+T(j&&j.stale_after)+'</small></div>';
        health.className='';
        health.innerHTML=
          row('US SNAPSHOT',uv.valid,us)+row('KR SNAPSHOT',kv.valid,kr)+row('CRYPTO SNAPSHOT',cv.valid,cr)+
          '<div class="health-row"><span>US ORDER WINDOW</span><b><span class="health-dot '+(open?'good-dot':'warn-dot')+'"></span>'+(known?(open?'OPEN':'CLOSED'):'UNKNOWN')+'</b><small>'+(known?'Toss market calendar':'trading link required')+'</small></div>';
        const head=document.querySelector('#headerDataState');
        if(head){const ok=uv.valid&&kv.valid&&cv.valid;head.className='pill '+(ok?'ok':'warn');head.textContent=ok?'SNAPSHOTS VALID':'SNAPSHOT CHECK';}
      }
      renderPlan();
    }catch(e){
      const h=document.querySelector('#headerDataState');
      if(h){h.className='pill warn';h.textContent='SNAPSHOT CHECK';}
    }finally{snapshotRefreshBusy=false;}
  }

  let scheduled=false;
  function apply(){
    scheduled=false;
    addStyle();ensureShell();renderBenchmark();renderPlan();renderServerState();refreshSnapshotPanels();
    const content=document.querySelector('#content');
    if(content){
      content.querySelectorAll('th').forEach(th=>{
        const t=th.textContent.trim();
        if(t==='Model Plan')th.textContent='Research Preview';
        if(t==='4h Target')th.textContent='Model 4h Target';
        if(t==='Δ Target')th.textContent='Model Δ';
      });
      content.querySelectorAll('.universe-title .muted').forEach(x=>{if(x.textContent.includes('예정 액션'))x.textContent='전체 후보 · 현재 R5.1 score · Top-6 research preview · 실제 주문 아님';});
      content.querySelectorAll('.u-kpi span').forEach(x=>{if(x.textContent.trim()==='MODEL PLAN')x.textContent='RESEARCH PREVIEW';});
      const uf=document.querySelector('#universeFilter option[value="ACTION"]');if(uf)uf.textContent='PREVIEW';
      content.querySelectorAll('.universe-title .pill').forEach(x=>{const sv=snapshotValidity(state().us||{});x.textContent=sv.valid?'SNAPSHOT VALID':'SNAPSHOT EXPIRED';x.className='pill '+(sv.valid?'ok':'warn');});
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
