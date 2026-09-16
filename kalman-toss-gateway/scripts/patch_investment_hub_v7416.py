from __future__ import annotations
import sys
from pathlib import Path

BASE="vNext.7.4.15"
TARGET="vNext.7.4.16"

def between(text,start,end,new,label):
    a=text.find(start)
    if a<0: raise SystemExit(f"[FAIL] {label}: start missing")
    b=text.find(end,a+len(start))
    if b<0: raise SystemExit(f"[FAIL] {label}: end missing")
    return text[:a]+new.rstrip()+"\n"+text[b:]

def once(text,old,new,label):
    n=text.count(old)
    if n!=1: raise SystemExit(f"[FAIL] {label}: expected 1 got {n}")
    return text.replace(old,new,1)

HEADER='''<header class="product-head">
      <div>
        <div class="brand-mark">KALMAN</div>
        <h1>Investment Intelligence</h1>
        <div class="muted">Portfolio · Model · Data Health</div>
      </div>
      <div class="header-status">
        <span id="headerDataState" class="pill">DATA —</span>
        <span class="pill warn">TRADE OFF</span>
      </div>
    </header>

    <section class="command-shell section">
      <div id="commandAccount" class="command-kpis"><div class="muted">계좌 요약을 불러오는 중...</div></div>
      <div class="command-grid">
        <article class="command-panel"><div class="panel-kicker">R5.1 · US MODEL</div><div id="commandModel" class="muted">모델 상태를 불러오는 중...</div></article>
        <article class="command-panel"><div class="panel-kicker">SYSTEM HEALTH</div><div id="commandHealth" class="muted">데이터 상태를 확인하는 중...</div></article>
      </div>
    </section>'''

