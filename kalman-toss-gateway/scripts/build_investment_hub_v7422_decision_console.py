from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE_MANIFEST = ROOT / "kalman-hub-recovery/v7.4.21/source_manifest.ndjson"
OUT_DIR = ROOT / "kalman-hub-recovery/v7.4.22"
TARGET = "vNext.7.4.22"


def decode_manifest(manifest: Path, out: Path) -> None:
    rows = [json.loads(x) for x in manifest.read_text(encoding="utf-8").splitlines() if x.strip()]
    if len(rows) != 30:
        raise SystemExit(f"expected 30 files, got {len(rows)}")
    for row in rows:
        rel = Path(row["file"])
        if rel.is_absolute() or ".." in rel.parts:
            raise SystemExit(f"unsafe path: {rel}")
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(base64.b64decode(row["data_b64"]))


def patch_api(src: Path) -> None:
    p = src / "api/assets.js"
    text = p.read_text(encoding="utf-8")
    anchor = "async function dashboard(req,res){"
    if anchor not in text:
        raise SystemExit("dashboard anchor missing")
    control = r"""async function control(req,res){
  res.setHeader('Cache-Control','no-store');
  if(!process.env.DATABASE_URL_READER)return res.status(503).json({error:'DB_NOT_CONFIGURED'});
  try{
    const {neon}=await import('@neondatabase/serverless');
    const sql=neon(process.env.DATABASE_URL_READER);
    const [bench,latestSignal,canaryCandidate,executableCandidate,exec,managed]=await Promise.all([
      sql`SELECT benchmark_name,COUNT(*)::int AS snapshots,MIN(as_of) AS first_as_of,MAX(as_of) AS last_as_of,
                 AVG(net_return)::float8 AS avg_net,STDDEV_SAMP(net_return)::float8 AS std_net,
                 (EXP(SUM(LN(1+net_return)))-1)::float8 AS compounded
          FROM strategy_benchmark_ledger
          WHERE market='US' AND strategy_version='R5.1_BASE_HGB'
          GROUP BY benchmark_name ORDER BY benchmark_name`,
      sql`SELECT symbol,as_of,strategy_version,signal,entry_allowed,risk_gate,position_state,payload
          FROM strategy_signal
          WHERE market='US' AND strategy_version='R5.1_BASE_HGB'
          ORDER BY as_of DESC LIMIT 1`,
      sql`SELECT s.symbol,s.as_of,s.strategy_version,s.signal,s.entry_allowed,s.risk_gate,s.position_state,s.payload
          FROM strategy_signal s
          JOIN dashboard_snapshot d ON d.run_id=s.run_id AND d.market=s.market
          WHERE s.market='US'
            AND s.strategy_version='R5.1_BASE_HGB'
            AND s.signal='SHADOW'
            AND upper(COALESCE(s.position_state,''))='FLAT'
            AND lower(COALESCE(s.payload->>'allow_trade_shadow','false'))='true'
            AND lower(COALESCE(s.payload->>'shadow_entry_this_signal','false'))='true'
            AND d.status='READY'
          ORDER BY s.as_of DESC LIMIT 1`,
      sql`SELECT s.symbol,s.as_of,s.strategy_version,s.signal,s.entry_allowed,s.risk_gate,s.position_state,s.payload
          FROM strategy_signal s
          JOIN dashboard_snapshot d ON d.run_id=s.run_id AND d.market=s.market
          WHERE s.market='US'
            AND s.strategy_version='R5.1_BASE_HGB'
            AND s.as_of >= now()-interval '90 minutes'
            AND s.signal='SHADOW'
            AND upper(COALESCE(s.position_state,''))='FLAT'
            AND lower(COALESCE(s.payload->>'allow_trade_shadow','false'))='true'
            AND lower(COALESCE(s.payload->>'shadow_entry_this_signal','false'))='true'
            AND d.status='READY'
            AND d.stale_after > now()
          ORDER BY s.as_of DESC LIMIT 1`,
      sql`SELECT position_id,symbol,strategy_version,state,entry_signal_as_of,entry_order_id,
                 entry_filled_quantity,entry_average_price,exit_order_id,exit_filled_quantity,
                 exit_average_price,exit_reason,realized_return_pct,updated_at
          FROM v_live_trade_ledger ORDER BY updated_at DESC LIMIT 20`,
      sql`SELECT COUNT(*)::int AS total,
                 COUNT(*) FILTER (WHERE state NOT IN ('CLOSED','CLOSED_MANUAL','ENTRY_ABORTED'))::int AS active
          FROM managed_position_mirror`
    ]);
    const byName=Object.fromEntries((bench||[]).map(x=>[x.benchmark_name,x]));
    return res.status(200).json({
      schema_version:'kalman-web-control-v1',
      status:'READY',
      strategy_version:'R5.1_BASE_HGB',
      target_order_krw:5000,
      daily_buy_cap_krw:30000,
      execution_contract:{
        signal_policy:'SHADOW_CANARY',
        max_signal_age_minutes:90,
        requires:['SHADOW','FLAT','allow_trade_shadow=true','shadow_entry_this_signal=true','dashboard READY + unexpired','broker/account gates on server']
      },
      exit_rules:{stop_loss_pct:-0.03,take_profit_pct:0.20,model_rotation:true,max_hold_buckets:4},
      latest_model_signal:(latestSignal&&latestSignal[0])||null,
      latest_canary_candidate:(canaryCandidate&&canaryCandidate[0])||null,
      executable_model_candidate:(executableCandidate&&executableCandidate[0])||null,
      entry_signal_fresh_now:Boolean(executableCandidate&&executableCandidate.length),
      model_candidate_eligible_now:Boolean(executableCandidate&&executableCandidate.length),
      benchmark_contract:{exit_rule:'MAX_HOLD_4_BUCKETS_ONLY',cost_bps_round_trip:10,overlapping_windows:true,includes_live_exit_overrides:false},
      benchmarks:{top1:byName.TOP1_4B_10BP||null,top6:byName.TOP6_EQUAL_4B_10BP||null},
      execution_ledger:exec||[],
      managed_summary:(managed&&managed[0])||{total:0,active:0},
      broker_execution_present:Boolean(exec&&exec.length),
      generated_at:new Date().toISOString()
    });
  }catch(e){
    return res.status(500).json({error:'CONTROL_READ_FAILED',detail:String(e?.message||e)});
  }
}

"""
    text = text.replace(anchor, control + anchor, 1)
    old = "if(view==='account')return account(req,res);\n  if(view==='dashboard')return dashboard(req,res);"
    new = "if(view==='account')return account(req,res);\n  if(view==='control')return control(req,res);\n  if(view==='dashboard')return dashboard(req,res);"
    if old not in text:
        raise SystemExit("dispatch anchor missing")
    text = text.replace(old, new, 1)

    old2 = "if(!ok)return res.status(502).json({error:'ACCOUNT_GATEWAY_UNAVAILABLE',parts:Object.fromEntries(Object.entries(parts).map(([k,v])=>[k,{ok:v.ok,status:v.status,error:v.error}])),trading_status:tradingStatus.data,gateway_health:gatewayHealth.data,trade_execution:false,server_trade_execution:false,generated_at:new Date().toISOString()});"
    new2 = "if(!ok)return res.status(200).json({status:'OFFLINE',error:'ACCOUNT_GATEWAY_UNAVAILABLE',parts:Object.fromEntries(Object.entries(parts).map(([k,v])=>[k,{ok:v.ok,status:v.status,error:v.error}])),accounts:null,holdings:null,buying_power_usd:null,buying_power_krw:null,trading_status:tradingStatus.data,gateway_health:gatewayHealth.data,trading_status_available:Boolean(tradingStatus.ok),trade_execution:false,server_trade_execution:false,generated_at:new Date().toISOString()});"
    if old2 not in text:
        raise SystemExit("account offline anchor missing")
    text = text.replace(old2, new2, 1)
    p.write_text(text, encoding="utf-8")


