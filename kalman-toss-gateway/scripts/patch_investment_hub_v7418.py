from __future__ import annotations
import sys
from pathlib import Path

BASE="vNext.7.4.17"
TARGET="vNext.7.4.18"

UNIVERSE_HTML=r'''<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Kalman · US Universe</title>
  <link rel="stylesheet" href="/style.css">
  <link rel="stylesheet" href="/universe.css">
</head>
<body>
  <div class="wrap universe-wrap">
    <header class="product-head universe-head">
      <div>
        <a class="back-link" href="/">← KALMAN</a>
        <div class="brand-mark">US R5.1 UNIVERSE</div>
        <h1>Model Ranking Table</h1>
        <div class="muted">전체 후보 · 현재 R5.1 score · 보유/Top-6/예정 액션</div>
      </div>
      <div class="header-status">
        <span id="freshState" class="pill">DATA —</span>
        <a class="pill universe-home" href="/">COMMAND CENTER</a>
      </div>
    </header>

    <section class="universe-summary section" id="summary">
      <div class="muted">Universe 데이터를 불러오는 중...</div>
    </section>

    <section class="card universe-controls section">
      <div class="universe-search">
        <label for="search">Search</label>
        <input id="search" type="search" placeholder="GS, ORCL, NVDA...">
      </div>
      <div class="universe-filter">
        <label for="filter">Filter</label>
        <select id="filter">
          <option value="ALL">ALL</option>
          <option value="TOP6">TOP-6</option>
          <option value="HELD">HELD</option>
          <option value="ACTION">ACTION</option>
          <option value="WATCH">WATCH</option>
        </select>
      </div>
      <div class="universe-filter">
        <label for="sort">Sort</label>
        <select id="sort">
          <option value="RANK">Rank</option>
          <option value="SCORE">Score</option>
          <option value="SYMBOL">Symbol</option>
          <option value="WEIGHT">Weight</option>
        </select>
      </div>
      <button id="refresh" class="btn" type="button">새로고침</button>
    </section>

    <section class="card section universe-note">
      <b>Universe contract</b>
      <span>현재 Production R5.1 API는 93개 scored symbols를 반환합니다. 요청한 102개 baseline 중 나머지 9개는 심볼 identity가 현재 dashboard payload에 노출되지 않아 임의 생성하지 않습니다.</span>
    </section>

    <section class="card section universe-table-card">
      <div class="section-title">
        <div>
          <h3>US R5.1 Ranking</h3>
          <span id="tableMeta" class="small">—</span>
        </div>
        <div class="universe-legend">
          <span class="pill top6-pill">TOP-6</span>
          <span class="pill held-pill">HELD</span>
          <span class="pill action-pill">ACTION</span>
        </div>
      </div>
      <div class="universe-table-scroll">
        <table class="universe-table">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Symbol</th>
              <th>Status</th>
              <th>Score</th>
              <th>Reference</th>
              <th>4h Target</th>
              <th>Δ Target</th>
              <th>Weight</th>
              <th>Holding</th>
              <th>Next Action</th>
            </tr>
          </thead>
          <tbody id="rows">
            <tr><td colspan="10" class="muted">Loading...</td></tr>
          </tbody>
        </table>
      </div>
    </section>
    <footer>vNext.7.4.18 · US Universe · Read/Plan View</footer>
  </div>
  <script src="/universe.js"></script>
</body>
</html>
'''

