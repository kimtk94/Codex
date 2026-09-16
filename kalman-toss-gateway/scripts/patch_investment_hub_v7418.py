from __future__ import annotations
import sys
from pathlib import Path

BASE="vNext.7.4.17"
TARGET="vNext.7.4.18"

UNIVERSE_JS=r'''
const UNIVERSE_BASELINE_TOTAL=102;
const UNIVERSE_TOP_COUNT=6;
const UNIVERSE_TARGET_KRW=5000;
const UNIVERSE_MIN_ORDER_KRW=1000;
var universeState={rows:[],us:null,account:null,fx:null};

function universeHoldingItems(a){
  return asArray(a&&a.holdings);
}
function universeActionFor(asset,held,fx,fresh){
  var rank=Number(asset&&asset.rank||999);
  var isTop=rank<=UNIVERSE_TOP_COUNT;
  var currentKrw=(held&&fx)?marketValueUsd(held)*n(fx.rate||0):0;
  var gap=Math.max(0,UNIVERSE_TARGET_KRW-currentKrw);
  if(isTop){
    if(held&&gap<UNIVERSE_MIN_ORDER_KRW)return{label:'HOLD',kind:'hold',detail:'TARGET #'+rank};
    var base=held?'TOP-UP':'BUY';
    return{
      label:fresh?base:base+' PREVIEW',
      kind:'buy',
      detail:(gap>=UNIVERSE_MIN_ORDER_KRW?money(Math.min(UNIVERSE_TARGET_KRW,Math.floor(gap)),'KRW')+' · ':'')+'TARGET #'+rank
    };
  }
  if(held)return{label:fresh?'SELL':'SELL PREVIEW',kind:'sell',detail:'NOT IN TOP-6'};
  return{label:'WATCH',kind:'watch',detail:'RANK #'+rank};
}
function buildUniverseRows(us,account,fx){
  var assets=us&&us.payload&&(us.payload.assets||us.payload.top3)||[];
  var heldMap=new Map(
    universeHoldingItems(account).map(function(h){
      return [String(h&&h.symbol||'').toUpperCase(),h];
    })
  );
  var fresh=executionFreshness(us).fresh;
  return assets.map(function(a){
    var symbol=String(a&&a.symbol||'').toUpperCase();
    var held=heldMap.get(symbol)||null;
    var ref=n(a.reference_price),target=n(a.target_price_4h);
    return Object.assign({},a,{
      symbol:symbol,
      held:held,
      top6:Number(a.rank)<=UNIVERSE_TOP_COUNT,
      delta:(ref&&target)?target/ref-1:null,
      action:universeActionFor(a,held,fx,fresh)
    });
  });
}
function universeFlag(label,kind){
  return '<span class="u-flag '+(kind||'')+'">'+esc(label)+'</span>';
}
function universeFilteredRows(){
  var rows=universeState.rows.slice();
  var q=String($('#universeSearch')&&$('#universeSearch').value||'').trim().toUpperCase();
  var f=String($('#universeFilter')&&$('#universeFilter').value||'ALL');
  var sort=String($('#universeSort')&&$('#universeSort').value||'RANK');
  rows=rows.filter(function(x){return !q||x.symbol.includes(q);});
  if(f==='TOP6')rows=rows.filter(function(x){return x.top6;});
  if(f==='HELD')rows=rows.filter(function(x){return !!x.held;});
  if(f==='ACTION')rows=rows.filter(function(x){return ['buy','sell','hold'].includes(x.action.kind);});
  if(f==='WATCH')rows=rows.filter(function(x){return x.action.kind==='watch';});
  rows.sort(function(a,b){
    if(sort==='SCORE')return (n(b.model_score)||-Infinity)-(n(a.model_score)||-Infinity);
    if(sort==='SYMBOL')return a.symbol.localeCompare(b.symbol);
    if(sort==='WEIGHT')return (n(b.position_weight_r4_vol_target)||0)-(n(a.position_weight_r4_vol_target)||0);
    return Number(a.rank||999)-Number(b.rank||999);
  });
  return rows;
}
function universeRowHtml(x){
  var status=[
    x.top6?universeFlag('TOP-6','top6'):null,
    x.held?universeFlag('HELD','held'):null
  ].filter(Boolean).join(' ')||universeFlag('SCORED','scored');
  var hold=x.held
    ?'<b>'+accountUsd(marketValueUsd(x.held),2)+'</b><small>'+esc(qty(x.held)||'')+' sh</small>'
    :'<span class="muted">—</span>';
  var d=n(x.delta);
  return '<tr class="'+(x.top6?'row-top6 ':'')+(x.held?'row-held ':'')+'">'+
    '<td class="rank-cell">'+esc(x.rank)+'</td>'+
    '<td><b class="symbol-cell">'+esc(x.symbol)+'</b></td>'+
    '<td>'+status+'</td>'+
    '<td><b>'+fmt((n(x.model_score)||0)*10000,2)+' bp</b></td>'+
    '<td>'+money(x.reference_price,'USD')+'</td>'+
    '<td>'+money(x.target_price_4h,'USD')+'</td>'+
    '<td class="'+(d==null?'':d>=0?'good':'bad')+'">'+(d==null?'—':pct(d,100))+'</td>'+
    '<td>'+pct(x.position_weight_r4_vol_target,100)+'</td>'+
    '<td class="holding-cell">'+hold+'</td>'+
    '<td><span class="action '+x.action.kind+'">'+esc(x.action.label)+'</span><small class="action-detail">'+esc(x.action.detail)+'</small></td>'+
  '</tr>';
}
function renderUniverseTable(){
  var rows=universeFilteredRows();
  var body=$('#universeRows');
  if(body)body.innerHTML=rows.length?rows.map(universeRowHtml).join(''):'<tr><td colspan="10" class="muted">조건에 맞는 종목이 없습니다.</td></tr>';
  var meta=$('#universeTableMeta');
  var fi=executionFreshness(universeState.us);
  if(meta)meta.textContent=rows.length+' / '+universeState.rows.length+' rows · data '+time(universeState.us&&universeState.us.data_as_of)+' · '+(Number.isFinite(fi.ageMinutes)?Math.round(fi.ageMinutes)+'m old':'age unknown');
}
function renderUniverseView(){
  var c=$('#content');
  var fi=executionFreshness(universeState.us);
  var scored=universeState.rows.length;
  var held=universeState.rows.filter(function(x){return !!x.held;}).length;
  var actions=universeState.rows.filter(function(x){return ['buy','sell'].includes(x.action.kind);}).length;
  var unmapped=Math.max(0,UNIVERSE_BASELINE_TOTAL-scored);
  var summary=[
    ['BASELINE',UNIVERSE_BASELINE_TOTAL,'requested universe'],
    ['R5.1 SCORED',scored,'current contract'],
    ['UNMAPPED',unmapped,'outside current payload'],
    ['HELD',held,'US positions'],
    ['ACTION',actions,fi.fresh?'live-plan eligible':'preview only']
  ].map(function(x){
    return '<div class="u-kpi"><span>'+x[0]+'</span><b>'+x[1]+'</b><small>'+x[2]+'</small></div>';
  }).join('');

  c.innerHTML=
    '<div class="universe-view">'+
      '<div class="universe-title"><div><div class="eyebrow">US R5.1 UNIVERSE</div><h2>Model Ranking Table</h2><div class="muted">전체 후보 · 현재 R5.1 score · 보유/Top-6/예정 액션</div></div><span class="pill '+(fi.fresh?'ok':'warn')+'">'+(fi.fresh?'R5.1 FRESH':'R5.1 PREVIEW')+'</span></div>'+
      '<section class="universe-summary section">'+summary+'</section>'+
      '<section class="card universe-controls section">'+
        '<div class="universe-search"><label>Search</label><input id="universeSearch" type="search" placeholder="GS, ORCL, NVDA..."></div>'+
        '<div><label>Filter</label><select id="universeFilter"><option value="ALL">ALL</option><option value="TOP6">TOP-6</option><option value="HELD">HELD</option><option value="ACTION">ACTION</option><option value="WATCH">WATCH</option></select></div>'+
        '<div><label>Sort</label><select id="universeSort"><option value="RANK">Rank</option><option value="SCORE">Score</option><option value="SYMBOL">Symbol</option><option value="WEIGHT">Weight</option></select></div>'+
        '<button id="universeRefresh" class="btn" type="button">새로고침</button>'+
      '</section>'+
      '<section class="card section universe-note"><b>Universe contract</b><span>현재 Production R5.1 API는 '+scored+'개 scored symbols를 반환합니다. 요청 baseline 102와의 차이 '+unmapped+'개는 현재 dashboard payload에 심볼 identity가 없어 임의 생성하지 않습니다.</span></section>'+
      '<section class="card section universe-table-card"><div class="section-title"><div><h3>US R5.1 Ranking</h3><span id="universeTableMeta" class="small">—</span></div><div class="universe-legend">'+universeFlag('TOP-6','top6')+universeFlag('HELD','held')+'</div></div>'+
      '<div class="universe-table-scroll"><table class="universe-table"><thead><tr><th>Rank</th><th>Symbol</th><th>Status</th><th>Score</th><th>Reference</th><th>4h Target</th><th>Δ Target</th><th>Weight</th><th>Holding</th><th>Next Action</th></tr></thead><tbody id="universeRows"></tbody></table></div></section>'+
    '</div>';

  ['universeSearch','universeFilter','universeSort'].forEach(function(id){
    var el=$('#'+id);if(!el)return;
    el.addEventListener(id==='universeSearch'?'input':'change',renderUniverseTable);
  });
  var refresh=$('#universeRefresh');
  if(refresh)refresh.addEventListener('click',loadUniverse);
  renderUniverseTable();
}
async function loadUniverse(){
  document.body.classList.add('universe-mode');
  history.replaceState(null,'','/?view=universe');
  $$('.tab').forEach(function(b){b.classList.toggle('active',b.id==='universeTab');});
  var c=$('#content');
  c.innerHTML='<div class="muted">Universe 데이터를 불러오는 중...</div>';
  try{
    var x=await Promise.all([getJSON('/api/dashboard?market=US'),getJSON('/api/account'),loadAccountFx()]);
    universeState.us=x[0];universeState.account=x[1];universeState.fx=x[2];
    universeState.rows=buildUniverseRows(x[0],x[1],x[2]);
    renderUniverseView();
  }catch(e){
    c.innerHTML='<div class="notice error"><b>Universe 데이터를 불러오지 못했습니다.</b><div class="small">'+esc(e.message)+'</div></div>';
  }
}
'''