HELPERS=r'''
function cmdMetric(label,value,sub,kind){
  return '<div class="command-metric '+(kind||'')+'"><span>'+esc(label)+'</span><b>'+value+'</b><small>'+(sub||'')+'</small></div>';
}
function renderCommandAccount(j,fx){
  var box=$('#commandAccount');if(!box)return;
  var h=unwrap(j&&j.holdings)||{};
  var buy=n(h&&h.totalPurchaseAmount&&h.totalPurchaseAmount.usd);
  var val=n(h&&h.marketValue&&(h.marketValue.amountAfterCost&&h.marketValue.amountAfterCost.usd||h.marketValue.amount&&h.marketValue.amount.usd));
  var pl=n(h&&h.profitLoss&&(h.profitLoss.amountAfterCost&&h.profitLoss.amountAfterCost.usd||h.profitLoss.amount&&h.profitLoss.amount.usd));
  var rate=(buy!=null&&buy!==0&&pl!=null)?pl/buy:null;
  var bp=pick(unwrap(j&&j.buying_power_krw),['cashBuyingPower','buyingPower','availableAmount','available','amount','value']);
  box.innerHTML=[
    cmdMetric('PORTFOLIO',accountUsd(val,2),accountKrw(val,fx),''),
    cmdMetric('P / L',accountUsd(pl,2),rate==null?'—':pct(rate,100),pl>0?'metric-good':pl<0?'metric-bad':''),
    cmdMetric('BUYING POWER',money(bp,'KRW'),'KRW available',''),
    cmdMetric('BROKER','TOSS','updated '+time(j&&j.generated_at),'')
  ].join('');
}
function stateLabel(stale){return '<span class="health-dot '+(stale?'warn-dot':'good-dot')+'"></span>'+(stale?'STALE':'FRESH');}
function renderCommandModel(j){
  var box=$('#commandModel');if(!box)return;
  var p=j&&j.payload||{},a=(p.assets||p.top3||[]).slice(0,6);
  var rows=a.map(function(x,i){return '<div class="command-rank"><span>'+(i+1)+'</span><b>'+esc(x.symbol||'—')+'</b><small>'+fmt((n(x.model_score)||0)*10000,2)+' bp</small></div>';}).join('');
  box.className='';
  box.innerHTML='<div class="command-model-head"><div><small>TOP SIGNAL</small><strong>'+esc(a[0]&&a[0].symbol||'—')+'</strong></div><div class="right">'+stateLabel(j&&j.effective_stale)+'<small>'+time(j&&j.data_as_of)+'</small></div></div><div class="command-ranks">'+rows+'</div>';
}
function healthRow(label,state,detail){return '<div class="health-row"><span>'+label+'</span><b>'+state+'</b><small>'+detail+'</small></div>';}
function renderCommandHealth(us,g,h){
  var box=$('#commandHealth');if(!box)return;
  var c=g&&g.payload&&g.payload.components||{},kr=c.KR||{},cr=c.CRYPTO||{},safe=h&&h.trade_enabled===false&&h.account_trade_execution===false;
  box.className='';
  box.innerHTML=[
    healthRow('US DATA',stateLabel(us&&us.effective_stale),time(us&&us.data_as_of)),
    healthRow('KR DATA',stateLabel(kr.stale),time(kr.data_as_of)),
    healthRow('CRYPTO',stateLabel(cr.stale),time(cr.data_as_of)),
    healthRow('EXECUTION','<span class="health-dot '+(safe?'good-dot':'warn-dot')+'"></span>'+(safe?'SAFE':'CHECK'),safe?'trade off':'gate changed')
  ].join('');
  var head=$('#headerDataState');if(head){var live=!(us&&us.effective_stale)&&!kr.stale&&!cr.stale;head.className='pill '+(live?'ok':'warn');head.textContent=live?'DATA LIVE':'DATA CHECK';}
}
async function loadCommandCenter(){
  try{
    var x=await Promise.all([getJSON('/api/dashboard?market=US'),getJSON('/api/dashboard?market=GLOBAL'),getJSON('/api/health')]);
    renderCommandModel(x[0]);renderCommandHealth(x[0],x[1],x[2]);
  }catch(e){}
}
function usLedgerTable(j){
  var l=j&&j.payload&&j.payload.source_payload&&j.payload.source_payload.r5_shadow_ledger||{},a=l.annual_2026||{},t=(a.trades&&a.trades.length?a.trades:l.trades)||[];
  if(!t.length)return '<div class="notice">표시할 R5.1 ledger가 없습니다.</div>';
  var rows=t.slice().sort(function(x,y){return Date.parse(y.entry_time)-Date.parse(x.entry_time);}).map(function(x){
    var recon=x.provenance==='R5_1_RECONSTRUCTED_2026',ret=n(x.return_pct),kind=recon?'RECON':'FORWARD';
    return '<tr data-ledger-kind="'+kind+'"><td>'+time(x.entry_time)+'</td><td><b>'+esc(x.symbol||'—')+'</b></td><td>'+(recon?badge('RECON','warn'):badge('FORWARD','ok'))+'</td><td>'+money(x.entry_price,'USD')+'</td><td>'+(x.exit_price==null?'—':money(x.exit_price,'USD'))+'</td><td class="'+(ret==null?'':ret>=0?'good':'bad')+'">'+(ret==null?'OPEN':pct(ret,100))+'</td><td>'+(x.exit_time?'CLOSED':'OPEN')+'</td></tr>';
  }).join('');
  return '<div class="section-title"><div><h3>2026 R5.1 Ledger</h3><span class="small">'+fmt(t.length,0)+' trades</span></div><div class="ledger-filters"><button class="ledger-filter active" data-ledger-filter="ALL">ALL</button><button class="ledger-filter" data-ledger-filter="RECON">RECON</button><button class="ledger-filter" data-ledger-filter="FORWARD">FORWARD</button></div></div><div class="table-scroll ledger-table-scroll"><table class="data-table"><thead><tr><th>Entry</th><th>Symbol</th><th>Type</th><th>Entry</th><th>Exit</th><th>Return</th><th>Status</th></tr></thead><tbody>'+rows+'</tbody></table></div>';
}
function usModelTable(j){
  var a=j&&j.payload&&(j.payload.assets||j.payload.top3)||[];
  var rows=a.map(function(x){return '<tr><td>'+fmt(x.rank,0)+'</td><td><b>'+esc(x.symbol||'—')+'</b></td><td>'+fmt((n(x.model_score)||0)*10000,2)+' bp</td><td>'+money(x.reference_price,'USD')+'</td><td>'+money(x.target_price_4h,'USD')+'</td><td>'+pct(x.position_weight_r4_vol_target,100)+'</td></tr>';}).join('');
  return '<div class="section-title"><div><h3>R5.1 Model Universe</h3><span class="small">'+fmt(a.length,0)+' symbols</span></div>'+badge(j.model_version||'R5.1')+'</div><div class="table-scroll model-table-scroll"><table class="data-table"><thead><tr><th>Rank</th><th>Symbol</th><th>Score</th><th>Reference</th><th>4h Target</th><th>Weight</th></tr></thead><tbody>'+rows+'</tbody></table></div>';
}
async function loadUsPrimaryChart(j){
  var box=$('#usPrimaryChart');if(!box)return;
  var p=j&&j.payload||{},first=(p.assets||p.top3||[])[0];
  var symbol=String(first&&first.symbol||'').toUpperCase();
  if(!symbol){box.innerHTML='<div class="notice">Top-1 symbol이 없습니다.</div>';return;}
  try{
    var hist=await getJSON('/api/history?mode=ytd-points&market=US&assets='+encodeURIComponent(symbol));
    var raw=(hist.items||[]).find(function(x){return String(x.symbol||'').toUpperCase()===symbol;});
    if(!raw){box.innerHTML='<div class="notice">Top-1 가격 이력이 없습니다.</div>';return;}
    var ledger=p.source_payload&&p.source_payload.r5_shadow_ledger||{},annual=ledger.annual_2026||{};
    var events=(annual.events||ledger.events||[])
      .filter(function(e){return String(e.symbol||'').toUpperCase()===symbol;})
      .map(function(e){return Object.assign({},e,{price:n(e.price)});})
      .filter(function(e){return e.price!=null;})
      .sort(function(a,b){return Date.parse(a.time)-Date.parse(b.time);});
    var item=Object.assign({},raw,{
      events:events,
      summary:Object.assign({},raw.summary||{},{rule:'R5.1 TOP-1'})
    });
    box.innerHTML=ytdPointChart(item,{name:symbol,actualModel:true,lifecycle:true,rule:'R5.1 TOP-1'});
  }catch(e){
    box.innerHTML='<div class="notice error">Top-1 차트를 불러오지 못했습니다.<div class="small">'+esc(e.message)+'</div></div>';
  }
}
function bindUsWorkspace(){
  var host=$('.us-workspace');if(!host)return;
  host.querySelectorAll('.market-subtab').forEach(function(btn){btn.addEventListener('click',function(){var v=btn.dataset.usView;host.querySelectorAll('.market-subtab').forEach(function(x){x.classList.toggle('active',x===btn)});host.querySelectorAll('.us-pane').forEach(function(x){x.classList.toggle('active',x.dataset.usPane===v)});});});
  host.querySelectorAll('.ledger-filter').forEach(function(btn){btn.addEventListener('click',function(){var f=btn.dataset.ledgerFilter;host.querySelectorAll('.ledger-filter').forEach(function(x){x.classList.toggle('active',x===btn)});host.querySelectorAll('tr[data-ledger-kind]').forEach(function(r){r.hidden=f!=='ALL'&&r.dataset.ledgerKind!==f;});});});
}
'''