UNIVERSE_JS=r'''const BASELINE_TOTAL=102;
const FRESH_MINUTES=90;
const TOP_COUNT=6;
const TARGET_KRW=5000;
const MIN_ORDER_KRW=1000;

const $=s=>document.querySelector(s);
const state={rows:[],filtered:[],us:null,account:null,fx:null};

function esc(v){return String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function n(v){const x=Number(v);return Number.isFinite(x)?x:null}
function fmt(v,d=2){const x=n(v);return x==null?'—':x.toLocaleString('en-US',{maximumFractionDigits:d,minimumFractionDigits:d})}
function usd(v){const x=n(v);return x==null?'—':'$'+x.toLocaleString('en-US',{maximumFractionDigits:2,minimumFractionDigits:2})}
function krw(v){const x=n(v);return x==null?'—':'₩'+Math.round(x).toLocaleString('ko-KR')}
function pct(v,d=2){const x=n(v);return x==null?'—':(x*100).toFixed(d)+'%'}
function time(v){if(!v)return'—';const d=new Date(v);return Number.isNaN(d.getTime())?'—':d.toLocaleString('ko-KR',{timeZone:'Asia/Seoul',hour12:false})}
async function getJSON(url){const r=await fetch(url,{cache:'no-store'});const j=await r.json();if(!r.ok)throw new Error(j?.error||('HTTP '+r.status));return j}
function holdingItems(a){return a?.holdings?.result?.items||[]}
function mvUsd(h){return n(h?.marketValue?.amountAfterCost??h?.marketValue?.amount)||0}
function freshInfo(us){const t=Date.parse(us?.data_as_of||'');const age=Number.isFinite(t)?Math.max(0,(Date.now()-t)/60000):Infinity;return{fresh:Number.isFinite(age)&&age<=FRESH_MINUTES,age}}
async function loadFx(){
  try{
    const r=await fetch('https://open.er-api.com/v6/latest/USD',{cache:'no-store'});
    const j=await r.json();const x=n(j?.rates?.KRW);if(x)return x;
  }catch(_){}
  try{
    const r=await fetch('https://api.frankfurter.dev/v2/rate/usd/krw',{cache:'no-store'});
    const j=await r.json();const x=n(j?.rate);if(x)return x;
  }catch(_){}
  return null;
}
function flag(label,kind=''){return '<span class="u-flag '+kind+'">'+esc(label)+'</span>'}
function actionFor(asset,held,fx,fresh){
  const rank=Number(asset.rank||999);
  const isTop=rank<=TOP_COUNT;
  const currentKrw=held&&fx?mvUsd(held)*fx:0;
  const gap=Math.max(0,TARGET_KRW-currentKrw);
  if(isTop){
    if(held&&gap<MIN_ORDER_KRW)return{label:'HOLD',kind:'hold',detail:'TARGET #'+rank};
    const base=held?'TOP-UP':'BUY';
    return{
      label:fresh?base:base+' PREVIEW',
      kind:'buy',
      detail:(gap>=MIN_ORDER_KRW?krw(Math.min(TARGET_KRW,gap))+' · ':'')+'TARGET #'+rank
    };
  }
  if(held)return{label:fresh?'SELL':'SELL PREVIEW',kind:'sell',detail:'NOT IN TOP-6'};
  return{label:'WATCH',kind:'watch',detail:'RANK #'+rank};
}
function buildRows(){
  const assets=state.us?.payload?.assets||state.us?.payload?.top3||[];
  const heldMap=new Map(holdingItems(state.account).map(h=>[String(h.symbol||'').toUpperCase(),h]));
  const fi=freshInfo(state.us);
  state.rows=assets.map(a=>{
    const symbol=String(a.symbol||'').toUpperCase();
    const held=heldMap.get(symbol)||null;
    const action=actionFor(a,held,state.fx,fi.fresh);
    const ref=n(a.reference_price),target=n(a.target_price_4h);
    return{
      ...a,symbol,held,action,
      delta:(ref&&target)?target/ref-1:null,
      top6:Number(a.rank)<=TOP_COUNT
    };
  });
  render();
}
function summary(){
  const fi=freshInfo(state.us);
  const scored=state.rows.length;
  const held=state.rows.filter(x=>x.held).length;
  const actions=state.rows.filter(x=>x.action.kind==='buy'||x.action.kind==='sell').length;
  const unmapped=Math.max(0,BASELINE_TOTAL-scored);
  $('#summary').innerHTML=[
    ['BASELINE',BASELINE_TOTAL,'requested universe'],
    ['R5.1 SCORED',scored,'current contract'],
    ['UNMAPPED',unmapped,'outside current payload'],
    ['HELD',held,'US positions'],
    ['ACTION',actions,fi.fresh?'live-plan eligible':'preview only']
  ].map(x=>'<div class="u-kpi"><span>'+x[0]+'</span><b>'+x[1]+'</b><small>'+x[2]+'</small></div>').join('');
  const pill=$('#freshState');
  pill.className='pill '+(fi.fresh?'ok':'warn');
  pill.textContent=fi.fresh?'R5.1 FRESH':'R5.1 PREVIEW';
}
function applyFilter(rows){
  const q=$('#search').value.trim().toUpperCase();
  const f=$('#filter').value;
  let out=rows.filter(x=>!q||x.symbol.includes(q));
  if(f==='TOP6')out=out.filter(x=>x.top6);
  if(f==='HELD')out=out.filter(x=>x.held);
  if(f==='ACTION')out=out.filter(x=>['buy','sell','hold'].includes(x.action.kind));
  if(f==='WATCH')out=out.filter(x=>x.action.kind==='watch');
  const sort=$('#sort').value;
  out.sort((a,b)=>{
    if(sort==='SCORE')return (n(b.model_score)||-Infinity)-(n(a.model_score)||-Infinity);
    if(sort==='SYMBOL')return a.symbol.localeCompare(b.symbol);
    if(sort==='WEIGHT')return (n(b.position_weight_r4_vol_target)||0)-(n(a.position_weight_r4_vol_target)||0);
    return Number(a.rank||999)-Number(b.rank||999);
  });
  return out;
}
function rowHtml(x){
  const status=[
    x.top6?flag('TOP-6','top6'):null,
    x.held?flag('HELD','held'):null
  ].filter(Boolean).join(' ')||flag('SCORED','scored');
  const hold=x.held
    ?'<b>'+usd(mvUsd(x.held))+'</b><small>'+esc(x.held.quantity||'')+' sh</small>'
    :'<span class="muted">—</span>';
  return '<tr class="'+(x.top6?'row-top6 ':'')+(x.held?'row-held ':'')+'">'+
    '<td class="rank-cell">'+esc(x.rank)+'</td>'+
    '<td><b class="symbol-cell">'+esc(x.symbol)+'</b></td>'+
    '<td>'+status+'</td>'+
    '<td><b>'+fmt((n(x.model_score)||0)*10000,2)+' bp</b></td>'+
    '<td>'+usd(x.reference_price)+'</td>'+
    '<td>'+usd(x.target_price_4h)+'</td>'+
    '<td class="'+((n(x.delta)||0)>=0?'good':'bad')+'">'+pct(x.delta,3)+'</td>'+
    '<td>'+pct(x.position_weight_r4_vol_target,1)+'</td>'+
    '<td class="holding-cell">'+hold+'</td>'+
    '<td><span class="action '+x.action.kind+'">'+esc(x.action.label)+'</span><small class="action-detail">'+esc(x.action.detail)+'</small></td>'+
  '</tr>';
}
function render(){
  summary();
  const out=applyFilter(state.rows);
  state.filtered=out;
  $('#rows').innerHTML=out.length?out.map(rowHtml).join(''):'<tr><td colspan="10" class="muted">조건에 맞는 종목이 없습니다.</td></tr>';
  const fi=freshInfo(state.us);
  $('#tableMeta').textContent=out.length+' / '+state.rows.length+' rows · data '+time(state.us?.data_as_of)+' · '+(Number.isFinite(fi.age)?Math.round(fi.age)+'m old':'age unknown');
}
async function load(){
  const btn=$('#refresh');btn.disabled=true;btn.textContent='불러오는 중...';
  try{
    const [us,account,fx]=await Promise.all([
      getJSON('/api/dashboard?market=US'),
      getJSON('/api/account'),
      loadFx()
    ]);
    state.us=us;state.account=account;state.fx=fx;
    buildRows();
  }catch(e){
    $('#rows').innerHTML='<tr><td colspan="10" class="bad">'+esc(e.message)+'</td></tr>';
  }finally{btn.disabled=false;btn.textContent='새로고침'}
}
['search','filter','sort'].forEach(id=>$('#'+id).addEventListener(id==='search'?'input':'change',()=>render()));
$('#refresh').addEventListener('click',load);
load();
'''

