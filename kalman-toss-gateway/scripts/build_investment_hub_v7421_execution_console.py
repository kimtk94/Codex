from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE_MANIFEST = ROOT / "kalman-hub-recovery/v7.4.20/source_manifest.ndjson"
OUT_DIR = ROOT / "kalman-hub-recovery/v7.4.21"
TARGET = "vNext.7.4.21"


def decode_manifest(manifest: Path, out: Path) -> None:
    count = 0
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        rel = Path(row["file"])
        if rel.is_absolute() or ".." in rel.parts:
            raise SystemExit(f"unsafe path: {rel}")
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(base64.b64decode(row["data_b64"]))
        count += 1
    if count != 30:
        raise SystemExit(f"expected 30 files, got {count}")


def patch_assets(src: Path) -> None:
    p = src / "api/assets.js"
    text = p.read_text(encoding="utf-8")

    start = text.find("async function account(req,res){")
    end = text.find("async function dashboard(req,res){", start)
    if start < 0 or end < 0:
        raise SystemExit("account() anchors missing")

    replacement = r"""async function optionalGatewayGet(path){
  try{return {ok:true,data:await gatewayGet(path),status:200}}
  catch(e){return {ok:false,data:null,error:e.code||e.name||'GATEWAY_ERROR',status:e.status||null}}
}
async function account(req,res){
  res.setHeader('Cache-Control','no-store');
  if(!GATEWAY_URL||!process.env.HUB_GATEWAY_SECRET)return res.status(503).json({error:'ACCOUNT_GATEWAY_NOT_CONFIGURED',gateway_url_configured:Boolean(GATEWAY_URL),gateway_url_source:GATEWAY.source,gateway_secret_configured:Boolean(process.env.HUB_GATEWAY_SECRET),trade_execution:false,server_trade_execution:false});
  const paths={accounts:'/api/accounts',holdings:'/api/holdings',buying_power_usd:'/api/buying-power?currency=USD',buying_power_krw:'/api/buying-power?currency=KRW'};
  const entries=await Promise.all(Object.entries(paths).map(async([k,path])=>{try{return [k,{ok:true,data:await gatewayGet(path)}]}catch(e){return [k,{ok:false,error:e.code||e.name||'GATEWAY_ERROR',status:e.status||null}]}}));
  const parts=Object.fromEntries(entries),ok=Object.values(parts).filter(x=>x.ok).length;
  const optional=await Promise.all([optionalGatewayGet('/api/trading-status'),optionalGatewayGet('/health')]);
  const tradingStatus=optional[0],gatewayHealth=optional[1];
  if(!ok)return res.status(502).json({error:'ACCOUNT_GATEWAY_UNAVAILABLE',parts:Object.fromEntries(Object.entries(parts).map(([k,v])=>[k,{ok:v.ok,status:v.status,error:v.error}])),trading_status:tradingStatus.data,gateway_health:gatewayHealth.data,trade_execution:false,server_trade_execution:false,generated_at:new Date().toISOString()});
  const bot=tradingStatus.data||null;
  return res.status(200).json({
    schema_version:'investment-hub-account-readonly-v0.2',
    status:ok===4?'READY':'PARTIAL',
    accounts:parts.accounts?.data??null,
    holdings:parts.holdings?.data??null,
    buying_power_usd:parts.buying_power_usd?.data??null,
    buying_power_krw:parts.buying_power_krw?.data??null,
    trading_status:bot,
    gateway_health:gatewayHealth.data||null,
    trading_status_available:Boolean(tradingStatus.ok),
    parts:Object.fromEntries(Object.entries(parts).map(([k,v])=>[k,{ok:v.ok,status:v.status||200,error:v.error||null}])),
    trade_execution:false,
    server_trade_execution:Boolean(bot&&bot.executionMode==='LIVE'&&bot.liveGateOpen===true&&bot.autoTradeEnabled===true),
    generated_at:new Date().toISOString()
  });
}
"""
    text = text[:start] + replacement + text[end:]
    p.write_text(text, encoding="utf-8")


