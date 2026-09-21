
function siteNav(active){
  let items=[['MAIN','https://kalman-investment-hub-v2.vercel.app'],['KR','https://kalman-investment-hub-kr.vercel.app'],['US','https://kalman-investment-hub-us.vercel.app']];
  return '<nav class="site-nav" aria-label="Kalman market sites">'+items.map(([k,u])=>'<a class="site-nav-link '+(k===active?'active':'')+'" href="'+u+'">'+k+'</a>').join('')+'</nav>';
}

function todaySignalList(){
  let L=S?.payload?.source_payload?.ledger||{},h=L.top3_event_history||L.top3_event_tail||[],d=D(S?.data_as_of),m=new Map();
  for(let e of h){
    let ed=D(e.event_date||e.date),t=String(e.event_type||e.type||'').toUpperCase(),c=String(e.Code||e.code||'');
    if(ed!==d||!c||!['TOP3_ENTER','TOP3_REENTER','TOP3_EXIT'].includes(t))continue;
    m.set(c+'|'+t,{date:ed,type:t,code:c,name:e.Name||e.name||c,rank:N(e.momentum_rank),close:N(e.close)});
  }
  let p={TOP3_EXIT:0,TOP3_REENTER:1,TOP3_ENTER:2};
  return [...m.values()].sort((a,b)=>(p[a.type]??9)-(p[b.type]??9)||(a.rank??999)-(b.rank??999));
}
function compactSignalHtml(){
  let z=todaySignalList();
  if(!z.length)return '<section class="dailybox"><div class="sectiontitle"><b>오늘 Signal</b><span>'+E(D(S?.data_as_of))+'</span></div><div class="nosignal">변경 없음 · 기존 Top3 유지</div></section>';
  return '<section class="dailybox"><div class="sectiontitle"><b>오늘 Signal</b><span>'+E(D(S?.data_as_of))+'</span></div><div class="signalrows">'+z.map(x=>{
    let isExit=x.type==='TOP3_EXIT',label=isExit?'EXIT':x.type==='TOP3_REENTER'?'REENTRY':'NEW ENTRY',cls=isExit?'sigexit':'sigenter';
    return '<button class="signalrow pick" data-c="'+E(x.code)+'"><span class="signalbadge '+cls+'">'+label+'</span><span class="signalname"><b>'+E(x.name)+'</b><small>'+E(x.code)+'</small></span><span class="signalmeta">Rank #'+E(x.rank??'—')+'<small>'+P(x.close)+'</small></span></button>';
  }).join('')+'</div></section>';
}
function compactOpenHtml(op){
  return '<section class="dailybox"><div class="sectiontitle"><div><b>현재 OPEN</b><small>STRICT TOP3 · 신규진입 판단 분리</small></div><span class="badge">'+op.length+' OPEN</span></div><div class="positionrows">'+op.map(x=>{
    let ed=entryDecision(x),short=ed.label==='HOLD ONLY'?'HOLD':ed.label==='LATE ENTRY · CAUTION'?'CAUTION':ed.label;
    return '<button class="positionrow pick" data-c="'+E(x.code)+'"><span class="posrank">#'+x.rank+'</span><span class="posname"><b>'+E(x.name)+'</b><small>'+E(x.code)+' · '+E(x.entryDate)+' 진입</small></span><span class="posprice"><b>'+P(x.current)+'</b><small>'+P(x.entry)+' → 현재</small></span><span class="posret '+(N(x.ret)>=0?'pos':'neg')+'">'+PC(x.ret)+'</span><span class="posdecision '+ed.cls+'">'+E(short)+'</span></button>';
  }).join('')+'</div></section>';
}
function compactMarketTop3Html(s,j){
  let t=S?.payload?.top3||[];
  let score=N(s?.market_score);
  return '<section class="dailybox markettop3"><div class="sectiontitle"><div><b>현재 Top3 · 시장상태</b><small>'+E(s?.regime||'—')+' · '+E(s?.overall_action_label||'—')+'</small></div><span class="badge marketbadge">Market '+(score==null?'—':score.toFixed(1))+'</span></div><div class="top3rows">'+t.map((x,i)=>{
    let a=A.find(z=>String(z.code)===String(x.code))||x;
    return '<button class="top3row pick" data-c="'+E(x.code)+'"><span class="posrank">#'+E(x.momentum_rank??i+1)+'</span><span class="top3name"><b>'+E(x.name||a.name)+'</b><small>'+E(x.code)+' · '+E(x.market||a.market)+'</small></span><span class="top3price"><b>'+P(a.close)+'</b><small>현재가</small></span><span class="top3score"><b>Score '+(N(a.stock_score)==null?'—':N(a.stock_score).toFixed(1))+'</b><small>'+E(a.action_label||'—')+'</small></span></button>';
  }).join('')+'</div><div class="note">KR Momentum Core 기준 현재 상위 3종목 · 시장 상태와 종목 Rank를 한 화면에서 확인</div></section>';
}
function pulseNum(x){
  let v=N(x?.value);if(v==null)return '—';
  if(x.kind==='yield_pct')return v.toFixed(3)+'%';
  if(x.kind==='fx')return v.toLocaleString('ko-KR',{maximumFractionDigits:1});
  if(x.kind==='price')return String.fromCharCode(36)+v.toLocaleString('en-US',{maximumFractionDigits:2});
  return v.toLocaleString('ko-KR',{maximumFractionDigits:2});
}
function pulseDelta(x){
  let d=N(x?.change_abs),p=N(x?.change_pct);
  if(x?.kind==='yield_pct')return d==null?'—':(d>=0?'+':'')+(d*100).toFixed(1)+'bp';
  return p==null?'—':(p>=0?'+':'')+(p*100).toFixed(2)+'%';
}
function marketPulseHtml(){
  let z=K?.items||[];
  if(!z.length)return '<section class="pulsebar"><div class="pulseempty">Market Pulse · unavailable</div></section>';
  return '<section class="pulsebar" aria-label="KR market pulse">'+z.map(x=>'<div class="pulseitem"><span>'+E(x.label)+'</span><b>'+E(pulseNum(x))+'</b><small class="'+(N(x.change_abs)>=0?'pos':'neg')+'">'+E(pulseDelta(x))+'</small></div>').join('')+'<div class="pulsemeta">PUBLIC CONTEXT · '+E(K.status||'—')+' · 모델/매매 입력 아님</div></section>';
}
function compactTop5Html(){
  let z=perfTop5();
  return '<div class="ranklist">'+z.map((x,i)=>'<button class="rankitem '+(x.current?'pick':'')+'" '+(x.current?'data-c="'+E(x.code)+'"':'')+'><span class="rankno">'+(i+1)+'</span><span class="rankname"><b>'+E(x.name)+'</b><small>'+x.closed+'회 종료 · 승률 '+(x.winRate==null?'—':x.winRate.toFixed(0)+'%')+(x.open?' · OPEN '+PC(x.openRet):'')+'</small></span><b class="rankret '+(x.avg>=0?'pos':'neg')+'">'+PC(x.avg)+'</b></button>').join('')+'</div>';
}
function foldHtml(title,meta,body,extra=''){
  return '<details class="fold card"><summary><span><b>'+title+'</b>'+(meta?'<small>'+meta+'</small>':'')+'</span><span class="foldright">'+extra+'<span class="chev">⌄</span></span></summary><div class="foldbody">'+body+'</div></details>';
}
async function load(){
  let [r,k]=await Promise.all([fetch('/api/dashboard?market=KR',{cache:'no-store'}),fetch('/market-pulse?market=KR',{cache:'no-store'}).then(x=>x.ok?x.json():null).catch(()=>null)]),j=await r.json();
  K=k;
  if(!r.ok)return $('#m').innerHTML='<div class=card>LOAD FAILED</div>';
  S=j;let p=j.payload||{},s=p.summary||{};
  A=(p.assets||[]).sort((a,b)=>(N(a.momentum_rank)||999)-(N(b.momentum_rank)||999));
  let op=currentOpenList(),opm=new Map(op.map(x=>[String(x.code),entryDecision(x)])),sc=p?.source_payload?.strategy_compare,
      st=sc?.strict||{},bf=sc?.buffer||{};
  let strategyMeta=sc?'STRICT '+PC(st.avg_closed_return_pct)+' · BUFFER '+PC(bf.avg_closed_return_pct):'2026 YTD 병렬 비교',
      perfMeta='종료 사이클 산술평균 · '+perfTop5().length+'종목',
      universeMeta=A.length+'종목 · 헤더 정렬 가능';
  $('#m').innerHTML=`
    <section class="appbar">
      <div class="appbrand">KR Investment Hub</div>
      ${siteNav("KR")}
      <div class="appmarket"><b>${E(s.regime)}</b><span>Market ${N(s.market_score)?.toFixed(1)??'—'}</span><span>${E(s.overall_action_label)}</span><span class="badge ${j.effective_stale?'bad':''}">${j.effective_stale?'STALE':'FRESH'}</span></div>
      <small>${D(j.data_as_of)}</small>
    </section>
    ${marketPulseHtml()}
    ${compactSignalHtml()}
    ${compactOpenHtml(op)}
    ${compactMarketTop3Html(s,j)}
    <section class="searchcompact card">
      <div class="sw"><input id=q class=search placeholder="🔎 종목 검색 · 삼성전자, 005930, GS"><div id=sg class="sg hide"></div></div>
      <div id=d class="detailhost"></div>
    </section>
    ${foldHtml('전략 비교 · 2026 YTD',strategyMeta,strategyCompareHtml(),'<span class="taglab">RESEARCH</span>')}
    ${foldHtml('종료 성과 Top5',perfMeta,compactTop5Html())}
    ${foldHtml('KR Universe',universeMeta,universeHtml(opm))}
  `;
  bind();
}