UNIVERSE_CSS=r'''.universe-wrap{max-width:1440px}
.back-link{display:inline-block;color:#91a6cc;text-decoration:none;font-size:11px;font-weight:900;letter-spacing:.08em;margin-bottom:7px}
.universe-home{text-decoration:none;color:#cbd5e1}
.universe-summary{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}
.u-kpi{background:#0d1729;border:1px solid #263654;border-radius:12px;padding:12px;display:flex;flex-direction:column}
.u-kpi span{font-size:9px;font-weight:900;letter-spacing:.08em;color:#7f91b1}.u-kpi b{font-size:24px;line-height:1.1;margin-top:3px}.u-kpi small{font-size:10px;color:#71819e;margin-top:2px}
.universe-controls{display:grid;grid-template-columns:minmax(220px,1fr) 170px 170px auto;gap:9px;align-items:end}
.universe-controls label{display:block;font-size:9px;font-weight:900;letter-spacing:.08em;color:#7f91b1;margin-bottom:5px}
.universe-controls input,.universe-controls select{width:100%;border:1px solid #2a3857;background:#0b1425;color:#e7edf9;border-radius:9px;padding:9px 10px;outline:none}
.universe-note{display:flex;gap:12px;align-items:flex-start;font-size:11px}.universe-note b{white-space:nowrap}.universe-note span{color:#92a2bd}
.universe-legend{display:flex;gap:5px}.top6-pill{background:#19345a;color:#aad1ff}.held-pill{background:#153424;color:#a7efbd}.action-pill{background:#3a2c16;color:#ffe3a7}
.universe-table-scroll{overflow:auto;max-height:calc(100vh - 330px);min-height:420px;border:1px solid #25304a;border-radius:10px}
.universe-table{width:100%;border-collapse:collapse;min-width:1080px;font-size:11px}
.universe-table th{position:sticky;top:0;z-index:4;background:#111a2d;color:#8798b8;text-align:left;padding:9px 10px;border-bottom:1px solid #2b3852;white-space:nowrap}
.universe-table td{padding:8px 10px;border-bottom:1px solid #1e2b42;white-space:nowrap}.universe-table tbody tr:hover{background:#101c31}
.row-top6{background:rgba(60,116,191,.07)}.row-held td:first-child{box-shadow:inset 3px 0 0 #61c983}
.rank-cell{font-weight:900;color:#aab7cc}.symbol-cell{font-size:12px}
.u-flag{display:inline-block;padding:2px 6px;border-radius:999px;font-size:9px;font-weight:900;background:#25304a;color:#b8c5da}.u-flag.top6{background:#19345a;color:#aad1ff}.u-flag.held{background:#153424;color:#a7efbd}.u-flag.scored{background:#222d43;color:#9daac1}
.holding-cell{display:flex;flex-direction:column}.holding-cell small{font-size:9px;color:#7c8ca7}
.action{display:inline-block;font-size:10px;font-weight:900}.action.buy{color:#9fd3ff}.action.sell{color:#ff9e9e}.action.hold{color:#8fe3ab}.action.watch{color:#8798b8}.action-detail{display:block;font-size:9px;color:#7585a2;margin-top:1px}
@media(max-width:900px){.universe-summary{grid-template-columns:repeat(3,1fr)}.universe-controls{grid-template-columns:1fr 1fr}.universe-controls .universe-search{grid-column:1/-1}}
@media(max-width:600px){.universe-summary{grid-template-columns:1fr 1fr}.universe-controls{grid-template-columns:1fr}.universe-controls .universe-search{grid-column:auto}.universe-table-scroll{max-height:none}.universe-note{display:block}.universe-note b{display:block;margin-bottom:5px}}
'''