US_VIEW=r'''function renderUS(j){
  var p=j.payload||{},s=p.summary||{},a=(p.assets||p.top3||[]),top6=a.slice(0,6);
  var ranks=top6.map(function(x,i){return '<div class="top us-rank-row"><div class="rank">'+(i+1)+'</div><div><div class="asset">'+esc(x.symbol)+'</div><div class="small">target '+money(x.target_price_4h,'USD')+' · weight '+pct(x.position_weight_r4_vol_target,100)+'</div></div><div class="right"><b>'+fmt((n(x.model_score)||0)*10000,2)+' bp</b><div class="small">'+money(x.reference_price,'USD')+'</div></div></div>';}).join('');
  var perf=top6.length?'<div class="performance-section"><div class="section-title"><h3>Performance</h3><span class="small">benchmark / actual model</span></div>'+performanceTabs('US')+'</div>':'<div class="notice">성과 데이터가 없습니다.</div>';
  return '<div class="us-workspace"><nav class="market-subnav"><button class="market-subtab active" data-us-view="overview">Overview</button><button class="market-subtab" data-us-view="performance">Performance</button><button class="market-subtab" data-us-view="ledger">Ledger</button><button class="market-subtab" data-us-view="model">Model</button></nav>'+
    '<section class="us-pane active" data-us-pane="overview"><div class="summary">'+staleBadge(j.effective_stale)+' '+badge(s.market_risk||'US')+' '+badge(s.primary_lineage||j.model_version||'MODEL')+' <span class="muted">'+time(j.data_as_of)+'</span></div><div class="us-overview-grid"><div class="card us-primary"><div class="section-title"><div><div class="eyebrow">PRIMARY WORKSPACE</div><h3>Top-1 Price + Model B/S</h3></div><span class="small">R5.1 ledger overlay</span></div><div id="usPrimaryChart"><div class="muted">Top-1 차트를 불러오는 중...</div></div></div><div class="card us-top6"><div class="section-title"><div><div class="eyebrow">LIVE RANKING</div><h3>R5.1 Top 6</h3></div></div>'+ranks+'</div></div></section>'+
    '<section class="us-pane" data-us-pane="performance">'+perf+'</section>'+
    '<section class="us-pane card" data-us-pane="ledger">'+usLedgerTable(j)+'</section>'+
    '<section class="us-pane card" data-us-pane="model">'+usModelTable(j)+'</section></div>';
}'''