def patch_index(src: Path) -> None:
    p = src / "index.html"
    text = p.read_text(encoding="utf-8")
    text = text.replace(
        '<span id="headerDataState" class="pill">DATA —</span>\n        <span class="pill warn">WEB READ ONLY</span>',
        '<span id="headerDataState" class="pill">DATA —</span>\n        <span id="headerServerState" class="pill warn">SERVER —</span>\n        <span class="pill">READ ONLY</span>'
    )
    old_grid = '''      <div class="command-grid">
        <article class="command-panel"><div class="panel-kicker">R5.1 · US MODEL</div><div id="commandModel" class="muted">모델 상태를 불러오는 중...</div></article>
        <article class="command-panel"><div class="panel-kicker">SYSTEM HEALTH</div><div id="commandHealth" class="muted">데이터 상태를 확인하는 중...</div></article>
        <article class="command-panel next-actions-panel"><div class="panel-kicker">AUTO TRADE · NEXT ACTION</div><div id="commandNextActions" class="muted">실제 서버 자동매매 상태를 계산하는 중...</div></article>
      </div>'''
    new_grid = '''      <div class="command-grid control-grid">
        <article class="command-panel execution-panel">
          <div class="panel-kicker">AUTO-TRADE · SERVER CONTRACT</div>
          <div id="commandNextActions" class="muted">R5.1 실행 계획을 계산하는 중...</div>
        </article>
        <article class="command-panel">
          <div class="panel-kicker">R5.1 · MODEL RANKING</div>
          <div id="commandModel" class="muted">모델 상태를 불러오는 중...</div>
        </article>
        <article class="command-panel">
          <div class="panel-kicker">RESEARCH BENCHMARK · TOP1 vs TOP6</div>
          <div id="commandBenchmark" class="muted">동일 4-bucket benchmark를 불러오는 중...</div>
        </article>
        <article class="command-panel">
          <div class="panel-kicker">SYSTEM / BROKER</div>
          <div id="commandHealth" class="muted">데이터와 서버 상태를 확인하는 중...</div>
        </article>
      </div>'''
    if old_grid not in text:
        raise SystemExit("command grid anchor missing")
    text = text.replace(old_grid, new_grid, 1)

    text = text.replace(
        '<div class="muted">Toss Securities · 계좌 + 서버 bot 상태</div>',
        '<div id="accountSubtitle" class="muted">Toss Securities · 서버 연결 시 실계좌 표시</div>'
    )
    text = text.replace(
        '<div id="account"><div class="muted">계좌를 불러오는 중...</div></div>',
        '<div id="account"><div class="muted">계좌 연결 상태를 확인하는 중...</div></div>'
    )

    nav = '    <nav class="tabs primary-tabs" aria-label="시장 선택">'
    ledger = '''    <section class="card section execution-ledger-card">
      <div class="section-head">
        <div>
          <div class="eyebrow">LIVE EXECUTION MIRROR · NEON</div>
          <h2>실매매 체결 미러</h2>
          <div class="muted">Shadow/model 평가와 분리 · 서버가 미러링한 실제 bot 주문/체결만 표시</div>
        </div>
        <span id="executionLedgerState" class="pill">MIRROR EMPTY</span>
      </div>
      <div id="executionLedger"><div class="notice">Neon execution mirror가 비어 있습니다. Broker 전체 거래내역이 0건이라는 의미는 아닙니다.</div></div>
    </section>

'''
    if nav not in text:
        raise SystemExit("nav anchor missing")
    text = text.replace(nav, ledger + nav, 1)

    text = text.replace("AUTO-TRADE · SERVER CONTRACT", "자동매매 · 실행 조건")
    text = text.replace("R5.1 · MODEL RANKING", "R5.1 · 모델 순위")
    text = text.replace("RESEARCH BENCHMARK · TOP1 vs TOP6", "연구 벤치마크 · TOP-1 vs TOP-6")
    text = text.replace("SYSTEM / BROKER", "시스템 · Toss")
    text = text.replace("LIVE EXECUTION MIRROR · NEON", "실매매 기록 · NEON MIRROR")
    text = text.replace("<h2>실매매 체결 미러</h2>", "<h2>실매매 기록</h2>")
    text = text.replace(
        "Shadow/model 평가와 분리 · 서버가 미러링한 실제 bot 주문/체결만 표시",
        "실제 자동매매 주문·체결만 표시 · Shadow/연구 결과와 분리"
    )
    text = text.replace('id="executionLedgerState" class="pill">MIRROR EMPTY<', 'id="executionLedgerState" class="pill">기록 없음<')
    text = text.replace(
        "Neon execution mirror가 비어 있습니다. Broker 전체 거래내역이 0건이라는 의미는 아닙니다.",
        "Neon 실매매 미러에 아직 기록이 없습니다. Toss 전체 거래내역이 0건이라는 뜻은 아닙니다."
    )
    text = text.replace(">READ ONLY<", ">조회 전용<")
    text = text.replace("vNext.7.4.21 · Auto-Trade Console + Universe", TARGET + " · Decision Console")
    text = text.replace("vNext.7.4.21", TARGET)
    p.write_text(text, encoding="utf-8")