def patch_app(src: Path) -> None:
    p = src / "app.js"
    text = p.read_text(encoding="utf-8")

    old_state = "var kalmanCommandState={account:null,us:null,fx:null,health:null,global:null};"
    if old_state not in text:
        raise SystemExit("command state anchor missing")
    text = text.replace(old_state, old_state + "\nconst LIVE_CANARY_TARGET_KRW=5000;", 1)

    start = text.find("function renderNextActions(){")
    end = text.find("function cmdMetric(", start)
    if start < 0 or end < 0:
        raise SystemExit("renderNextActions anchors missing")

    replacement = r"""function currentUsSelector(us){
  var p=us&&us.payload||{};
  return (p.source_payload&&p.source_payload.today_selector)||p.today_selector||(p.summary&&p.summary.today_selector)||{};
}
function botState(account){return account&&account.trading_status||null}
function yesNo(v,yes,no){return v===true?yes:(v===false?no:'UNKNOWN')}
function renderNextActions(){
  var box=$('#commandNextActions');if(!box)return;
  var account=kalmanCommandState.account,us=kalmanCommandState.us;
  if(!account||!us){
    box.className='muted';
    box.textContent='Toss 계좌 · R5.1 신호 · 서버 bot 상태를 함께 불러오는 중...';
    return;
  }
  box.className='';
  var sel=currentUsSelector(us);
  var assets=(us.payload&&(us.payload.assets||us.payload.top3)||[]);
  var symbol=String(sel.selected_symbol||(assets[0]&&assets[0].symbol)||'').toUpperCase();
  var fresh=executionFreshness(us);
  var bot=botState(account),legacy=account.gateway_health||{};
  var canary=sel.allow_trade_shadow===true&&sel.shadow_entry_this_signal===true;
  var strategy=String((bot&&bot.strategyVersion)||sel.primary_lineage||'R5.1_BASE_HGB');
  var mode=String((bot&&bot.executionMode)||'UNKNOWN').toUpperCase();
  var policy=String((bot&&bot.signalPolicy)||'UNKNOWN').toUpperCase();
  var enabled=bot?bot.autoTradeEnabled===true:null;
  var liveGate=bot?bot.liveGateOpen===true:(legacy.liveGateOpen===true?true:null);
  var holdings=usHoldings(account);
  var openOrders=bot&&Array.isArray(bot.openOrders)?bot.openOrders:[];
  var active=bot&&Array.isArray(bot.activeManagedPositions)?bot.activeManagedPositions:[];
  var accountFlat=bot&&typeof bot.accountFlat==='boolean'?bot.accountFlat:(holdings.length===0?null:false);
  var windowOpen=bot&&typeof bot.usFractionalOrderWindowOpen==='boolean'?bot.usFractionalOrderWindowOpen:null;
  var orderKrw=n(bot&&bot.targetOrderKrw)||LIVE_CANARY_TARGET_KRW;
  var age=Number.isFinite(fresh.ageMinutes)?Math.round(fresh.ageMinutes)+'m old':'age unknown';

  var action='WAIT',reason='SERVER STATUS',detail='trading-status endpoint sync 필요',kind='hold-plan';
  if(active.length){
    var pos=active[0]||{};
    action=String(pos.state||'MANAGED');
    reason='BOT MANAGED POSITION';
    detail=String(pos.symbol||symbol||'—')+' · 4-bucket exit/reconcile';
    kind='hold-plan';
  }else if(!fresh.fresh){
    action='WAIT';reason='STALE R5.1';detail='fresh signal 필요 · '+age;kind='hold-plan';
  }else if(!canary){
    action='WAIT';reason='SHADOW CANARY OFF';detail=symbol||'no eligible symbol';kind='hold-plan';
  }else if(!bot){
    action='SYNC';reason='SERVER BOT STATUS';detail='gateway update 후 LIVE gate 확인';kind='hold-plan';
  }else if(enabled!==true||mode!=='LIVE'){
    action='DRY / OFF';reason='AUTO TRADE NOT LIVE';detail=mode+' · '+policy;kind='hold-plan';
  }else if(!liveGate){
    action='BLOCKED';reason='LIVE GATE CLOSED';detail='TRADING_ENABLED + confirmation 필요';kind='sell-plan';
  }else if(accountFlat===false||openOrders.length){
    action='BLOCKED';reason='ACCOUNT NOT FLAT';detail=holdings.length+' holdings · '+openOrders.length+' open orders';kind='sell-plan';
  }else if(windowOpen===false){
    action='QUEUED';reason='US ORDER WINDOW CLOSED';detail=symbol+' · 다음 허용 window';kind='hold-plan';
  }else{
    action='BUY '+symbol;reason='R5.1 SHADOW CANARY';detail=money(orderKrw,'KRW')+' · cron :25 · server execution';kind='buy-plan';
  }

  var rows=[
    nextActionRow(symbol||'—',action,reason,detail,kind),
    nextActionRow('BOT',mode,policy+' · '+strategy,(bot?'enabled '+yesNo(enabled,'YES','NO'):'status endpoint pending'),''),
    nextActionRow('ACCOUNT',yesNo(accountFlat,'FLAT','NOT FLAT'),'TOSS BROKER',holdings.length+' holdings · '+openOrders.length+' open orders',''),
    nextActionRow('GATES',yesNo(liveGate,'LIVE OPEN','CLOSED'),'FRESH '+yesNo(fresh.fresh,'YES','NO')+' · CANARY '+yesNo(canary,'YES','NO'),'WINDOW '+yesNo(windowOpen,'OPEN','CLOSED'),'')
  ];

  var ready=action.indexOf('BUY ')===0;
  box.innerHTML='<div class="next-actions-head"><div><b>'+(ready?'LIVE CANARY READY':'AUTO-TRADE CHECK')+'</b><small>R5.1 latest eligible signal · 1 position · '+money(orderKrw,'KRW')+' per entry</small></div><div class="right"><span class="pill '+(ready?'ok':'warn')+'">'+(ready?'READY':'GUARDED')+'</span><small>'+age+'</small></div></div><div class="next-actions-list">'+rows.join('')+'</div><div class="next-actions-note">웹은 주문을 제출하지 않습니다. 실제 주문은 서버 cron worker가 :25에 실행하며, account flat · signal freshness · SHADOW_CANARY · live gate · Toss order window를 모두 통과해야 합니다.</div>';
}

"""
    text = text[:start] + replacement + text[end:]

    old_broker = "cmdMetric('BROKER','TOSS','updated '+time(j&&j.generated_at),'')"
    new_broker = "cmdMetric('BOT',(j&&j.trading_status&&j.trading_status.executionMode)||'SYNC',(j&&j.trading_status?((j.trading_status.liveGateOpen?'GATE OPEN':'GATE CLOSED')+' · '+(j.trading_status.strategyVersion||'—')):'Toss connected · bot status pending'),'')"
    if old_broker not in text:
        raise SystemExit("BROKER metric anchor missing")
    text = text.replace(old_broker, new_broker, 1)

    # Make the detailed account status explicitly include bot state.
    old_status = """<div class="statusline">${badge('연결됨','ok')}<span class="muted">계좌 ${accounts.length||1} · 보유 ${holdings.length}종목 · ${time(j.generated_at)}</span></div>"""
    new_status = """<div class="statusline">${badge('TOSS 연결','ok')}<span class="muted">계좌 ${accounts.length||1} · 보유 ${holdings.length}종목 · bot ${esc(j?.trading_status?.executionMode||'SYNC')} · ${time(j.generated_at)}</span></div>"""
    if old_status not in text:
        raise SystemExit("account status anchor missing")
    text = text.replace(old_status, new_status, 1)

    # Universe remains a model portfolio view; do not imply these are submitted orders.
    text = text.replace("<th>Next Action</th>", "<th>Model Plan</th>")
    text = text.replace("['ACTION',actions,fi.fresh?'live-plan eligible':'preview only']", "['MODEL PLAN',actions,fi.fresh?'ranking plan':'preview only']")

    text = text.replace("vNext.7.4.20", TARGET)
    p.write_text(text, encoding="utf-8")


