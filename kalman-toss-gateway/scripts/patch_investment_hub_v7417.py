from __future__ import annotations
import sys
from pathlib import Path

BASE="vNext.7.4.16"
TARGET="vNext.7.4.17"

def once(text,old,new,label):
    n=text.count(old)
    if n!=1: raise SystemExit(f"[FAIL] {label}: expected 1 got {n}")
    return text.replace(old,new,1)

NEXT_HELPERS=r'''
const EXECUTION_FRESH_MINUTES=90;
const TOP6_TARGET_KRW=5000;
const TOP6_TOTAL_LIMIT_KRW=30000;
const TOP6_MIN_ORDER_KRW=1000;
var kalmanCommandState={account:null,us:null,fx:null,health:null,global:null};

function executionFreshness(us){
  var ts=Date.parse(us&&us.data_as_of||'');
  var age=Number.isFinite(ts)?Math.max(0,(Date.now()-ts)/60000):Infinity;
  return {fresh:Number.isFinite(age)&&age<=EXECUTION_FRESH_MINUTES,ageMinutes:age};
}
function marketValueUsd(h){
  var mv=h&&h.marketValue||{};
  return n(mv.amountAfterCost!=null?mv.amountAfterCost:mv.amount)||0;
}
function usHoldings(account){
  return asArray(account&&account.holdings).filter(function(h){
    var country=String(h&&h.marketCountry||'').toUpperCase();
    var cur=String(h&&h.currency||'').toUpperCase();
    return (country==='US'||cur==='USD')&&n(qty(h))>0;
  });
}
function nextActionRow(symbol,action,reason,detail,kind){
  return '<div class="next-action-row '+(kind||'')+'"><div class="next-symbol"><b>'+esc(symbol)+'</b><small>'+esc(reason)+'</small></div><div class="next-action"><b>'+esc(action)+'</b><small>'+esc(detail)+'</small></div></div>';
}
function renderNextActions(){
  var box=$('#commandNextActions');if(!box)return;
  var account=kalmanCommandState.account,us=kalmanCommandState.us,fx=kalmanCommandState.fx;
  if(!account||!us){
    box.className='muted';
    box.textContent='계좌와 US 모델을 함께 불러오는 중...';
    return;
  }
  box.className='';
  var assets=(us.payload&&(us.payload.assets||us.payload.top3)||[]).slice(0,6);
  if(assets.length<6){
    box.innerHTML='<div class="notice error">Top-6 target가 완전하지 않아 다음 액션을 계산하지 않습니다.</div>';
    return;
  }
  var targetMap=new Map(assets.map(function(x,i){return [String(x.symbol||'').toUpperCase(),{rank:i+1,row:x}];}));
  var holdings=usHoldings(account),holdingMap=new Map(holdings.map(function(h){return [String(h.symbol||'').toUpperCase(),h];}));
  var fresh=executionFreshness(us),rate=n(fx&&fx.rate);
  var executionOn=account.trade_execution===true;
  var sells=holdings.filter(function(h){return !targetMap.has(String(h.symbol||'').toUpperCase());});
  var rows=[];

  sells.forEach(function(h){
    var sym=String(h.symbol||'').toUpperCase();
    var value=marketValueUsd(h);
    var detail=fresh.fresh?'NEXT US ORDER WINDOW':'fresh R5.1 확인 후';
    if(value>0)detail+=' · '+accountUsd(value,2);
    rows.push(nextActionRow(sym,fresh.fresh?'SELL':'SELL PREVIEW','NOT IN TOP-6',detail,'sell-plan'));
  });

  assets.forEach(function(x,i){
    var sym=String(x.symbol||'').toUpperCase(),h=holdingMap.get(sym);
    var currentKrw=(h&&rate)?marketValueUsd(h)*rate:0;
    var gap=Math.max(0,TOP6_TARGET_KRW-currentKrw);
    if(h&&gap<TOP6_MIN_ORDER_KRW){
      rows.push(nextActionRow(sym,'HOLD','TARGET #'+(i+1),'near ₩5,000 target','hold-plan'));
      return;
    }
    var action=h?'TOP-UP':'BUY';
    var amount=gap>=TOP6_MIN_ORDER_KRW?Math.min(TOP6_TARGET_KRW,Math.floor(gap)):0;
    var timing=sells.length?'AFTER SELL CONFIRM':'NEXT US ORDER WINDOW';
    if(!fresh.fresh){action+=' PREVIEW';timing='fresh R5.1 확인 후';}
    rows.push(nextActionRow(sym,action,'TARGET #'+(i+1),(amount?money(amount,'KRW')+' · ':'')+timing,'buy-plan'));
  });

  var status=fresh.fresh
    ?(executionOn?'PLAN READY · EXECUTION ON':'PLAN READY · EXECUTION OFF')
    :'WAITING FOR FRESH US SNAPSHOT';
  var age=Number.isFinite(fresh.ageMinutes)?Math.round(fresh.ageMinutes)+'m old':'age unknown';
  box.innerHTML='<div class="next-actions-head"><div><b>'+status+'</b><small>US only · max 6 · ₩5,000 each · ₩30,000 cap</small></div><div class="right"><span class="pill '+(fresh.fresh?'ok':'warn')+'">'+(fresh.fresh?'FRESH':'PREVIEW')+'</span><small>'+age+'</small></div></div><div class="next-actions-list">'+rows.join('')+'</div><div class="next-actions-note">SELL-first sequencing. BUY/TOP-UP은 비대상 종목 정리 후 다음 cycle에 계산됩니다. 화면은 주문 자체가 아니라 현재 계좌 + R5.1 기준 운용 계획입니다.</div>';
}
'''


