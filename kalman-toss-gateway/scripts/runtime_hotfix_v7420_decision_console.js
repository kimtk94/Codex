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
      const k=next.querySelector('.panel-kicker');if(k)k.textContent='EXECUTION PLAN';
      grid.insertBefore(next,grid.firstChild);
    }
    if(model){const k=model.querySelector('.panel-kicker');if(k)k.textContent='R5.1 · MODEL SIGNAL';}

    if(!document.querySelector('#commandBenchmark')){
      const a=document.createElement('article');
      a.className='command-panel';
      a.innerHTML='<div class="panel-kicker">TOP1 ↔ TOP6 · FORWARD CHECK</div><div id="commandBenchmark"></div>';
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
      sec.innerHTML='<div class="section-head"><div><div class="eyebrow">BROKER EXECUTION LEDGER</div><h2>실제 체결 기록</h2><div class="muted">Shadow 성과와 분리 · Toss 체결이 발생한 경우에만 기록</div></div><span class="pill">NO EXECUTION</span></div><div class="kalman-offline"><div><b>실제 Toss 체결 0건</b><span>서버 미가동 상태이므로 정상입니다. 실매매가 시작되면 v7.4.22 execution ledger와 연결됩니다.</span></div></div>';
      tabs.parentNode.insertBefore(sec,tabs);
    }
  }

  function renderBenchmark(){
    const box=document.querySelector('#commandBenchmark');if(!box)return;
    const d=BENCH.top6.compounded-BENCH.top1.compounded;
    box.innerHTML=
      '<div class="kalman-bench-grid">'+
        '<div class="kalman-bench-col"><span>TOP-1</span><b>'+P(BENCH.top1.compounded)+'</b><small>avg '+P(BENCH.top1.avg)+' · σ '+P(BENCH.top1.std)+' · n='+BENCH.snapshots+'</small></div>'+
        '<div class="kalman-bench-col"><span>TOP-6 EQUAL</span><b>'+P(BENCH.top6.compounded)+'</b><small>avg '+P(BENCH.top6.avg)+' · σ '+P(BENCH.top6.std)+' · n='+BENCH.snapshots+'</small></div>'+
      '</div>'+
      '<div class="kalman-bench-foot"><span>same 4-bucket · 10bp · through '+T(BENCH.asOf)+'</span><b>Δ cumulative '+P(d)+'</b></div>'+
      '<div class="small">Forward snapshot 비교이며 자동 전략 선택 기준으로 사용하지 않습니다.</div>';
  }

  function renderPlan(){
    const box=document.querySelector('#commandNextActions');if(!box)return;
    const sig=latestSignal(),online=brokerOnline();
    let fresh=false;
    if(sig.asOf){const age=(Date.now()-Date.parse(sig.asOf))/60000;fresh=Number.isFinite(age)&&age>=0&&age<=90;}
    box.className='';
    box.innerHTML=
      '<div class="kalman-execution-hero"><div><small>'+(online?'BROKER CONNECTED':'SERVER OFFLINE')+'</small><strong>'+E(sig.symbol)+'</strong><span>'+M(5000)+' / entry</span></div>'+pill(online?'GUARDED':'PLANNED',online?'ok':'warn')+'</div>'+
      '<div class="kalman-rule-grid">'+
        '<div><span>SIGNAL</span><b>R5.1 SHADOW</b><small>'+T(sig.asOf)+'</small></div>'+
        '<div><span>ENTRY</span><b>'+M(5000)+'</b><small>latest eligible signal</small></div>'+
        '<div><span>EXIT</span><b>-3% / +20%</b><small>stop loss · take profit</small></div>'+
        '<div><span>ROTATE</span><b>ON</b><small>model rotation · 4 buckets max</small></div>'+
      '</div>'+
      '<div class="kalman-gates">'+pill(fresh?'FRESH':'STALE',fresh?'ok':'warn')+pill(sig.canary?'CANARY SIGNAL':'WAIT SIGNAL',sig.canary?'ok':'warn')+pill(online?'BROKER ONLINE':'BROKER OFFLINE',online?'ok':'warn')+pill('NO BROKER FILL','')+'</div>'+
      '<div class="next-actions-note">웹은 주문하지 않습니다. 서버가 켜지면 계좌·bot gate·실제 체결 정보만 추가됩니다.</div>';
  }

  function renderServerState(){
    const online=brokerOnline();
    const h=document.querySelector('#headerServerState');
    if(h){h.className='pill '+(online?'ok':'warn');h.textContent=online?'SERVER ONLINE':'SERVER OFFLINE';}

    if(!online){
      const account=document.querySelector('#account');
      if(account){
        const txt=(account.textContent||'').toLowerCase();
        if(txt.includes('불러오지 못')||txt.includes('실패')||txt.includes('gateway')){
          account.innerHTML='<div class="kalman-offline"><div><b>SERVER OFFLINE</b><span>Toss 계좌 데이터는 서버가 켜지면 자동 복구됩니다. 모델·신호 화면은 계속 사용할 수 있습니다.</span></div>'+pill('NO BROKER DATA','warn')+'</div>';
        }
      }
    }
  }

  let scheduled=false;
  function apply(){
    scheduled=false;
    addStyle();ensureShell();renderBenchmark();renderPlan();renderServerState();
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
