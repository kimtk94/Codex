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
    const [bench,signal,exec,managed]=await Promise.all([
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
      exit_rules:{stop_loss_pct:-0.03,take_profit_pct:0.20,model_rotation:true,max_hold_buckets:4},
      latest_signal:(signal&&signal[0])||null,
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
          <div class="panel-kicker">EXECUTION PLAN</div>
          <div id="commandNextActions" class="muted">R5.1 실행 계획을 계산하는 중...</div>
        </article>
        <article class="command-panel">
          <div class="panel-kicker">R5.1 · MODEL SIGNAL</div>
          <div id="commandModel" class="muted">모델 상태를 불러오는 중...</div>
        </article>
        <article class="command-panel">
          <div class="panel-kicker">TOP1 ↔ TOP6 · FORWARD CHECK</div>
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
          <div class="eyebrow">BROKER EXECUTION LEDGER</div>
          <h2>실제 체결 기록</h2>
          <div class="muted">Shadow 성과와 분리 · Toss 체결이 발생한 경우에만 기록</div>
        </div>
        <span id="executionLedgerState" class="pill">NO EXECUTION</span>
      </div>
      <div id="executionLedger"><div class="notice">서버 미가동 상태에서는 체결 기록이 비어 있는 것이 정상입니다.</div></div>
    </section>

'''
    if nav not in text:
        raise SystemExit("nav anchor missing")
    text = text.replace(nav, ledger + nav, 1)

    text = text.replace("vNext.7.4.21 · Auto-Trade Console + Universe", TARGET + " · Decision Console")
    text = text.replace("vNext.7.4.21", TARGET)
    p.write_text(text, encoding="utf-8")


def patch_app(src: Path) -> None:
    p = src / "app.js"
    text = p.read_text(encoding="utf-8")
    text = text.replace(
        "var kalmanCommandState={account:null,us:null,fx:null,health:null,global:null};",
        "var kalmanCommandState={account:null,us:null,fx:null,health:null,global:null,control:null};"
    )

    start = text.find("function renderNextActions(){")
    end = text.find("\nfunction cmdMetric(", start)
    if start < 0 or end < 0:
        raise SystemExit("next actions anchors missing")
    next_fn = r"""function renderNextActions(){
  var box=$('#commandNextActions');if(!box)return;
  var us=kalmanCommandState.us,ctl=kalmanCommandState.control||{},account=kalmanCommandState.account;
  var sig=ctl.latest_signal||{};
  var sel=currentUsSelector(us||{});
  var assets=(us&&us.payload&&(us.payload.assets||us.payload.top3))||[];
  var symbol=String(sig.symbol||sel.selected_symbol||(assets[0]&&assets[0].symbol)||'—').toUpperCase();
  var fresh=executionFreshness(us||{data_as_of:sig.as_of});
  var brokerOnline=account&&account.status!=='OFFLINE';
  var bot=botState(account);
  var brokerExec=ctl.broker_execution_present===true;
  var orderKrw=n(ctl.target_order_krw)||LIVE_CANARY_TARGET_KRW;
  var rules=ctl.exit_rules||{stop_loss_pct:-.03,take_profit_pct:.20,model_rotation:true,max_hold_buckets:4};
  var shadowAllowed=Boolean(sig.payload&&sig.payload.allow_trade_shadow===true&&sig.payload.shadow_entry_this_signal===true);
  if(!shadowAllowed)shadowAllowed=sel.allow_trade_shadow===true&&sel.shadow_entry_this_signal===true;
  var status='PLANNED',kind='warn',headline='SERVER OFFLINE';
  if(brokerOnline&&bot&&bot.autoTradeEnabled===true&&bot.executionMode==='LIVE'&&bot.liveGateOpen===true){
    status='LIVE';kind='ok';headline='LIVE CANARY';
  }else if(brokerOnline){
    status='GUARDED';kind='warn';headline='BROKER CONNECTED';
  }

  box.className='';
  box.innerHTML=
    '<div class="execution-hero"><div><small>'+headline+'</small><strong>'+esc(symbol)+'</strong><span>'+money(orderKrw,'KRW')+' / entry</span></div><span class="pill '+kind+'">'+status+'</span></div>'+
    '<div class="execution-rule-grid">'+
      '<div><span>SIGNAL</span><b>'+esc(sig.signal||'SHADOW')+'</b><small>'+time(sig.as_of||(us&&us.data_as_of))+'</small></div>'+
      '<div><span>ENTRY</span><b>'+money(orderKrw,'KRW')+'</b><small>R5.1 latest eligible</small></div>'+
      '<div><span>EXIT</span><b>-3% / +20%</b><small>SL · TP</small></div>'+
      '<div><span>ROTATE</span><b>'+(rules.model_rotation?'ON':'OFF')+'</b><small>'+fmt(rules.max_hold_buckets,0)+' buckets max</small></div>'+
    '</div>'+
    '<div class="execution-gates">'+
      badge(fresh.fresh?'FRESH':'STALE',fresh.fresh?'ok':'warn')+
      badge(shadowAllowed?'CANARY SIGNAL':'WAIT SIGNAL',shadowAllowed?'ok':'warn')+
      badge(brokerOnline?'BROKER ONLINE':'BROKER OFFLINE',brokerOnline?'ok':'warn')+
      badge(brokerExec?'EXECUTION EXISTS':'NO BROKER FILL',brokerExec?'ok':'')+
    '</div>'+
    '<div class="next-actions-note">웹은 주문하지 않습니다. 서버가 켜지면 동일 계약을 읽어 Toss 주문 상태와 체결 ledger만 추가 표시합니다.</div>';
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
  if(head){head.className='pill '+(offline?'warn':'ok');head.textContent=offline?'SERVER OFFLINE':'SERVER ONLINE';}
  var subtitle=$('#accountSubtitle');
  if(subtitle)subtitle.textContent=offline?'Toss Securities · 서버 미가동 / 계좌 데이터 없음':'Toss Securities · 계좌 연결됨';

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
  if(kalmanCommandState.us&&kalmanCommandState.global&&kalmanCommandState.health){renderCommandHealth(kalmanCommandState.us,kalmanCommandState.global,kalmanCommandState.health);}
}
"""
    text = text[:start] + acc_fn + text[end:]

    anchor = "async function loadCommandCenter(){"
    if anchor not in text:
        raise SystemExit("loadCommandCenter anchor missing")
    renderers = r"""function benchmarkMetric(label,row){
  if(!row)return '<div class="benchmark-col"><span>'+esc(label)+'</span><b>—</b><small>no completed snapshot</small></div>';
  return '<div class="benchmark-col"><span>'+esc(label)+'</span><b>'+pct(row.compounded,100)+'</b><small>avg '+pct(row.avg_net,100)+' · σ '+pct(row.std_net,100)+' · n='+fmt(row.snapshots,0)+'</small></div>';
}
function renderBenchmark(ctl){
  kalmanCommandState.control=ctl;
  var box=$('#commandBenchmark');if(!box)return;
  var b=ctl&&ctl.benchmarks||{},a=b.top1,z=b.top6;
  var delta=(a&&z)?n(z.compounded)-n(a.compounded):null;
  box.className='';
  box.innerHTML=
    '<div class="benchmark-grid">'+benchmarkMetric('TOP-1',a)+benchmarkMetric('TOP-6 EQUAL',z)+'</div>'+
    '<div class="benchmark-foot"><span>same 4-bucket · 10bp</span><b>Δ cumulative '+(delta==null?'—':pct(delta,100))+'</b></div>'+
    '<div class="small">Forward sample only. 전략 선택이 아니라 지속 관찰용 비교입니다.</div>';
  renderExecutionLedger(ctl);
  renderNextActions();
}
function renderExecutionLedger(ctl){
  var box=$('#executionLedger'),state=$('#executionLedgerState');if(!box)return;
  var rows=(ctl&&ctl.execution_ledger)||[];
  if(!rows.length){
    if(state){state.className='pill';state.textContent='NO EXECUTION';}
    box.innerHTML='<div class="execution-empty"><div><b>실제 Toss 체결 0건</b><span>서버가 아직 가동되지 않았으므로 정상입니다. Shadow/benchmark 데이터와 실제 체결 데이터는 분리되어 있습니다.</span></div></div>';
    return;
  }
  if(state){state.className='pill ok';state.textContent=rows.length+' RECENT';}
  box.innerHTML='<div class="table-scroll"><table class="data-table"><thead><tr><th>Signal</th><th>Symbol</th><th>State</th><th>Entry Avg</th><th>Exit Avg</th><th>Return</th><th>Exit reason</th></tr></thead><tbody>'+
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
      getJSON('/api/dashboard?market=GLOBAL'),
      getJSON('/api/health'),
      getJSON('/api/assets?view=control')
    ]);
    renderCommandModel(x[0]);renderCommandHealth(x[0],x[1],x[2]);renderBenchmark(x[3]);
  }catch(e){
    var b=$('#commandBenchmark');if(b)b.innerHTML='<div class="notice error">Neon control data를 읽지 못했습니다.</div>';
  }
}
"""
    text = text[:start] + load + text[end:]

    text = text.replace(
        "healthRow('EXECUTION','<span class=\"health-dot good-dot\"></span>SERVER','US Top-6 gate')",
        "healthRow('EXECUTION',kalmanCommandState.account&&kalmanCommandState.account.status!=='OFFLINE'?'<span class=\"health-dot good-dot\"></span>ONLINE':'<span class=\"health-dot warn-dot\"></span>OFFLINE','server-side only')"
    )

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
      "index":[TARGET,"EXECUTION PLAN","TOP1 ↔ TOP6 · FORWARD CHECK","BROKER EXECUTION LEDGER","headerServerState"],
      "app":["renderBenchmark","renderExecutionLedger","SERVER OFFLINE","NO BROKER FILL","/api/assets?view=control"],
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