ACCOUNT_API=r'''const GATEWAY=(process.env.TOSS_GATEWAY_URL||'').replace(/\/+$/,'');
const SECRET=process.env.HUB_GATEWAY_SECRET||'';

async function gateway(path){
  if(!GATEWAY)throw new Error('TOSS_GATEWAY_URL is not configured');
  const r=await fetch(GATEWAY+path,{
    headers:{'Accept':'application/json','X-Gateway-Secret':SECRET},
    cache:'no-store'
  });
  let body=null;
  try{body=await r.json()}catch(_){body={error:'INVALID_GATEWAY_JSON'}}
  if(!r.ok){
    const e=new Error('gateway '+path+' HTTP '+r.status);
    e.status=r.status;e.body=body;throw e;
  }
  return body;
}

export default async function handler(req,res){
  res.setHeader('Cache-Control','no-store');
  if(req.method!=='GET')return res.status(405).json({error:'METHOD_NOT_ALLOWED'});
  const specs=[
    ['accounts','/api/accounts'],
    ['holdings','/api/holdings'],
    ['buying_power_usd','/api/buying-power?currency=USD'],
    ['buying_power_krw','/api/buying-power?currency=KRW'],
    ['gateway_health','/health']
  ];
  const settled=await Promise.allSettled(specs.map(function(x){return gateway(x[1])}));
  const out={};
  const parts={};
  specs.forEach(function(spec,i){
    const key=spec[0],r=settled[i];
    if(r.status==='fulfilled'){
      out[key]=r.value;
      parts[key]={ok:true};
    }else{
      out[key]=null;
      parts[key]={ok:false,error:String(r.reason&&r.reason.message||r.reason)};
    }
  });
  const required=['accounts','holdings','buying_power_usd','buying_power_krw'];
  const ready=required.every(function(k){return parts[k]&&parts[k].ok===true});
  const gh=out.gateway_health||{};
  return res.status(ready?200:502).json({
    status:ready?'READY':'DEGRADED',
    generated_at:new Date().toISOString(),
    trade_execution:gh.liveGateOpen===true,
    trading_enabled:gh.tradingEnabled===true,
    auto_trade_profile:'US_R5_1_TOP6_30000',
    limits:gh.limits||null,
    accounts:out.accounts,
    holdings:out.holdings,
    buying_power_usd:out.buying_power_usd,
    buying_power_krw:out.buying_power_krw,
    gateway_health:gh,
    parts:parts
  });
}
'''

CSS=r'''
/* vNext.7.4.17 — next actions / execution-aware freshness */
.next-actions-panel{grid-column:1/-1}
.next-actions-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:9px}.next-actions-head>div:first-child{display:flex;flex-direction:column}.next-actions-head b{font-size:13px}.next-actions-head small{font-size:10px;color:#7f91b1}.next-actions-list{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}.next-action-row{display:flex;justify-content:space-between;gap:10px;padding:8px 9px;border:1px solid #24334f;border-radius:9px;background:#0e182a}.next-symbol,.next-action{display:flex;flex-direction:column;min-width:0}.next-symbol b{font-size:12px}.next-symbol small,.next-action small{font-size:9px;color:#8293b2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.next-action{text-align:right}.next-action b{font-size:10px;letter-spacing:.03em}.sell-plan .next-action b{color:#ff9e9e}.buy-plan .next-action b{color:#9fd3ff}.hold-plan .next-action b{color:var(--good)}.next-actions-note{margin-top:8px;font-size:9px;color:#71819e;border-top:1px solid #21304a;padding-top:7px}
@media(max-width:900px){.next-actions-list{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:600px){.next-actions-list{grid-template-columns:1fr}.next-actions-head{align-items:flex-start}}
'''