def once(text,old,new,label):
    n=text.count(old)
    if n!=1: raise SystemExit(f"[FAIL] {label}: expected 1 got {n}")
    return text.replace(old,new,1)

def main():
    if len(sys.argv)!=2: raise SystemExit("usage: patch_investment_hub_v7418.py <source-root>")
    root=Path(sys.argv[1]); ap=root/"app.js";cp=root/"style.css";ip=root/"index.html";hp=root/"api/health.js"
    for p in (ap,cp,ip,hp):
        if not p.exists(): raise SystemExit(f"[FAIL] missing {p}")
    idx=ip.read_text(encoding="utf-8");health=hp.read_text(encoding="utf-8")
    if BASE not in idx: raise SystemExit("[FAIL] v7.4.17 base missing")
    before=len(list((root/"api").rglob("*.js")))
    if before!=12: raise SystemExit(f"[FAIL] expected 12 API functions before patch, got {before}")

    us_tab='<button class="tab" data-m="US">미국장</button>'
    idx=once(
        idx,us_tab,
        us_tab+'\n      <a class="tab universe-link" href="/universe.html">Universe</a>',
        "Universe nav"
    )
    idx=idx.replace(BASE,TARGET)
    idx=idx.replace(
        "vNext.7.4.17 · Command Center + Model Workspace",
        "vNext.7.4.18 · Command Center + Universe Table"
    )
    health=health.replace(BASE,TARGET)

    (root/"universe.html").write_text(UNIVERSE_HTML,encoding="utf-8")
    (root/"universe.js").write_text(UNIVERSE_JS,encoding="utf-8")
    (root/"universe.css").write_text(UNIVERSE_CSS,encoding="utf-8")

    after=len(list((root/"api").rglob("*.js")))
    if after!=12 or after!=before:
        raise SystemExit(f"[FAIL] API function count changed: {before}->{after}")
    for p in ("universe.html","universe.js","universe.css"):
        if not (root/p).exists(): raise SystemExit(f"[FAIL] missing generated {p}")
    for m in ("BASELINE_TOTAL=102","R5.1 SCORED","SELL PREVIEW","TOP-UP PREVIEW","/api/dashboard?market=US"):
        if m not in UNIVERSE_JS and m not in UNIVERSE_HTML:
            raise SystemExit(f"[FAIL] Universe marker missing: {m}")

    ip.write_text(idx,encoding="utf-8")
    hp.write_text(health,encoding="utf-8")
    print("[PASS] vNext.7.4.18 Universe page")
    print("[PASS] current R5.1 scored universe = dynamic assets payload")
    print("[PASS] requested baseline 102 / unmapped gap displayed transparently")
    print("[PASS] search/filter/sort + holdings + next-action table")
    print("[PASS] API function count = 12")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