UNIVERSE_CSS=r'''
/* vNext.7.4.18 inline Universe view */
.universe-link{text-decoration:none}
.universe-mode .command-shell,.universe-mode .account{display:none}
.universe-mode .wrap>main{max-width:none}
.universe-view{max-width:1440px;margin:0 auto}
.universe-title{display:flex;justify-content:space-between;align-items:flex-end;gap:12px}
.universe-summary{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}
.u-kpi{background:#0d1729;border:1px solid #263654;border-radius:12px;padding:12px;display:flex;flex-direction:column}
.u-kpi span{font-size:9px;font-weight:900;letter-spacing:.08em;color:#7f91b1}
.u-kpi b{font-size:24px;line-height:1.1;margin-top:3px}
.u-kpi small{font-size:10px;color:#71819e;margin-top:2px}
.universe-controls{display:grid;grid-template-columns:minmax(220px,1fr) 170px 170px auto;gap:9px;align-items:end}
.universe-controls label{display:block;font-size:9px;font-weight:900;letter-spacing:.08em;color:#7f91b1;margin-bottom:5px}
.universe-controls input,.universe-controls select{width:100%;border:1px solid #2a3857;background:#0b1425;color:#e7edf9;border-radius:9px;padding:9px 10px;outline:none}
.universe-note{display:flex;gap:12px;align-items:flex-start;font-size:11px}
.universe-note b{white-space:nowrap}.universe-note span{color:#92a2bd}
.universe-legend{display:flex;gap:5px}
.universe-table-scroll{overflow:auto;max-height:calc(100vh - 350px);min-height:420px;border:1px solid #25304a;border-radius:10px}
.universe-table{width:100%;border-collapse:collapse;min-width:1080px;font-size:11px}
.universe-table th{position:sticky;top:0;z-index:4;background:#111a2d;color:#8798b8;text-align:left;padding:9px 10px;border-bottom:1px solid #2b3852;white-space:nowrap}
.universe-table td{padding:8px 10px;border-bottom:1px solid #1e2b42;white-space:nowrap}
.universe-table tbody tr:hover{background:#101c31}
.row-top6{background:rgba(60,116,191,.07)}
.row-held td:first-child{box-shadow:inset 3px 0 0 #61c983}
.rank-cell{font-weight:900;color:#aab7cc}.symbol-cell{font-size:12px}
.u-flag{display:inline-block;padding:2px 6px;border-radius:999px;font-size:9px;font-weight:900;background:#25304a;color:#b8c5da}
.u-flag.top6{background:#19345a;color:#aad1ff}.u-flag.held{background:#153424;color:#a7efbd}.u-flag.scored{background:#222d43;color:#9daac1}
.holding-cell{display:flex;flex-direction:column}.holding-cell small{font-size:9px;color:#7c8ca7}
.action{display:inline-block;font-size:10px;font-weight:900}.action.buy{color:#9fd3ff}.action.sell{color:#ff9e9e}.action.hold{color:#8fe3ab}.action.watch{color:#8798b8}
.action-detail{display:block;font-size:9px;color:#7585a2;margin-top:1px}
@media(max-width:900px){.universe-summary{grid-template-columns:repeat(3,1fr)}.universe-controls{grid-template-columns:1fr 1fr}.universe-controls .universe-search{grid-column:1/-1}}
@media(max-width:600px){.universe-summary{grid-template-columns:1fr 1fr}.universe-controls{grid-template-columns:1fr}.universe-controls .universe-search{grid-column:auto}.universe-table-scroll{max-height:none}.universe-note{display:block}.universe-note b{display:block;margin-bottom:5px}}
'''