def main():
    if len(sys.argv)!=2: raise SystemExit("usage: patch_investment_hub_v7417.py <source-root>")
    root=Path(sys.argv[1]); ap=root/"app.js";cp=root/"style.css";ip=root/"index.html";hp=root/"api/health.js"
    for p in (ap,cp,ip,hp):
        if not p.exists(): raise SystemExit(f"[FAIL] missing {p}")
    account_path=root/"api/account.js"
    app=ap.read_text();css=cp.read_text();idx=ip.read_text();health=hp.read_text()
    if BASE not in idx: raise SystemExit("[FAIL] v7.4.16 base missing")
    for m in ("commandAccount","commandModel","commandHealth","loadUsPrimaryChart","R5.1 Top 6"):
        if m not in app and m not in idx: raise SystemExit(f"[FAIL] v7.4.16 marker missing: {m}")

    idx=once(
        idx,
        '<article class="command-panel"><div class="panel-kicker">SYSTEM HEALTH</div><div id="commandHealth" class="muted">데이터 상태를 확인하는 중...</div></article>',
        '<article class="command-panel"><div class="panel-kicker">SYSTEM HEALTH</div><div id="commandHealth" class="muted">데이터 상태를 확인하는 중...</div></article>\n        <article class="command-panel next-actions-panel"><div class="panel-kicker">NEXT ACTIONS · US TOP-6</div><div id="commandNextActions" class="muted">다음 운용 계획을 계산하는 중...</div></article>',
        "next actions panel"
    )

    app=once(app,"function cmdMetric(label,value,sub,kind){",NEXT_HELPERS+"\nfunction cmdMetric(label,value,sub,kind){","next actions helpers")

    app=once(
        app,
        "function renderCommandAccount(j,fx){\n  var box=$('#commandAccount');if(!box)return;",
        "function renderCommandAccount(j,fx){\n  kalmanCommandState.account=j;kalmanCommandState.fx=fx;\n  var box=$('#commandAccount');if(!box)return;",
        "capture account state"
    )
    app=once(
        app,
        "  ].join('');\n}\nfunction stateLabel(stale)",
        "  ].join('');\n  renderNextActions();\n}\nfunction stateLabel(stale)",
        "render actions after account"
    )

    app=once(
        app,
        "function renderCommandModel(j){\n  var box=$('#commandModel');if(!box)return;",
        "function renderCommandModel(j){\n  kalmanCommandState.us=j;\n  var box=$('#commandModel');if(!box)return;",
        "capture US state"
    )
    app=once(
        app,
        "  box.innerHTML='<div class=\"command-model-head\"><div><small>TOP SIGNAL</small><strong>'+esc(a[0]&&a[0].symbol||'—')+'</strong></div><div class=\"right\">'+stateLabel(j&&j.effective_stale)+'<small>'+time(j&&j.data_as_of)+'</small></div></div><div class=\"command-ranks\">'+rows+'</div>';\n}",
        "  var ef=executionFreshness(j);\n  box.innerHTML='<div class=\"command-model-head\"><div><small>TOP RANK</small><strong>'+esc(a[0]&&a[0].symbol||'—')+'</strong></div><div class=\"right\">'+stateLabel(!ef.fresh)+'<small>'+time(j&&j.data_as_of)+'</small></div></div><div class=\"command-ranks\">'+rows+'</div>';\n  renderNextActions();\n}",
        "execution-aware model freshness"
    )

    app=once(
        app,
        "function renderCommandHealth(us,g,h){\n  var box=$('#commandHealth');if(!box)return;",
        "function renderCommandHealth(us,g,h){\n  kalmanCommandState.health=h;\n  var box=$('#commandHealth');if(!box)return;",
        "capture health"
    )
    app=once(
        app,
        "  box.innerHTML=[\n    healthRow('US DATA',stateLabel(us&&us.effective_stale),time(us&&us.data_as_of)),",
        "  var usExec=executionFreshness(us);\n  box.innerHTML=[\n    healthRow('US DATA',stateLabel(!usExec.fresh),time(us&&us.data_as_of)),",
        "health freshness"
    )
    app=once(
        app,
        "  var head=$('#headerDataState');if(head){var live=!(us&&us.effective_stale)&&!kr.stale&&!cr.stale;head.className='pill '+(live?'ok':'warn');head.textContent=live?'DATA LIVE':'DATA CHECK';}",
        "  var head=$('#headerDataState');if(head){var live=usExec.fresh&&!kr.stale&&!cr.stale;head.className='pill '+(live?'ok':'warn');head.textContent=live?'DATA LIVE':'DATA CHECK';}",
        "header freshness"
    )

    idx=idx.replace(BASE,TARGET)
    health=health.replace(BASE,TARGET)
    css=css.rstrip()+"\n\n"+CSS.strip()+"\n"
    account_path.write_text(ACCOUNT_API,encoding="utf-8")

    for m in ("commandNextActions","renderNextActions","WAITING FOR FRESH US SNAPSHOT","SELL PREVIEW","TOP6_TARGET_KRW","US Top-6 armed"):
        if m not in app and m not in idx: raise SystemExit(f"[FAIL] v7.4.17 marker missing: {m}")
    if len(list((root/"api").rglob("*.js")))!=12: raise SystemExit("[FAIL] API function count changed")

    ap.write_text(app);cp.write_text(css);ip.write_text(idx);hp.write_text(health)
    print("[PASS] vNext.7.4.17 next-actions panel")
    print("[PASS] execution freshness = 90 minutes")
    print("[PASS] SELL-first US Top-6 plan preview")
    print("[PASS] account API reflects gateway liveGateOpen")
    print("[PASS] API function count = 12")
    return 0
if __name__=="__main__": raise SystemExit(main())