def patch_app(src: Path) -> None:
    p = src / "app.js"
    text = p.read_text(encoding="utf-8")
    text = text.replace(
        "var kalmanCommandState={account:null,us:null,fx:null,health:null,global:null};",
        "var kalmanCommandState={account:null,us:null,kr:null,crypto:null,fx:null,health:null,global:null,control:null};"
    )

    start = text.find("function renderNextActions(){")
    end = text.find("\nfunction cmdMetric(", start)
    if start < 0 or end < 0:
        raise SystemExit("next actions anchors missing")
    next_fn = r"""function renderNextActions(){
  var box=$('#commandNextActions');if(!box)return;
  var us=kalmanCommandState.us,ctl=kalmanCommandState.control||{},account=kalmanCommandState.account;
  var sig=ctl.latest_canary_candidate||ctl.latest_model_signal||{};
  var sel=currentUsSelector(us||{});
  var assets=(us&&us.payload&&(us.payload.assets||us.payload.top3))||[];
  var symbol=String(sig.symbol||sel.selected_symbol||(assets[0]&&assets[0].symbol)||'—').toUpperCase();
  var brokerOnline=account&&account.status!=='OFFLINE';
  var bot=botState(account);
  var mirrorHasRows=ctl.broker_execution_present===true;
  var orderKrw=n(ctl.target_order_krw)||LIVE_CANARY_TARGET_KRW;
  var rules=ctl.exit_rules||{stop_loss_pct:-.03,take_profit_pct:.20,model_rotation:true,max_hold_buckets:4};
  var modelEligible=(ctl.entry_signal_fresh_now===true)||(ctl.model_candidate_eligible_now===true);
  var contract=ctl.execution_contract||{};
  var botLive=Boolean(brokerOnline&&bot&&bot.autoTradeEnabled===true&&bot.executionMode==='LIVE'&&bot.liveGateOpen===true);

  var status='NOT EXECUTABLE',kind='warn',headline='TRADING LINK OFFLINE';
  if(brokerOnline&&!modelEligible)headline='ENTRY SIGNAL EXPIRED';
  if(brokerOnline&&modelEligible&&!botLive){status='GUARDED';headline='SERVER GATES NOT LIVE';}
  if(botLive&&modelEligible){status='LIVE READY';kind='ok';headline='SHADOW_CANARY';}

  box.className='';
  box.innerHTML=
    '<div class="execution-hero"><div><small>'+headline+'</small><strong>'+esc(symbol)+'</strong><span>last canary candidate · '+time(sig.as_of)+'</span></div><span class="pill '+kind+'">'+status+'</span></div>'+
    '<div class="execution-rule-grid">'+
      '<div><span>LIVE POLICY</span><b>'+esc(contract.signal_policy||'SHADOW_CANARY')+'</b><small>SHADOW signal is expected</small></div>'+
      '<div><span>TARGET SIZE</span><b>'+money(orderKrw,'KRW')+'</b><small>per new entry</small></div>'+
      '<div><span>LIVE EXITS</span><b>-3% / +20%</b><small>stop loss · take profit</small></div>'+
      '<div><span>EARLY / MAX EXIT</span><b>'+(rules.model_rotation?'ROTATE ON':'ROTATE OFF')+'</b><small>'+fmt(rules.max_hold_buckets,0)+' canonical buckets max</small></div>'+
    '</div>'+
    '<div class="execution-gates">'+
      badge(modelEligible?'ENTRY SIGNAL <90M':'ENTRY SIGNAL EXPIRED',modelEligible?'ok':'warn')+
      badge(brokerOnline?'BROKER LINK ONLINE':'BROKER LINK OFFLINE',brokerOnline?'ok':'warn')+
      badge(botLive?'SERVER LIVE GATES OPEN':'SERVER GATES NOT CONFIRMED',botLive?'ok':'warn')+
      badge(mirrorHasRows?'EXECUTION MIRROR HAS ROWS':'EXECUTION MIRROR EMPTY',mirrorHasRows?'ok':'')+
    '</div>'+
    '<div class="next-actions-note"><b>구분:</b> Top-6는 research benchmark/portfolio preview이며 실제 자동매매 selector가 아닙니다. 실제 신규 진입 후보는 SHADOW_CANARY 계약을 통과한 단일 R5.1 signal입니다. 웹은 주문을 제출하지 않습니다.</div>';
}
"""
    text = text[:start] + next_fn + text[end:]

    start = text.find("function renderCommandAccount(j,fx){")
    end = text.find("\nfunction stateLabel(", start)
    if start < 0 or end < 0:
        raise SystemExit("command account anchors missing")
    acc_fn = r"""function renderCommandAccount(j,fx){
  kalmanCommandState.account=j;kalmanCommandState.fx=fx;
  var box=$('#commandAccount');if(!box)return;
  var offline=!j||j.status==='OFFLINE';
  var head=$('#headerServerState');
  if(head){head.className='pill '+(offline?'warn':'ok');head.textContent=offline?'TRADING LINK OFFLINE':'TRADING LINK ONLINE';}
  var subtitle=$('#accountSubtitle');
  if(subtitle)subtitle.textContent=offline?'Toss Securities · trading link offline / broker data 없음':'Toss Securities · 계좌 연결됨';

  if(offline){
    box.innerHTML=[
      cmdMetric('PORTFOLIO','—','server offline',''),
      cmdMetric('P / L','—','server offline',''),
      cmdMetric('BUYING POWER','—','server offline',''),
      cmdMetric('BROKER','OFFLINE','Neon model data continues','')
    ].join('');
    renderNextActions();
    return;
  }

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
    cmdMetric('BROKER',(j&&j.trading_status&&j.trading_status.executionMode)||'CONNECTED',(j&&j.trading_status?((j.trading_status.liveGateOpen?'GATE OPEN':'GATE CLOSED')+' · '+(j.trading_status.strategyVersion||'—')):'Toss connected'),'')
  ].join('');
  renderNextActions();
  if(kalmanCommandState.us&&kalmanCommandState.kr&&kalmanCommandState.crypto&&kalmanCommandState.health){renderCommandHealth(kalmanCommandState.us,kalmanCommandState.kr,kalmanCommandState.crypto,kalmanCommandState.health);}
}
"""
    text = text[:start] + acc_fn + text[end:]

    anchor = "async function loadCommandCenter(){"
    if anchor not in text:
        raise SystemExit("loadCommandCenter anchor missing")
    renderers = r"""function benchmarkMetric(label,row){
  if(!row)return '<div class="benchmark-col"><span>'+esc(label)+'</span><b>—</b><small>no completed 4-bucket snapshot</small></div>';
  return '<div class="benchmark-col"><span>'+esc(label)+'</span><b>avg '+pct(row.avg_net,100)+'</b><small>σ '+pct(row.std_net,100)+' · n='+fmt(row.snapshots,0)+' · through '+time(row.last_as_of)+'</small></div>';
}
function renderBenchmark(ctl){
  kalmanCommandState.control=ctl;
  var box=$('#commandBenchmark');if(!box)return;
  var b=ctl&&ctl.benchmarks||{},a=b.top1,z=b.top6;
  var delta=(a&&z)?n(z.avg_net)-n(a.avg_net):null;
  box.className='';
  box.innerHTML=
    '<div class="benchmark-grid">'+benchmarkMetric('TOP-1 · 4B ONLY',a)+benchmarkMetric('TOP-6 EQUAL · 4B ONLY',z)+'</div>'+
    '<div class="benchmark-foot"><span>10bp round-trip approximation · overlapping 4h windows</span><b>Δ avg '+(delta==null?'—':pct(delta,100))+'</b></div>'+
    '<div class="small"><b>Research benchmark only:</b> -3% stop, +20% take-profit, model rotation을 포함하지 않습니다. 따라서 live auto-trade P/L과 직접 비교하면 안 됩니다. sequence compounded 값은 겹치는 window 때문에 포트폴리오 누적수익으로 표시하지 않습니다.</div>';
  renderExecutionLedger(ctl);
  renderNextActions();
}
function renderExecutionLedger(ctl){
  var box=$('#executionLedger'),state=$('#executionLedgerState');if(!box)return;
  var rows=(ctl&&ctl.execution_ledger)||[];
  if(!rows.length){
    if(state){state.className='pill';state.textContent='MIRROR EMPTY';}
    box.innerHTML='<div class="execution-empty"><div><b>Neon execution mirror 0 rows</b><span>현재 bot 주문/체결이 Neon에 미러링되지 않았다는 뜻입니다. Toss 계정 전체 거래내역이 0건이라는 뜻은 아닙니다.</span></div></div>';
    return;
  }
  if(state){state.className='pill ok';state.textContent=rows.length+' MIRRORED';}
  box.innerHTML='<div class="table-scroll"><table class="data-table"><thead><tr><th>Signal</th><th>Symbol</th><th>State</th><th>Entry Avg</th><th>Exit Avg</th><th>Realized Return</th><th>Exit reason</th></tr></thead><tbody>'+
    rows.map(function(x){var r=n(x.realized_return_pct);return '<tr><td>'+time(x.entry_signal_as_of)+'</td><td><b>'+esc(x.symbol||'—')+'</b></td><td>'+esc(x.state||'—')+'</td><td>'+money(x.entry_average_price,'USD')+'</td><td>'+money(x.exit_average_price,'USD')+'</td><td class="'+(r==null?'':r>=0?'good':'bad')+'">'+(r==null?'—':pct(r,100))+'</td><td>'+esc(x.exit_reason||'—')+'</td></tr>';}).join('')+
    '</tbody></table></div>';
}
"""
    text = text.replace(anchor, renderers + anchor, 1)

    start = text.find("async function loadCommandCenter(){")
    end = text.find("\nfunction usLedgerTable(", start)
    if start < 0 or end < 0:
        raise SystemExit("loadCommandCenter range missing")
    load = r"""async function loadCommandCenter(){
  try{
    var x=await Promise.all([
      getJSON('/api/dashboard?market=US'),
      getJSON('/api/dashboard?market=KR'),
      getJSON('/api/dashboard?market=CRYPTO'),
      getJSON('/api/dashboard?market=GLOBAL'),
      getJSON('/api/health'),
      getJSON('/api/assets?view=control')
    ]);
    kalmanCommandState.global=x[3];
    renderCommandModel(x[0]);
    renderCommandHealth(x[0],x[1],x[2],x[4]);
    renderBenchmark(x[5]);
  }catch(e){
    var b=$('#commandBenchmark');if(b)b.innerHTML='<div class="notice error">Decision-console data를 읽지 못했습니다.</div>';
  }
}
"""
    text = text[:start] + load + text[end:]

    account_anchor = "    const [j,fx]=await Promise.all([getJSON('/api/account'),loadAccountFx()]);\n"
    account_insert = r"""    const [j,fx]=await Promise.all([getJSON('/api/account'),loadAccountFx()]);
    if(j&&j.status==='OFFLINE'){
      renderCommandAccount(j,null);
      box.innerHTML='<div class="account-offline"><div><b>TRADING LINK OFFLINE</b><span>Toss 계좌/주문 데이터 링크가 오프라인입니다. 모델·benchmark·signal은 Neon에서 계속 표시됩니다.</span></div>'+badge('NO BROKER DATA','warn')+'</div>';
      return;
    }
"""
    if account_anchor not in text:
        raise SystemExit("loadAccount offline anchor missing")
    text = text.replace(account_anchor, account_insert, 1)

    # Snapshot validity and live-entry freshness are different contracts.
    text = text.replace(
        "function staleBadge(x){return x?badge('STALE','warn'):badge('LIVE','ok')}",
        "function staleBadge(x){return x?badge('SNAPSHOT EXPIRED','warn'):badge('SNAPSHOT VALID','ok')}"
    )
    old_fresh = """function executionFreshness(us){
  var ts=Date.parse(us&&us.data_as_of||'');
  var age=Number.isFinite(ts)?Math.max(0,(Date.now()-ts)/60000):Infinity;
  return {fresh:Number.isFinite(age)&&age<=EXECUTION_FRESH_MINUTES,ageMinutes:age};
}"""
    new_fresh = """function snapshotValidity(j){
  var dataTs=Date.parse(j&&j.data_as_of||'');
  var staleTs=Date.parse(j&&j.stale_after||'');
  var age=Number.isFinite(dataTs)?Math.max(0,(Date.now()-dataTs)/60000):Infinity;
  var expired=(j&&typeof j.effective_stale==='boolean')?j.effective_stale:(Number.isFinite(staleTs)?Date.now()>=staleTs:true);
  return {valid:expired===false,expired:expired!==false,ageMinutes:age,validUntil:Number.isFinite(staleTs)?staleTs:null};
}
function executionFreshness(us){
  var sv=snapshotValidity(us);
  return {fresh:sv.valid&&Number.isFinite(sv.ageMinutes)&&sv.ageMinutes<=EXECUTION_FRESH_MINUTES,ageMinutes:sv.ageMinutes,snapshotValid:sv.valid};
}"""
    if old_fresh not in text:
        raise SystemExit("executionFreshness source anchor missing")
    text = text.replace(old_fresh, new_fresh, 1)

    f0 = text.find("function stateLabel(")
    f1 = text.find("\nfunction benchmarkMetric(", f0)
    if f0 < 0 or f1 < 0:
        raise SystemExit("command freshness block anchors missing")
    freshness_render = r"""function snapshotStateLabel(j){
  var sv=snapshotValidity(j);
  return '<span class="health-dot '+(sv.valid?'good-dot':'warn-dot')+'"></span>'+(sv.valid?'VALID':'EXPIRED');
}
function renderCommandModel(j){
  kalmanCommandState.us=j;
  var box=$('#commandModel');if(!box)return;
  var p=j&&j.payload||{},a=(p.assets||p.top3||[]).slice(0,6);
  var rows=a.map(function(x,i){return '<div class="command-rank"><span>'+(i+1)+'</span><b>'+esc(x.symbol||'—')+'</b><small>'+fmt((n(x.model_score)||0)*10000,2)+' bp</small></div>';}).join('');
  box.className='';
  var ef=executionFreshness(j);
  box.innerHTML='<div class="command-model-head"><div><small>TOP RANK</small><strong>'+esc(a[0]&&a[0].symbol||'—')+'</strong></div><div class="right">'+snapshotStateLabel(j)+'<small>'+time(j&&j.data_as_of)+' · entry signal '+(ef.fresh?'&lt;90m':'expired')+'</small></div></div><div class="command-ranks">'+rows+'</div>';
  renderNextActions();
}
function healthRow(label,state,detail){return '<div class="health-row"><span>'+label+'</span><b>'+state+'</b><small>'+detail+'</small></div>';}
function renderCommandHealth(us,kr,cr,h){
  kalmanCommandState.health=h;kalmanCommandState.us=us;kalmanCommandState.kr=kr;kalmanCommandState.crypto=cr;
  var box=$('#commandHealth');if(!box)return;
  box.className='';
  var usv=snapshotValidity(us),krv=snapshotValidity(kr),crv=snapshotValidity(cr);
  var account=kalmanCommandState.account,bot=botState(account);
  var windowKnown=Boolean(bot&&typeof bot.usFractionalOrderWindowOpen==='boolean');
  var windowState=windowKnown?(bot.usFractionalOrderWindowOpen?'OPEN':'CLOSED'):'UNKNOWN';
  var windowKind=windowKnown&&bot.usFractionalOrderWindowOpen?'good-dot':'warn-dot';
  box.innerHTML=[
    healthRow('US SNAPSHOT',snapshotStateLabel(us),time(us&&us.data_as_of)+' · valid until '+time(us&&us.stale_after)),
    healthRow('KR SNAPSHOT',snapshotStateLabel(kr),time(kr&&kr.data_as_of)+' · valid until '+time(kr&&kr.stale_after)),
    healthRow('CRYPTO SNAPSHOT',snapshotStateLabel(cr),time(cr&&cr.data_as_of)+' · valid until '+time(cr&&cr.stale_after)),
    healthRow('US ORDER WINDOW','<span class="health-dot '+windowKind+'"></span>'+windowState,windowKnown?'Toss market calendar':'trading link required')
  ].join('');
  var head=$('#headerDataState');
  if(head){var ok=usv.valid&&krv.valid&&crv.valid;head.className='pill '+(ok?'ok':'warn');head.textContent=ok?'SNAPSHOTS VALID':'SNAPSHOT CHECK';}
}
"""
    text = text[:f0] + freshness_render + text[f1:]

    # Research/model views must never look like live order instructions.
    u0 = text.find("function universeActionFor(")
    u1 = text.find("\nfunction buildUniverseRows", u0)
    if u0 < 0 or u1 < 0:
        raise SystemExit("universeActionFor anchors missing")
    universe_action = r"""function universeActionFor(asset,held,fx,fresh){
  var rank=Number(asset&&asset.rank||999);
  var isTop=rank<=UNIVERSE_TOP_COUNT;
  var currentKrw=(held&&fx)?marketValueUsd(held)*n(fx.rate||0):0;
  var gap=Math.max(0,UNIVERSE_TARGET_KRW-currentKrw);
  if(isTop){
    if(held&&gap<UNIVERSE_MIN_ORDER_KRW)return{label:'AT TARGET',kind:'hold',detail:'RESEARCH TOP-6 #'+rank};
    return{
      label:held?'TOP-UP PREVIEW':'ADD PREVIEW',
      kind:'watch',
      detail:(gap>=UNIVERSE_MIN_ORDER_KRW?money(Math.min(UNIVERSE_TARGET_KRW,Math.floor(gap)),'KRW')+' · ':'')+'RESEARCH TOP-6 #'+rank
    };
  }
  if(held)return{label:'EXIT PREVIEW',kind:'watch',detail:'OUTSIDE RESEARCH TOP-6'};
  return{label:'WATCH',kind:'watch',detail:'RANK #'+rank};
}"""
    text = text[:u0] + universe_action + text[u1:]
    text = text.replace(
        "var actions=universeState.rows.filter(function(x){return ['buy','sell'].includes(x.action.kind);}).length;",
        "var actions=universeState.rows.filter(function(x){return String(x.action&&x.action.label||'').includes('PREVIEW');}).length;"
    )
    text = text.replace(
        "['MODEL PLAN',actions,fi.fresh?'ranking plan':'preview only']",
        "['RESEARCH PREVIEW',actions,'not live execution']"
    )
    text = text.replace(
        "전체 후보 · 현재 R5.1 score · 보유/Top-6/예정 액션",
        "전체 후보 · 현재 R5.1 score · Top-6 research preview · 실제 주문 아님"
    )
    text = text.replace("<th>Model Plan</th>", "<th>Research Preview</th>")
    text = text.replace('<option value="ACTION">ACTION</option>', '<option value="ACTION">PREVIEW</option>')
    text = text.replace(
        "if(f==='ACTION')rows=rows.filter(function(x){return ['buy','sell','hold'].includes(x.action.kind);});",
        "if(f==='ACTION')rows=rows.filter(function(x){return String(x.action&&x.action.label||'').includes('PREVIEW');});"
    )
    text = text.replace(
        "if(f==='WATCH')rows=rows.filter(function(x){return x.action.kind==='watch';});",
        "if(f==='WATCH')rows=rows.filter(function(x){return String(x.action&&x.action.label||'')==='WATCH';});"
    )
    text = text.replace("var fi=executionFreshness(universeState.us);", "var fi=snapshotValidity(universeState.us);")
    text = text.replace("fi.fresh?'R5.1 FRESH':'R5.1 PREVIEW'", "fi.valid?'SNAPSHOT VALID':'SNAPSHOT EXPIRED'")
    text = text.replace("<th>4h Target</th>", "<th>Model 4h Target</th>")
    text = text.replace("<th>Δ Target</th>", "<th>Model Δ</th>")
    text = text.replace("2026 R5.1 Ledger", "R5.1 SHADOW / MODEL EVALUATION LEDGER")
    text = text.replace(">FORWARD<", ">MODEL FORWARD<")
    text = text.replace("badge('FORWARD','ok')", "badge('MODEL FORWARD','ok')")
    text = text.replace("R5.1 TOP-1", "R5.1 MODEL TOP-1 · RESEARCH")
    text = text.replace("<h3>R5.1 Model Universe</h3>", "<h3>R5.1 Model Ranking</h3>")
    text = text.replace("LIVE RANKING", "MODEL RANKING")
    text = text.replace("${staleBadge(x.stale)}</div><div class=\"kpi\">", "${badge('EMBEDDED SNAPSHOT')}</div><div class=\"kpi\">")

    # User-facing terminology: Korean state words, English only for system identifiers.
    wording = [
        ("NOT EXECUTABLE", "주문 불가"),
        ("GUARDED", "게이트 대기"),
        ("LIVE READY", "실행 가능"),
        ("TRADING LINK OFFLINE", "Toss 오프라인"),
        ("TRADING LINK ONLINE", "Toss 연결됨"),
        ("BROKER LINK OFFLINE", "Toss 오프라인"),
        ("BROKER LINK ONLINE", "Toss 연결됨"),
        ("ENTRY SIGNAL EXPIRED", "진입 신호 만료"),
        ("ENTRY SIGNAL <90M", "진입 신호 유효 (<90분)"),
        ("SERVER GATES NOT LIVE", "자동매매 게이트 닫힘"),
        ("SERVER LIVE GATES OPEN", "자동매매 게이트 열림"),
        ("SERVER GATES NOT CONFIRMED", "자동매매 게이트 확인 불가"),
        ("EXECUTION MIRROR HAS ROWS", "실매매 기록 있음"),
        ("EXECUTION MIRROR EMPTY", "실매매 기록 없음"),
        ("MIRROR EMPTY", "기록 없음"),
        ("SNAPSHOTS VALID", "데이터 정상"),
        ("SNAPSHOT CHECK", "데이터 확인 필요"),
        ("SNAPSHOT VALID", "스냅샷 유효"),
        ("SNAPSHOT EXPIRED", "스냅샷 만료"),
        ("US SNAPSHOT", "US 데이터"),
        ("KR SNAPSHOT", "KR 데이터"),
        ("CRYPTO SNAPSHOT", "Crypto 데이터"),
        ("US ORDER WINDOW", "미국 주문시간"),
        ("OPEN", "주문 가능"),
        ("CLOSED", "마감"),
        ("UNKNOWN", "확인 불가"),
        ("LIVE POLICY", "실매매 정책"),
        ("TARGET SIZE", "진입 금액"),
        ("LIVE EXITS", "손절 / 익절"),
        ("EARLY / MAX EXIT", "교체 / 최대 보유"),
        ("last canary candidate", "최근 canary 후보"),
        ("SHADOW signal is expected", "SHADOW 신호 사용"),
        ("per new entry", "신규 진입 1회 기준"),
        ("stop loss · take profit", "손절 · 익절"),
        ("canonical buckets max", "canonical bucket 최대"),
        ("RESEARCH PREVIEW", "연구 미리보기"),
        ("ADD PREVIEW", "편입 미리보기"),
        ("TOP-UP PREVIEW", "추가 미리보기"),
        ("EXIT PREVIEW", "제외 미리보기"),
        ("AT TARGET", "목표 도달"),
        ("WATCH", "관찰"),
        ("RESEARCH TOP-6", "연구 Top-6"),
        ("OUTSIDE RESEARCH TOP-6", "연구 Top-6 제외"),
        ("Research Preview", "연구 미리보기"),
        ("R5.1 SHADOW / MODEL EVALUATION LEDGER", "R5.1 SHADOW · 모델 평가 기록"),
        ("R5.1 Model Ranking", "R5.1 모델 순위"),
        ("MODEL RANKING", "모델 순위"),
        ("Model 4h Target", "모델 4h 목표"),
        ("Model Δ", "모델 Δ"),
        ("MODEL FORWARD", "모델 Forward"),
        ("PORTFOLIO", "평가금액"),
        ("P / L", "손익"),
        ("BUYING POWER", "주문가능금액"),
        ("BROKER", "Toss"),
        ("server offline", "연결 끊김"),
        ("Neon model data continues", "모델 데이터는 계속 표시"),
        ("NO BROKER DATA", "계좌 데이터 없음"),
        ("READ ONLY", "조회 전용"),
    ]
    for old, new in wording:
        text = text.replace(old, new)

    text = text.replace("valid until ", "유효기한 ")
    text = text.replace("entry signal &lt;90m", "진입 신호 유효 (&lt;90분)")
    text = text.replace("entry signal expired", "진입 신호 만료")
    text = text.replace("Toss Securities · trading link offline / broker data 없음", "Toss Securities · 연결 끊김 · 계좌 데이터 없음")
    text = text.replace("Toss Securities · 계좌 연결됨", "Toss Securities · 연결됨")
    text = text.replace(
        "<b>Research benchmark only:</b>",
        "<b>연구용 벤치마크:</b>"
    )
    text = text.replace(
        "따라서 live auto-trade P/L과 직접 비교하면 안 됩니다.",
        "실매매 손익과 직접 비교하지 않습니다."
    )
    text = text.replace(
        "sequence compounded 값은 겹치는 window 때문에 포트폴리오 누적수익으로 표시하지 않습니다.",
        "겹치는 window이므로 sequence compounded 값은 포트폴리오 누적수익으로 표시하지 않습니다."
    )
    text = text.replace(
        "<b>구분:</b> Top-6는 research benchmark/portfolio preview이며 실제 자동매매 selector가 아닙니다. 실제 신규 진입 후보는 SHADOW_CANARY 계약을 통과한 단일 R5.1 signal입니다. 웹은 주문을 제출하지 않습니다.",
        "<b>구분:</b> Top-6는 연구용 비교/미리보기이며 실제 자동매매 대상 선정에 사용하지 않습니다. 신규 진입은 SHADOW_CANARY 조건을 통과한 단일 R5.1 신호만 사용합니다. 웹은 주문을 제출하지 않습니다."
    )
    text = text.replace("Neon execution mirror 0 rows", "Neon 실매매 미러 기록 없음")
    text = text.replace(
        "현재 bot 주문/체결이 Neon에 미러링되지 않았다는 뜻입니다. Toss 계정 전체 거래내역이 0건이라는 뜻은 아닙니다.",
        "현재 자동매매 주문·체결이 Neon에 기록되지 않았다는 뜻입니다. Toss 전체 거래내역이 0건이라는 뜻은 아닙니다."
    )
    text = text.replace("+ ' MIRRORED'", "+ '건 기록'")
    text = text.replace("<th>Signal</th><th>Symbol</th><th>State</th><th>Entry Avg</th><th>Exit Avg</th><th>Realized Return</th><th>Exit reason</th>",
                        "<th>신호 시각</th><th>종목</th><th>상태</th><th>평균 진입가</th><th>평균 청산가</th><th>실현수익률</th><th>청산 사유</th>")
    text = text.replace("<th>Entry</th><th>Symbol</th><th>Type</th><th>Entry</th><th>Exit</th><th>Return</th><th>Status</th>",
                        "<th>진입 시각</th><th>종목</th><th>구분</th><th>진입가</th><th>청산가</th><th>수익률</th><th>상태</th>")

    text = text.replace("vNext.7.4.21", TARGET)
    p.write_text(text, encoding="utf-8")