def once(text,old,new,label):
    n=text.count(old)
    if n!=1:
        raise SystemExit(f"[FAIL] {label}: expected 1 got {n}")
    return text.replace(old,new,1)

def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: patch_investment_hub_v7418.py <source-root>")
    root=Path(sys.argv[1])
    ap=root/"app.js";cp=root/"style.css";ip=root/"index.html";hp=root/"api/health.js"
    for p in (ap,cp,ip,hp):
        if not p.exists(): raise SystemExit(f"[FAIL] missing {p}")

    app=ap.read_text(encoding="utf-8")
    css=cp.read_text(encoding="utf-8")
    idx=ip.read_text(encoding="utf-8")
    health=hp.read_text(encoding="utf-8")

    if BASE not in idx:
        raise SystemExit("[FAIL] v7.4.17 base missing")
    before=len(list((root/"api").rglob("*.js")))
    if before!=12:
        raise SystemExit(f"[FAIL] expected 12 API functions before patch, got {before}")

    us_tab='<button class="tab" data-m="US">미국장</button>'
    idx=once(
        idx,
        us_tab,
        us_tab+'\n      <button class="tab universe-link" id="universeTab" type="button">Universe</button>',
        "Universe nav"
    )

    app=once(
        app,
        "function renderGlobal(j){",
        UNIVERSE_JS+"\nfunction renderGlobal(j){",
        "Universe helpers"
    )
    app=once(
        app,
        "async function loadMarket(m){\n  const c=$('#content');c.innerHTML='<div class=\"muted\">데이터를 불러오는 중...</div>';",
        "async function loadMarket(m){\n  document.body.classList.remove('universe-mode');\n  if(new URLSearchParams(location.search).get('view')==='universe')history.replaceState(null,'',location.pathname);\n  const c=$('#content');c.innerHTML='<div class=\"muted\">데이터를 불러오는 중...</div>';",
        "leave Universe mode"
    )
    app=once(
        app,
        "$$('.tab').forEach(b=>b.addEventListener('click',()=>loadMarket(b.dataset.m)));\n$('#accountRefresh').addEventListener('click',loadAccount);\nloadAccount();loadCommandCenter();loadMarket('GLOBAL');",
        "$$('.tab[data-m]').forEach(b=>b.addEventListener('click',()=>loadMarket(b.dataset.m)));\n$('#universeTab').addEventListener('click',loadUniverse);\n$('#accountRefresh').addEventListener('click',loadAccount);\nloadAccount();loadCommandCenter();\nif(new URLSearchParams(location.search).get('view')==='universe')loadUniverse();else loadMarket('GLOBAL');",
        "Universe boot"
    )

    css=css.rstrip()+"\n\n"+UNIVERSE_CSS.strip()+"\n"
    idx=idx.replace(
        "vNext.7.4.17 · Command Center + Model Workspace",
        "vNext.7.4.18 · Command Center + Universe View"
    )
    idx=idx.replace(BASE,TARGET)
    health=health.replace(BASE,TARGET)

    after=len(list((root/"api").rglob("*.js")))
    if after!=12 or after!=before:
        raise SystemExit(f"[FAIL] API function count changed: {before}->{after}")

    for m in (
        "UNIVERSE_BASELINE_TOTAL=102",
        "function loadUniverse()",
        "US R5.1 UNIVERSE",
        "SELL PREVIEW",
        "var base=held?'TOP-UP':'BUY'",
        "label:fresh?base:base+' PREVIEW'",
        "/api/dashboard?market=US",
        "universeTab"
    ):
        if m not in app and m not in idx:
            raise SystemExit(f"[FAIL] Universe marker missing: {m}")

    ap.write_text(app,encoding="utf-8")
    cp.write_text(css,encoding="utf-8")
    ip.write_text(idx,encoding="utf-8")
    hp.write_text(health,encoding="utf-8")

    print("[PASS] vNext.7.4.18 inline Universe view")
    print("[PASS] URL /?view=universe")
    print("[PASS] current R5.1 scored universe = dynamic assets payload")
    print("[PASS] requested baseline 102 / unmapped gap displayed transparently")
    print("[PASS] search/filter/sort + holdings + next-action table")
    print("[PASS] API function count = 12")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