CSS=r'''
/* vNext.7.4.16 command-center */
.wrap{display:flex;flex-direction:column}.product-head{order:0;display:flex;justify-content:space-between;align-items:flex-end;gap:18px}.brand-mark{font-size:11px;font-weight:950;letter-spacing:.22em;color:var(--accent)}.header-status{display:flex;gap:7px}.command-shell{order:1;background:linear-gradient(180deg,#111a30,#0d1527);border:1px solid #2a3857;border-radius:18px;padding:14px}.primary-tabs,.tabs{order:2}.wrap>main{order:3}.wrap>.account{order:4}.wrap>footer{order:5}.command-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.command-metric,.command-panel{background:#0b1425;border:1px solid #263654;border-radius:12px;padding:11px}.command-metric{display:flex;flex-direction:column}.command-metric span,.panel-kicker{font-size:10px;color:#8293b2;font-weight:850;letter-spacing:.06em}.command-metric b{font-size:20px}.command-metric small{font-size:10px;color:#7787a4}.metric-good b{color:var(--good)}.metric-bad b{color:var(--bad)}.command-grid{display:grid;grid-template-columns:1.4fr .8fr;gap:9px;margin-top:9px}.command-model-head{display:flex;justify-content:space-between;margin:8px 0}.command-model-head>div{display:flex;flex-direction:column}.command-model-head strong{font-size:25px}.command-ranks{display:grid;grid-template-columns:repeat(3,1fr);gap:5px}.command-rank{display:grid;grid-template-columns:18px 1fr auto;gap:5px;padding:6px;border-radius:8px;background:#0e182b}.command-rank small{font-size:9px;color:#91a3c2}.health-row{display:grid;grid-template-columns:70px 70px 1fr;gap:7px;padding:7px 0;border-bottom:1px solid #21304a;font-size:10px}.health-row small{text-align:right;color:#71819e}.health-dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px}.good-dot{background:var(--good)}.warn-dot{background:var(--warn)}.primary-tabs{position:sticky;top:0;z-index:20;background:rgba(11,16,32,.93);backdrop-filter:blur(10px);padding:9px 0}.market-subnav{display:flex;gap:5px;padding:4px;background:#0b1220;border:1px solid var(--line);border-radius:11px;margin-bottom:12px;position:sticky;top:58px;z-index:15;width:max-content}.market-subtab,.ledger-filter{border:0;background:transparent;color:#94a3b8;padding:8px 11px;border-radius:8px;font-weight:800;cursor:pointer}.market-subtab.active,.ledger-filter.active{background:#e2e8f0;color:#0f172a}.us-pane{display:none}.us-pane.active{display:block}.us-overview-grid{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(290px,.7fr);gap:12px}.us-primary .mini-chart{border:0;background:transparent;padding:0}.us-primary .ytd-spark{height:300px}.us-rank-row{grid-template-columns:28px 1fr auto}.ledger-filters{display:flex;gap:4px}.table-scroll{overflow:auto;max-height:640px;border:1px solid #25304a;border-radius:10px}.data-table{width:100%;min-width:700px;border-collapse:collapse;font-size:11px}.data-table th{position:sticky;top:0;background:#111a2d;color:#8495b4;text-align:left;padding:9px;border-bottom:1px solid #2b3852}.data-table td{padding:9px;border-bottom:1px solid #1e2b42;white-space:nowrap}.account{max-height:560px;overflow:auto}
@media(max-width:900px){.command-grid,.us-overview-grid{grid-template-columns:1fr}.command-ranks{grid-template-columns:repeat(2,1fr)}}@media(max-width:760px){.command-kpis{grid-template-columns:1fr 1fr}.command-ranks{grid-template-columns:1fr 1fr}.market-subnav{width:100%;overflow:auto}.market-subtab{flex:1}.us-primary .ytd-spark{height:230px}}@media(max-width:430px){.command-ranks{grid-template-columns:1fr}.command-metric b{font-size:17px}}
'''