def patch_style(src: Path) -> None:
    p = src / "style.css"
    text = p.read_text(encoding="utf-8")
    text += r"""

/* vNext.7.4.22 — decision console */
.control-grid{grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);align-items:stretch}
.execution-panel{grid-row:span 2}
.execution-hero{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;padding:8px 0 12px}
.execution-hero>div{display:flex;flex-direction:column}
.execution-hero small{font-size:10px;color:#8293b2;font-weight:850;letter-spacing:.06em}
.execution-hero strong{font-size:34px;line-height:1.05;margin:3px 0}
.execution-hero span:not(.pill){font-size:12px;color:#a8b5cc}
.execution-rule-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}
.execution-rule-grid>div{background:#0e182a;border:1px solid #24334f;border-radius:10px;padding:9px;display:flex;flex-direction:column}
.execution-rule-grid span,.benchmark-col span{font-size:9px;color:#8293b2;font-weight:850;letter-spacing:.05em}
.execution-rule-grid b{font-size:14px;margin-top:2px}
.execution-rule-grid small{font-size:9px;color:#72819e}
.execution-gates{display:flex;flex-wrap:wrap;gap:5px;margin-top:10px}
.benchmark-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:8px}
.benchmark-col{padding:10px;background:#0e182a;border:1px solid #24334f;border-radius:10px;display:flex;flex-direction:column}
.benchmark-col b{font-size:20px;margin:2px 0}
.benchmark-col small{font-size:9px;color:#8293b2}
.benchmark-foot{display:flex;justify-content:space-between;gap:12px;padding:8px 2px 5px;font-size:10px;color:#8293b2}
.benchmark-foot b{color:#d7e0f2}
.execution-ledger-card{order:2}
.execution-empty,.account-offline{display:flex;justify-content:space-between;gap:16px;align-items:center;background:#0e1729;border:1px dashed #3a4864;border-radius:12px;padding:14px}
.execution-empty span,.account-offline span{display:block;color:var(--muted);font-size:11px;margin-top:3px}
.account-offline b{color:var(--warn)}
@media(max-width:900px){.control-grid{grid-template-columns:1fr}.execution-panel{grid-row:auto}}
@media(max-width:520px){.execution-rule-grid,.benchmark-grid{grid-template-columns:1fr}.execution-hero strong{font-size:28px}.execution-empty,.account-offline{align-items:flex-start}}
"""
    p.write_text(text, encoding="utf-8")