def patch_index(src: Path) -> None:
    p = src / "index.html"
    text = p.read_text(encoding="utf-8")
    text = text.replace("NEXT ACTIONS · US TOP-6", "AUTO TRADE · NEXT ACTION")
    text = text.replace("다음 운용 계획을 계산하는 중...", "실제 서버 자동매매 상태를 계산하는 중...")
    text = text.replace("Toss Securities · 읽기 전용", "Toss Securities · 계좌 + 서버 bot 상태")
    text = text.replace("vNext.7.4.20 · Command Center + Universe View", TARGET + " · Auto-Trade Console + Universe")
    text = text.replace("vNext.7.4.20", TARGET)
    p.write_text(text, encoding="utf-8")


def patch_health(src: Path) -> None:
    p = src / "api/health.js"
    text = p.read_text(encoding="utf-8").replace("vNext.7.4.20", TARGET)
    p.write_text(text, encoding="utf-8")


def validate(src: Path) -> dict:
    api = sorted((src / "api").rglob("*.js"))
    if len(api) != 12:
        raise SystemExit(f"API count changed: {len(api)}")
    idx = (src / "index.html").read_text(encoding="utf-8")
    app = (src / "app.js").read_text(encoding="utf-8")
    assets = (src / "api/assets.js").read_text(encoding="utf-8")
    health = (src / "api/health.js").read_text(encoding="utf-8")

    required = {
        "index": [TARGET, "AUTO TRADE · NEXT ACTION", "계좌 + 서버 bot 상태", "Auto-Trade Console + Universe"],
        "app": ["LIVE_CANARY_TARGET_KRW=5000", "function currentUsSelector", "R5.1 SHADOW CANARY", "cron :25", "Model Plan"],
        "assets": ["/api/trading-status", "server_trade_execution", "trading_status_available"],
        "health": [TARGET, "trade_enabled", "account_trade_execution"],
    }
    for name, markers in required.items():
        body = {"index": idx, "app": app, "assets": assets, "health": health}[name]
        missing = [m for m in markers if m not in body]
        if missing:
            raise SystemExit(f"{name} missing {missing}")

    if "NEXT ACTIONS · US TOP-6" in idx:
        raise SystemExit("old Top-6 execution label remains")
    if shutil.which("node"):
        for p in sorted(src.rglob("*.js")):
            subprocess.run(["node", "--check", str(p)], check=True, stdout=subprocess.DEVNULL)
    return {
        "source_files": len([p for p in src.rglob("*") if p.is_file()]),
        "api_functions": len(api),
        "version": TARGET,
        "auto_trade_console": True,
        "server_bot_status": True,
        "fixed_krw_display": 5000,
        "web_read_only": True,
    }


