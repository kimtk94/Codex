const $=s=>document.querySelector(s),E=x=>String(x??'').replace(/[&<>\"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[m])),N=x=>x===null||x===undefined||x===''?null:(Number.isFinite(Number(x))?Number(x):null);
const USD=x=>N(x)==null?'—':'$'+N(x).toLocaleString(undefined,{minimumFractionDigits:N(x)<100?2:0,maximumFractionDigits:2});
const PCT=x=>N(x)==null?'—':(N(x)>=0?'+':'')+(N(x)*100).toFixed(4)+'%';
const DT=x=>x?String(x).replace('T',' ').replace('.000Z',' UTC').slice(0,22):'—';
let S=null,A=[],C=null,K=null;
const NYSE=new Set(['ACN','ORCL','UBER','GE','ABBV','ABT','AMT','BA','BAC','BMY','C','CAT','COF','CVS','CVX','DE','DHR','DIS','EMR','GM','GS','JNJ','JPM','LLY','MDT','MS','PFE','TMO','USB','WFC','CRM','AXP','BRK-B','CL','COP','DUK','FDX','HD','IBM','KO','LOW','MA','MCD','MMM','MO','MRK','NEE','NKE','PG','PM','RTX','SCHW','SO','SPG','T','UNH','UNP','UPS','V','VZ','XOM']);
function tvUS(s){return (NYSE.has(String(s||'').toUpperCase())?'NYSE:':'NASDAQ:')+String(s||'').toUpperCase()}
function tvChart(symbol){let tv=tvUS(symbol),u='https://s.tradingview.com/widgetembed/?symbol='+encodeURIComponent(tv)+'&interval=D&hidesidetoolbar=0&symboledit=0&saveimage=0&toolbarbg=f1f3f6&studies=%5B%5D&theme=dark&style=1&timezone=Etc%2FUTC&withdateranges=1&hideideas=1';return '<div class="charthead"><b>가격 차트</b><small>'+E(tv)+' · Daily · TradingView</small></div><div class="chartbox"><iframe title="'+E(symbol)+' price chart" src="'+u+'" loading="lazy" referrerpolicy="origin" allowtransparency="true" scrolling="no"></iframe></div>'}
function pulseNum(x){
  let v=N(x?.value);if(v==null)return '—';
  if(x.kind==='yield_pct')return v.toFixed(3)+'%';
  if(x.kind==='spread_bps')return (v>=0?'+':'')+v.toFixed(1)+'bp';
  if(x.kind==='fx')return v.toLocaleString(undefined,{maximumFractionDigits:1});
  if(x.kind==='price')return String.fromCharCode(36)+v.toLocaleString(undefined,{maximumFractionDigits:2});
  return v.toLocaleString(undefined,{maximumFractionDigits:2});
}
function pulseDelta(x){
  let d=N(x?.change_abs),p=N(x?.change_pct);
  if(x?.kind==='yield_pct')return d==null?'—':(d>=0?'+':'')+(d*100).toFixed(1)+'bp';
  if(x?.kind==='spread_bps')return d==null?'—':'Δ '+(d>=0?'+':'')+d.toFixed(1)+'bp';
  return p==null?'—':(p>=0?'+':'')+(p*100).toFixed(2)+'%';
}
function marketPulseHtml(){
  let z=K?.items||[];
  if(!z.length)return '<section class="pulsebar"><div class="pulseempty">Market Pulse · unavailable</div></section>';
  return '<section class="pulsebar" aria-label="US market pulse">'+z.map(x=>'<div class="pulseitem"><span>'+E(x.label)+'</span><b>'+E(pulseNum(x))+'</b><small class="'+(N(x.change_abs)>=0?'pos':'neg')+'">'+E(pulseDelta(x))+'</small></div>').join('')+'<div class="pulsemeta">REGIME STRIP · '+E(K.status||'—')+' · not a model/trade input</div></section>';
}
function currentTop3(){return S?.payload?.top3||[]}
function top3Html(){return '<section class="dailybox"><div class="sectiontitle"><div><b>현재 TOP3 · MODEL</b><small>4H relative-return ranking · Trade OFF</small></div><span class="badge info">TOP 3</span></div><div class="rows">'+currentTop3().map(x=>'<button class="rowbtn pick" data-s="'+E(x.symbol)+'"><span class="rank">#'+E(x.rank)+'</span><span class="name"><b>'+E(x.symbol)+'</b><small>Universe '+E(x.universe_size)+' · R5.1 HGB</small></span><span class="metric price"><b>'+USD(x.reference_price)+'</b><small>reference</small></span><span class="metric target"><b>'+USD(x.target_price_4h)+'</b><small>4H target</small></span><span class="alpha">'+PCT(x.model_score)+'</span><span class="tag">TOP PICK</span></button>').join('')+'</div></section>'}
function modelSignalHtml(){let t=S?.payload?.source_payload?.today_selector||{};return '<section class="dailybox"><div class="sectiontitle"><div><b>이번 Model Signal</b><small>'+E(t.as_of_utc||S?.data_as_of)+'</small></div><span class="badge">'+E(t.evidence_confidence||'—')+'</span></div><div class="signalgrid"><div class="sig"><span>Selected</span><b>'+E(t.selected_symbol||'—')+'</b></div><div class="sig"><span>4H target α</span><b class="pos">'+PCT(t.target_relative_return_4h)+'</b></div><div class="sig"><span>Risk band</span><b>'+USD(t.risk_band_low_4h)+' – '+USD(t.risk_band_high_4h)+'</b></div><div class="sig"><span>Observed hit rate</span><b>'+(N(t.observed_hit_rate)==null?'—':(N(t.observed_hit_rate)*100).toFixed(1)+'%')+'</b></div></div><div class="note">model_score는 상승확률이 아니라 universe median 대비 4시간 상대수익 예측값입니다.</div></section>'}
function detailHtml(x){if(!x)return'';return '<div class="detail"><div class="sectiontitle"><div><b>'+E(x.symbol)+'</b><small>Rank #'+E(x.rank)+' / '+E(x.universe_size)+'</small></div><span class="badge info">MODEL</span></div><div class="mini"><div><span>Reference</span><b>'+USD(x.reference_price)+'</b></div><div><span>4H Target</span><b>'+USD(x.target_price_4h)+'</b></div><div><span>Relative α</span><b class="pos">'+PCT(x.model_score)+'</b></div><div><span>Vol-target weight</span><b>'+(N(x.position_weight_r4_vol_target)==null?'—':(N(x.position_weight_r4_vol_target)*100).toFixed(1)+'%')+'</b></div></div>'+tvChart(x.symbol)+'<div class="note">차트는 TradingView 시장가격, 모델 Rank/Reference/4H Target은 Investment Hub snapshot 기준입니다. 두 데이터의 기준시각이 다를 수 있습니다.</div></div>'}
function universe(){return '<div class="tw"><table><thead><tr><th>Rank</th><th>Symbol</th><th>Reference</th><th>4H Target</th><th>Model α</th><th>Weight</th></tr></thead><tbody>'+A.map(x=>'<tr class="pick" data-s="'+E(x.symbol)+'"><td>#'+E(x.rank)+'</td><td><b>'+E(x.symbol)+'</b></td><td>'+USD(x.reference_price)+'</td><td>'+USD(x.target_price_4h)+'</td><td class="'+(N(x.model_score)>=0?'pos':'neg')+'">'+PCT(x.model_score)+'</td><td>'+(N(x.position_weight_r4_vol_target)==null?'—':(N(x.position_weight_r4_vol_target)*100).toFixed(1)+'%')+'</td></tr>').join('')+'</tbody></table></div>'}
function fold(title,meta,body){return '<details class="fold card"><summary><span><b>'+title+'</b><small>'+meta+'</small></span><span>⌄</span></summary><div class="foldbody">'+body+'</div></details>'}

const PCT2=x=>N(x)==null?'—':(N(x)>=0?'+':'')+(N(x)*100).toFixed(2)+'%';
function siteNav(active){
  let items=[['MAIN','https://kalman-investment-hub-v2.vercel.app'],['KR','https://kalman-investment-hub-kr.vercel.app'],['US','https://kalman-investment-hub-us.vercel.app']];
  return '<nav class="site-nav" aria-label="Kalman market sites">'+items.map(([k,u])=>'<a class="site-nav-link '+(k===active?'active':'')+'" href="'+u+'">'+k+'</a>').join('')+'</nav>';
}
function benchmarkHtml(){
  let b=C?.benchmarks||{},t1=b.top1||{},t6=b.top6||{};
  if(!t1.snapshots&&!t6.snapshots)return '';
  const card=(label,x)=>'<div class="benchcard"><div class="benchlabel">'+label+'</div><b class="'+(N(x.compounded)>=0?'pos':'neg')+'">'+PCT2(x.compounded)+'</b><small>'+E(x.snapshots||0)+' snapshots · avg '+PCT2(x.avg_net)+' · σ '+PCT2(x.std_net)+'</small><small>'+E(String(x.first_as_of||'').slice(0,10))+' → '+E(String(x.last_as_of||'').slice(0,10))+'</small></div>';
  return '<section class="dailybox benchmarkbox"><div class="sectiontitle"><div><b>Research Benchmark · TOP-1 vs TOP-6</b><small>4-bar · 10bp · research tracking only</small></div><span class="badge info">BENCHMARK</span></div><div class="benchgrid">'+card('TOP-1',t1)+card('TOP-6 equal',t6)+'</div><div class="note">벤치마크는 연구용 관측치이며 실제 주문/체결 성과가 아닙니다.</div></section>';
}
function ledgerHtml(){
  let a=S?.payload?.source_payload?.r5_shadow_ledger?.annual_2026||{},r=a.reconstructed?.summary||{},f=a.forward?.summary||{};
  if(!r.trade_count&&!f.trade_count)return '<div class="note">R5.1 annual ledger가 아직 없습니다.</div>';
  const box=(title,x,kind)=>'<div class="ledgercard"><div class="ledgerhead"><b>'+title+'</b><span class="badge '+(kind==='forward'?'info':'')+'">'+(kind==='forward'?'PROSPECTIVE':'REPLAY')+'</span></div><div class="ledgerkpis"><div><span>Trades</span><b>'+E(x.trade_count??'—')+'</b></div><div><span>Closed</span><b>'+E(x.closed_count??'—')+'</b></div><div><span>Compound</span><b class="'+(N(x.closed_compound_return_pct)>=0?'pos':'neg')+'">'+PCT2(x.closed_compound_return_pct)+'</b></div><div><span>Mean / trade</span><b class="'+(N(x.closed_mean_return_pct)>=0?'pos':'neg')+'">'+PCT2(x.closed_mean_return_pct)+'</b></div></div><small>'+E(DT(x.first_entry))+' → '+E(DT(x.last_event))+(x.open_symbols?.length?' · OPEN '+E(x.open_symbols.join(', ')):'')+'</small></div>';
  return '<div class="ledgergrid">'+box('RECONSTRUCTED · 2026',r,'replay')+box('FORWARD SHADOW',f,'forward')+'</div><div class="note">'+E(a.warning||'RECONSTRUCTED는 replay, FORWARD는 prospective SHADOW입니다.')+'</div>';
}
function forwardTradesHtml(){
  let a=S?.payload?.source_payload?.r5_shadow_ledger?.annual_2026||{},z=(a.forward?.trades||[]).slice(-12).reverse();
  if(!z.length)return '<div class="note">Forward trade가 아직 없습니다.</div>';
  return '<div class="tw"><table class="tinytable"><thead><tr><th>Status</th><th>Symbol</th><th>Entry</th><th>Exit</th><th>Net return</th></tr></thead><tbody>'+z.map(t=>'<tr><td><b>'+E(t.status||'—')+'</b></td><td><b>'+E(t.symbol||'—')+'</b></td><td>'+E(DT(t.entry_time))+'<br><small>'+USD(t.entry_price)+'</small></td><td>'+(t.exit_time?E(DT(t.exit_time))+'<br><small>'+USD(t.exit_price)+'</small>':'—')+'</td><td class="'+(N(t.return_pct)>=0?'pos':'neg')+'">'+PCT2(t.return_pct)+'</td></tr>').join('')+'</tbody></table></div>';
}

function performanceHtml(){
  let a=S?.payload?.source_payload?.r5_shadow_ledger?.annual_2026||{},r=a.reconstructed?.summary||{};
  if(!r.trade_count)return '';
  return '<section class="dailybox performancebox"><div class="sectiontitle"><div><b>R5.1 2026 성과 · RECONSTRUCTED</b><small>historical replay · 실제 주문/체결 성과와 분리</small></div><span class="badge replaybadge">REPLAY</span></div><div class="perfgrid"><div class="perfkpi"><span>Trades</span><b>'+E(r.trade_count??'—')+'</b><small>Closed '+E(r.closed_count??'—')+'</small></div><div class="perfkpi"><span>Mean / trade</span><b class="'+(N(r.closed_mean_return_pct)>=0?'pos':'neg')+'">'+PCT2(r.closed_mean_return_pct)+'</b><small>position-weighted net10</small></div><div class="perfkpi hero"><span>Compounded</span><b class="'+(N(r.closed_compound_return_pct)>=0?'pos':'neg')+'">'+PCT2(r.closed_compound_return_pct)+'</b><small>'+E(String(r.first_entry||'').slice(0,10))+' → '+E(String(r.last_event||'').slice(0,10))+'</small></div><div class="perfkpi"><span>Open</span><b>'+E(r.open_count??0)+'</b><small>'+E((r.open_symbols||[]).join(', ')||'없음')+'</small></div></div><div class="note strongnote">RECONSTRUCTED는 과거 데이터 replay입니다. 실거래 수익률이나 미래 성과로 해석하지 않습니다.</div></section>';
}
function forwardShadowHtml(){
  let a=S?.payload?.source_payload?.r5_shadow_ledger?.annual_2026||{},f=a.forward?.summary||{},z=(a.forward?.trades||[]).slice(-3).reverse();
  if(!f.trade_count)return '';
  return '<section class="dailybox forwardbox"><div class="sectiontitle"><div><b>Forward SHADOW · prospective</b><small>실시간 이후 추적 · execution=false</small></div><span class="badge info">SHADOW</span></div><div class="forwardgrid"><div><span>Trades</span><b>'+E(f.trade_count??'—')+'</b></div><div><span>Closed</span><b>'+E(f.closed_count??'—')+'</b></div><div><span>Open</span><b>'+E(f.open_count??0)+'</b><small>'+E((f.open_symbols||[]).join(', ')||'없음')+'</small></div><div><span>Compound</span><b class="'+(N(f.closed_compound_return_pct)>=0?'pos':'neg')+'">'+PCT2(f.closed_compound_return_pct)+'</b></div></div><div class="forwardrecent">'+z.map(t=>'<div class="forwardrow"><span class="status '+(t.status==='OPEN'?'open':'')+'">'+E(t.status||'—')+'</span><b>'+E(t.symbol||'—')+'</b><span>'+E(String(t.entry_time||'').slice(5,16).replace('T',' '))+'</span><strong class="'+(N(t.return_pct)>=0?'pos':'neg')+'">'+PCT2(t.return_pct)+'</strong></div>').join('')+'</div><div class="note">Forward SHADOW는 prospective 연구 추적이며 실제 주문을 실행하지 않습니다.</div></section>';
}
function bind(){document.addEventListener('click',e=>{let b=e.target.closest('[data-s]');if(b)select(b.dataset.s)});let q=$('#q'),sg=$('#sg');q?.addEventListener('input',()=>{let v=q.value.trim().toUpperCase();if(!v){sg.classList.add('hide');return}let z=A.filter(x=>x.symbol.includes(v)).slice(0,12);sg.innerHTML=z.map(x=>'<button data-s="'+E(x.symbol)+'"><b>'+E(x.symbol)+'</b><span>#'+E(x.rank)+' · '+USD(x.reference_price)+'</span></button>').join('');sg.classList.toggle('hide',!z.length)})}
function select(s){let x=A.find(z=>z.symbol===s);if(!x)return;$('#d').innerHTML=detailHtml(x);$('#q').value=s;$('#sg').classList.add('hide');$('#d').scrollIntoView({behavior:'smooth',block:'nearest'})}
async function load(){
  let [r,cr,kr]=await Promise.all([
    fetch('/api/dashboard?market=US',{cache:'no-store'}),
    fetch('/api/assets?view=control',{cache:'no-store'}),
    fetch('/market-pulse?market=US',{cache:'no-store'}).then(x=>x.ok?x.json():null).catch(()=>null)
  ]);
  let j=await r.json(),c=await cr.json();
  if(!r.ok){$('#m').innerHTML='<div class="card">LOAD FAILED</div>';return}
  S=j;C=cr.ok?c:null;K=kr;
  A=(j.payload?.assets||[]).sort((a,b)=>(a.rank??999)-(b.rank??999));
  let sm=j.payload?.summary||{},annual=j.payload?.source_payload?.r5_shadow_ledger?.annual_2026||{},fwd=annual.forward?.summary||{};
  $('#m').innerHTML=
    '<section class="appbar"><div class="appbrand">US Investment Hub</div>'+siteNav('US')+
    '<div class="appmarket"><b>'+E(sm.market_risk||'US')+'</b><span>'+E(j.model_version)+'</span><span class="badge '+(j.effective_stale?'bad':'')+'">'+(j.effective_stale?'STALE':'FRESH')+'</span></div><small>'+DT(j.data_as_of)+'</small></section>'+
    marketPulseHtml()+top3Html()+modelSignalHtml()+performanceHtml()+benchmarkHtml()+forwardShadowHtml()+
    '<section class="card"><div class="sw"><input id="q" class="search" placeholder="🔎 US ticker 검색 · NVDA, ORCL, AAPL"><div id="sg" class="sg hide"></div></div><div id="d"></div></section>'+
    fold('R5.1 2026 Ledger','replay + prospective 상세',ledgerHtml()+forwardTradesHtml())+
    fold('Model Context','R5.1_BASE_HGB · 4H relative-return','<div class="note">Primary lineage: '+E(sm.primary_lineage)+' · Evidence: '+E(sm.evidence_confidence)+' · Trade enabled: false</div>')+
    fold('US Universe',A.length+' stocks · rank order',universe());
  bind();
}
load().catch(e=>{$('#m').innerHTML='<div class="card">LOAD FAILED · '+E(e.message)+'</div>'});