def patch_health(src: Path) -> None:
    p = src / "api/health.js"
    p.write_text(p.read_text(encoding="utf-8").replace("vNext.7.4.21", TARGET), encoding="utf-8")


def validate(src: Path) -> dict:
    api = sorted((src / "api").rglob("*.js"))
    if len(api) != 12:
        raise SystemExit(f"API count changed: {len(api)}")
    bodies={
      "index":(src/"index.html").read_text(encoding="utf-8"),
      "app":(src/"app.js").read_text(encoding="utf-8"),
      "assets":(src/"api/assets.js").read_text(encoding="utf-8"),
      "css":(src/"style.css").read_text(encoding="utf-8"),
      "health":(src/"api/health.js").read_text(encoding="utf-8")
    }
    checks={
      "index":[TARGET,"자동매매 · 실행 조건","연구 벤치마크 · TOP-1 vs TOP-6","실매매 기록 · NEON MIRROR","headerServerState"],
      "app":["renderBenchmark","renderExecutionLedger","Toss 오프라인","실매매 기록 없음","/api/assets?view=control","연구 미리보기","스냅샷 유효","진입 신호 유효 (<90분)"],
      "assets":["async function control","strategy_benchmark_ledger","v_live_trade_ledger","status:'OFFLINE'"],
      "css":["vNext.7.4.22","execution-rule-grid","benchmark-grid","account-offline"],
      "health":[TARGET]
    }
    for name,markers in checks.items():
        miss=[x for x in markers if x not in bodies[name]]
        if miss: raise SystemExit(f"{name} missing {miss}")
    if shutil.which("node"):
        for q in sorted(src.rglob("*.js")):
            subprocess.run(["node","--check",str(q)],check=True,stdout=subprocess.DEVNULL)
    return {
      "source_files":len([x for x in src.rglob("*") if x.is_file()]),
      "api_functions":len(api),
      "version":TARGET,
      "decision_console":True,
      "server_offline_graceful":True,
      "benchmark_panel":True,
      "execution_ledger_panel":True,
      "web_read_only":True
    }