def emit_source_manifest(src: Path, out: Path) -> None:
    rows = []
    for p in sorted(x for x in src.rglob("*") if x.is_file()):
        rows.append(json.dumps({
            "file": p.relative_to(src).as_posix(),
            "data_b64": base64.b64encode(p.read_bytes()).decode("ascii")
        }, separators=(",", ":"), ensure_ascii=False))
    out.write_text("\n".join(rows) + "\n", encoding="utf-8")


def node_wrapper(source: bytes) -> str:
    payload = base64.b64encode(gzip.compress(source, compresslevel=9, mtime=0)).decode("ascii")
    return "const z=require('zlib');" + f"const s=z.gunzipSync(Buffer.from('{payload}','base64')).toString('utf8');" + "module._compile(s,__filename);"


def browser_loader() -> str:
    url = "https://raw.githubusercontent.com/kimtk94/Codex/main/kalman-hub-recovery/v7.4.21/source_manifest.ndjson"
    return (
        "(()=>{const U=" + json.dumps(url) + ";"
        "fetch(U,{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('manifest '+r.status);return r.text()})"
        ".then(t=>{for(const l of t.split(/\\r?\\n/)){if(!l.trim())continue;const x=JSON.parse(l);"
        "if(x.file==='app.js'){const b=Uint8Array.from(atob(x.data_b64),c=>c.charCodeAt(0));"
        "(0,Function)(new TextDecoder().decode(b))();return}}throw Error('app.js missing')})"
        ".catch(e=>{console.error(e);const c=document.querySelector('#content');if(c)c.innerHTML='<div class=\"card bad\">Kalman app recovery failed</div>'})})();"
    )


def emit_vercel_manifest(src: Path, out: Path) -> int:
    files = []
    for p in sorted(x for x in src.rglob("*") if x.is_file()):
        rel = p.relative_to(src).as_posix()
        if rel == "app.js":
            data = browser_loader()
        elif rel == "vercel.json":
            cfg = json.loads(p.read_text(encoding="utf-8"))
            functions = dict(cfg.get("functions") or {})
            functions["api/**/*.js"] = {"includeFiles": "**/*"}
            cfg["functions"] = functions
            data = json.dumps(cfg, ensure_ascii=False, separators=(",", ":"))
        elif p.suffix == ".js" and (rel.startswith("api/") or rel.startswith("lib/")):
            data = node_wrapper(p.read_bytes())
        else:
            data = p.read_text(encoding="utf-8")
        files.append({"file": rel, "data": data})
    out.write_text(json.dumps(files, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return out.stat().st_size


def main() -> int:
    if not BASE_MANIFEST.exists():
        raise SystemExit(f"missing {BASE_MANIFEST}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kalman-v7421-") as td:
        src = Path(td) / "source"
        src.mkdir()
        decode_manifest(BASE_MANIFEST, src)
        patch_assets(src)
        patch_app(src)
        patch_index(src)
        patch_health(src)
        report = validate(src)

        source = OUT_DIR / "source_manifest.ndjson"
        vercel = OUT_DIR / "vercel_manifest.json"
        emit_source_manifest(src, source)
        report["compact_manifest_bytes"] = emit_vercel_manifest(src, vercel)
        report["source_manifest_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        report["vercel_manifest_sha256"] = hashlib.sha256(vercel.read_bytes()).hexdigest()
        (OUT_DIR / "build_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