def main():
    if len(sys.argv)!=2: raise SystemExit("usage: patch_investment_hub_v7416.py <source-root>")
    root=Path(sys.argv[1]); ap=root/"app.js"; cp=root/"style.css"; ip=root/"index.html"; hp=root/"api/health.js"
    for p in (ap,cp,ip,hp):
        if not p.exists(): raise SystemExit(f"[FAIL] missing {p}")
    app=ap.read_text();css=cp.read_text();idx=ip.read_text();health=hp.read_text()
    if BASE not in idx: raise SystemExit("[FAIL] v7.4.15 base missing")
    start='<header class="head">'
    end='    <section class="card account section">'
    a=idx.find(start);b=idx.find(end,a)
    if a<0 or b<0: raise SystemExit("[FAIL] header anchors")
    idx=idx[:a]+HEADER+"\n\n    "+idx[b:]
    idx=idx.replace('<nav class="tabs" aria-label="시장 선택">','<nav class="tabs primary-tabs" aria-label="시장 선택">',1)
    idx=idx.replace('vNext.7.4.15 · Account + Forward SHADOW Read Only','vNext.7.4.16 · Command Center + Model Workspace',1)
    app=once(app,'async function loadAccount(){',HELPERS+'\nasync function loadAccount(){','helpers')
    app=once(app,"    const summary=[\n      card('총 매입금액',accountUsd(totalPurchaseUsd),accountKrw(totalPurchaseUsd,fx)),","    renderCommandAccount(j,fx);\n\n    const summary=[\n      card('총 매입금액',accountUsd(totalPurchaseUsd),accountKrw(totalPurchaseUsd,fx)),",'account command')
    app=between(app,'function renderUS(j){','function renderKR(',US_VIEW,'renderUS')
    app=once(app,"if(m==='US'){const a=(j.payload?.top3||[]).slice(0,3);bindPerformanceTabs('US',a,j);loadYtdStockCharts('US',a)}","if(m==='US'){const a=(j.payload?.assets||j.payload?.top3||[]).slice(0,6);bindUsWorkspace();bindPerformanceTabs('US',a,j);loadYtdStockCharts('US',a.slice(0,3));loadUsPrimaryChart(j);renderCommandModel(j)}",'US binding')
    app=once(app,"loadAccount();loadMarket('GLOBAL');","loadAccount();loadCommandCenter();loadMarket('GLOBAL');",'boot')
    css=css.rstrip()+"\n\n"+CSS.strip()+"\n";health=health.replace(BASE,TARGET);idx=idx.replace(BASE,TARGET)
    if len(list((root/"api").rglob("*.js")))!=12: raise SystemExit("[FAIL] API count")
    for m in ("commandAccount","commandModel","commandHealth","R5.1 Top 6","usLedgerTable","usModelTable","loadUsPrimaryChart","bindUsWorkspace"):
        if m not in app and m not in idx: raise SystemExit(f"[FAIL] marker {m}")
    ap.write_text(app);cp.write_text(css);ip.write_text(idx);hp.write_text(health)
    print("[PASS] vNext.7.4.16 command center")
    print("[PASS] US primary chart + Top-6")
    print("[PASS] US Overview / Performance / Ledger / Model")
    print("[PASS] API function count = 12")
    return 0
if __name__=="__main__": raise SystemExit(main())