def emit_source_manifest(src: Path, out: Path) -> None:
    rows=[]
    for p in sorted(x for x in src.rglob("*") if x.is_file()):
        rows.append(json.dumps({"file":p.relative_to(src).as_posix(),"data_b64":base64.b64encode(p.read_bytes()).decode("ascii")},separators=(",",":"),ensure_ascii=False))
    out.write_text("\n".join(rows)+"\n",encoding="utf-8")


def node_wrapper(source: bytes) -> str:
    payload=base64.b64encode(gzip.compress(source,compresslevel=9,mtime=0)).decode("ascii")
    return "const z=require('zlib');"+f"const s=z.gunzipSync(Buffer.from('{payload}','base64')).toString('utf8');"+"module._compile(s,__filename);"


def browser_loader() -> str:
    url="https://raw.githubusercontent.com/kimtk94/Codex/main/kalman-hub-recovery/v7.4.22/source_manifest.ndjson"
    return "(()=>{const U="+json.dumps(url)+";fetch(U,{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('manifest '+r.status);return r.text()}).then(t=>{for(const l of t.split(/\\r?\\n/)){if(!l.trim())continue;const x=JSON.parse(l);if(x.file==='app.js'){const b=Uint8Array.from(atob(x.data_b64),c=>c.charCodeAt(0));(0,Function)(new TextDecoder().decode(b))();return}}throw Error('app.js missing')}).catch(e=>{console.error(e);const c=document.querySelector('#content');if(c)c.innerHTML='<div class=\"card bad\">Kalman app recovery failed</div>'})})();"


def emit_vercel_manifest(src: Path, out: Path) -> int:
    files=[]
    for p in sorted(x for x in src.rglob("*") if x.is_file()):
        rel=p.relative_to(src).as_posix()
        if rel=="app.js": data=browser_loader()
        elif rel=="vercel.json":
            cfg=json.loads(p.read_text(encoding="utf-8"))
            fn=dict(cfg.get("functions") or {});fn["api/**/*.js"]={"includeFiles":"**/*"};cfg["functions"]=fn
            data=json.dumps(cfg,ensure_ascii=False,separators=(",",":"))
        elif p.suffix==".js" and (rel.startswith("api/") or rel.startswith("lib/")):
            data=node_wrapper(p.read_bytes())
        else:
            data=p.read_text(encoding="utf-8")
        files.append({"file":rel,"data":data})
    out.write_text(json.dumps(files,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    return out.stat().st_size


def main() -> int:
    OUT_DIR.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kalman-v7422-") as td:
        src=Path(td)/"source";src.mkdir()
        decode_manifest(BASE_MANIFEST,src)
        patch_api(src);patch_index(src);patch_app(src);patch_style(src);patch_health(src)
        report=validate(src)
        source=OUT_DIR/"source_manifest.ndjson";vercel=OUT_DIR/"vercel_manifest.json"
        emit_source_manifest(src,source)
        report["compact_manifest_bytes"]=emit_vercel_manifest(src,vercel)
        report["source_manifest_sha256"]=hashlib.sha256(source.read_bytes()).hexdigest()
        report["vercel_manifest_sha256"]=hashlib.sha256(vercel.read_bytes()).hexdigest()
        (OUT_DIR/"build_report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2,ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
