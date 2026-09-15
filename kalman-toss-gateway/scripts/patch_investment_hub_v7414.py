from __future__ import annotations

import sys
from pathlib import Path

BASE_VERSION = "vNext.7.4.13"
TARGET_VERSION = "vNext.7.4.14"


def replace_block(text: str, start_marker: str, end_marker: str, new_block: str, label: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        raise SystemExit(f"[FAIL] {label}: start marker missing")
    end = text.find(end_marker, start + len(start_marker))
    if end < 0:
        raise SystemExit(f"[FAIL] {label}: end marker missing")
    if text.find(start_marker, start + len(start_marker)) >= 0:
        raise SystemExit(f"[FAIL] {label}: duplicate start marker")
    return text[:start] + new_block.rstrip() + "\n" + text[end + 1:]


US_CHART = r'''async function usShadowSignalChart(marketSnapshot){
  const src=marketSnapshot?.payload?.source_payload||{};
  const ledger=src.r5_shadow_ledger||{};
  const annual=ledger.annual_2026||{};
  const annualTrades=Array.isArray(annual.trades)?annual.trades:[];
  const annualEvents=Array.isArray(annual.events)?annual.events:[];
  const forwardTrades=Array.isArray(ledger.trades)?ledger.trades:[];
  const forwardEvents=Array.isArray(ledger.events)?ledger.events:[];
  const trades=annualTrades.length?annualTrades:forwardTrades;
  const ledgerEvents=annualTrades.length?annualEvents:forwardEvents;

  if(trades.length){
    const recent=[...trades].sort((a,b)=>Date.parse(b.entry_time)-Date.parse(a.entry_time));
    const symbols=[];
    for(const t of recent){
      const s=String(t.symbol||'').toUpperCase();
      if(s&&!symbols.includes(s))symbols.push(s);
      if(symbols.length>=8)break;
    }
    const hist=await getJSON('/api/history?mode=ytd-points&market=US&assets='+encodeURIComponent(symbols.join(',')));
    const by=new Map((hist.items||[]).map(x=>[String(x.symbol||'').toUpperCase(),x]));

    const charts=symbols.map(symbol=>{
      const raw=by.get(symbol);
      if(!raw)return '';
      const events=ledgerEvents
        .filter(e=>String(e.symbol||'').toUpperCase()===symbol)
        .map(e=>({...e,price:n(e.price)}))
        .filter(e=>e.price!=null)
        .sort((a,b)=>Date.parse(a.time)-Date.parse(b.time));
      const symTrades=trades.filter(t=>String(t.symbol||'').toUpperCase()===symbol);
      const closed=symTrades.filter(t=>t.exit_time&&n(t.return_pct)!=null);
      let multiple=closed.reduce((m,t)=>m*(1+n(t.return_pct)),1);
      const open=symTrades.find(t=>!t.exit_time);
      const rows=raw.rows||[];
      const last=n(rows.at(-1)?.close);
      let openPosition=null;
      if(open&&last!=null&&n(open.entry_price)>0){
        const w=n(open.position_weight)??1;
        const r=w*(last/n(open.entry_price)-1)-w*0.001;
        multiple*=1+r;
        openPosition={entry_time:open.entry_time,entry_price:n(open.entry_price),current_price:last,return_pct:r*100};
      }
      const wins=closed.filter(t=>n(t.return_pct)>0).length;
      const hasRecon=symTrades.some(t=>t.provenance==='R5_1_RECONSTRUCTED_2026');
      const item={...raw,events,source:annualTrades.length?'R5_1_ANNUAL_2026_LEDGER':'R5_1_CANONICAL_FORWARD_LEDGER',summary:{...(raw.summary||{}),strategy_return_pct:(multiple-1)*100,closed_trades:closed.length,win_rate_pct:closed.length?wins/closed.length*100:null,open_position:openPosition,rule:hasRecon?'R5.1 2026 RECON + FORWARD':'R5.1 FORWARD SHADOW'}};
      return ytdPointChart(item,{name:symbol,actualModel:true,lifecycle:true,rule:item.summary.rule});
    }).filter(Boolean).join('');

    const recentRows=recent.slice(0,24).map(t=>{
      const recon=t.provenance==='R5_1_RECONSTRUCTED_2026';
      const ret=n(t.return_pct);
      const tag=recon?badge('RECON','warn'):badge('FORWARD','ok');
      return `<div class="top"><div><div class="asset">${esc(t.symbol||'—')} ${tag}</div><div class="small">${time(t.entry_time)} · +4 bars${t.exit_time?' · closed':' · open'}</div></div><div class="right"><b>${ret==null?'OPEN':pct(ret,100)}</b><div class="small">w ${pct(n(t.position_weight),100)}</div></div></div>`;
    }).join('');

    const annualMode=annualTrades.length>0;
    const title=annualMode?'R5.1 2026 Annual Ledger':'R5.1 Forward SHADOW lifecycle';
    const subtitle=annualMode?'RECON + Forward · B/S +4 bars':'Forward SHADOW · B/S +4 bars';
    return `<div class="section"><div class="section-title"><h3>${title}</h3><span class="small">${subtitle} · 실제 체결 아님</span></div>${annualMode?`<div class="card section"><div class="section-title"><h3>최근 Ledger</h3><span class="small">전체 ${fmt(trades.length,0)} trades</span></div>${recentRows}</div>`:''}<div class="trade-chart-grid">${charts||'<div class="notice">가격 이력을 불러오지 못했습니다.</div>'}</div></div>`;
  }

  const selector=src.today_selector||{};
  const symbol=String(selector.selected_symbol||'').toUpperCase();
  if(!symbol)return '<div class="notice">현재 표시 가능한 R5.1 모델 신호가 없습니다.</div>';
  const hist=await getJSON('/api/history?mode=ytd-points&market=US&assets='+encodeURIComponent(symbol));
  const raw=(hist.items||[]).find(x=>String(x.symbol||'').toUpperCase()===symbol);
  if(!raw)return '<div class="notice">현재 모델 선택 종목의 가격 이력이 없습니다.</div>';
  const events=[];
  if(selector.shadow_entry_this_signal===true){events.push({time:selector.as_of_utc,price:n(selector.reference_price),signal:'BUY',event_type:'R5_1_SHADOW_ENTRY',source:'R5.1_SHADOW_SIGNAL'});}
  const item={...raw,events,summary:{...(raw.summary||{}),strategy_return_pct:null,closed_trades:0,win_rate_pct:null,open_position:null,rule:'R5.1 SHADOW SIGNAL'}};
  return '<div class="section"><div class="section-title"><h3>현재 R5.1 모델 신호</h3><span class="small">SHADOW · 체결 아님</span></div>'+ytdPointChart(item,{name:symbol,actualModel:true,signalOnly:true,rule:'R5.1 SHADOW'})+'</div>';
}'''

US_VIEW = r'''function usModelPerformanceView(j,marketSnapshot=null){
  const s=j.summary||{},official=n(s.selector_observed_hit_rate_pct);
  const ledger=marketSnapshot?.payload?.source_payload?.r5_shadow_ledger||{};
  const annual=ledger.annual_2026||{};
  const recon=annual.reconstructed?.summary||{};
  const forward=annual.forward?.summary||{};
  const annualTrades=Array.isArray(annual.trades)?annual.trades:[];
  if(annualTrades.length){
    const reconRet=n(recon.closed_compound_return_pct),forwardRet=n(forward.closed_compound_return_pct);
    return `<div class="model-disclosure"><b>R5.1 · 2026 Annual Ledger</b><span>${badge('RECON + FORWARD','warn')}</span><span>${badge('실거래 아님','warn')}</span></div><div class="grid4 model-kpis">${card('2026 재구성 복리',reconRet==null?'—':pct(reconRet,1),`${fmt(recon.closed_count,0)} trades · IN-SAMPLE`)}${card('Forward SHADOW 복리',forwardRet==null?'—':pct(forwardRet,1),`${fmt(forward.closed_count,0)} closed · +4 bars`)}${card('2026 Ledger',fmt(annualTrades.length,0)+' trades',`RECON ${fmt(recon.trade_count,0)} · Forward ${fmt(forward.trade_count,0)}`)}${card('Forward Open',fmt(forward.open_count,0),esc((forward.open_symbols||[]).join(', ')||'—'))}</div><div class="notice model-note"><b>중요:</b> 2026-01-01부터 R5.1 freeze boundary까지는 현재 frozen R5.1을 과거 데이터에 재적용한 <b>reconstructed / in-sample replay</b>이며 OOS·prospective 성과가 아닙니다. boundary 이후만 canonical Forward SHADOW입니다. 모든 trade는 원래 R5.1 규칙인 non-overlap entry + <b>정확히 +4 bars exit</b>를 사용하며 10 bps 비용을 반영합니다.</div>`;
  }
  const ls=ledger.summary||{};
  const hasLedger=Array.isArray(ledger.trades)&&ledger.trades.length>0;
  if(hasLedger){
    const compound=n(ls.closed_compound_return_pct),closed=n(ls.closed_count),open=n(ls.open_count);
    return `<div class="model-disclosure"><b>R5.1 실제 모델 · Forward SHADOW ledger</b><span>${badge('실거래 아님','warn')}</span></div><div class="grid4 model-kpis">${card('종료 cycle 복리',compound==null?'—':pct(compound,1),`${fmt(closed,0)}개 closed trade`)}${card('Open',fmt(open,0),esc((ls.open_symbols||[]).join(', ')||'—'))}${card('공식 관측 적중률',official==null?'—':`${official.toFixed(1)}%`,`${fmt(s.selector_prospective_outcomes,0)}개 prospective outcome`)}${card('Ledger',fmt(ls.trade_count,0)+' trades',`${time(s.window_start)} ~ ${time(s.window_end)}`)}</div><div class="notice model-note">Canonical R5.1 Forward SHADOW trade log의 non-overlap entry와 정확한 +4 bars exit를 사용합니다.</div>`;
  }
  return `<div class="model-disclosure"><b>R5.1 실제 모델 · SHADOW</b><span>${badge('실거래 아님','warn')}</span></div><div class="grid4 model-kpis">${card('R5.1 수익률','미산출','lifecycle ledger 없음')}${card('공식 관측 적중률',official==null?'—':`${official.toFixed(1)}%`,`${fmt(s.selector_prospective_outcomes,0)}개 prospective outcome`)}${card('관측 일수',fmt(s.prospective_distinct_days,0),`${fmt(s.distinct_model_snapshots,0)}개 model snapshot`)}${card('Shadow 신호',fmt(s.shadow_signal_count,0),`${time(s.window_start)} ~ ${time(s.window_end)}`)}</div><div class="notice model-note">Forward SHADOW lifecycle 데이터가 아직 없습니다.</div>`;
}'''


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_investment_hub_v7414.py <source-root>")
    root = Path(sys.argv[1]).resolve()
    app_path = root / "app.js"
    index_path = root / "index.html"
    health_path = root / "api/health.js"
    vercel_path = root / "vercel.json"
    for p in (app_path,index_path,health_path,vercel_path):
        if not p.exists(): raise SystemExit(f"[FAIL] missing recovered source: {p}")
    app=app_path.read_text(encoding="utf-8"); index=index_path.read_text(encoding="utf-8"); health=health_path.read_text(encoding="utf-8")
    if BASE_VERSION not in index: raise SystemExit(f"[FAIL] expected base version {BASE_VERSION}")
    for marker in ("R5.1 Forward SHADOW lifecycle","STRICT_TOP3_ACTUAL_LEDGER","accountKrw"):
        if marker not in app: raise SystemExit(f"[FAIL] v7.4.13 base marker missing: {marker}")
    app=replace_block(app,"async function usShadowSignalChart(marketSnapshot){","\nfunction usModelPerformanceView(",US_CHART,"US annual chart")
    app=replace_block(app,"function usModelPerformanceView(j,marketSnapshot=null){","\n\nasync function loadActualModelPerformance",US_VIEW,"US annual summary")
    for marker in ("R5.1 2026 Annual Ledger","R5_1_RECONSTRUCTED_2026","annual_2026","정확히 +4 bars exit","STRICT_TOP3_ACTUAL_LEDGER"):
        if marker not in app: raise SystemExit(f"[FAIL] v7.4.14 marker missing: {marker}")
    index=index.replace(BASE_VERSION,TARGET_VERSION); health=health.replace(BASE_VERSION,TARGET_VERSION)
    health=health.replace("R5.1_SHADOW_LIFECYCLE_LEDGER","R5.1_2026_RECONSTRUCTED_PLUS_FORWARD_LEDGER")
    api_count=len(list((root/"api").rglob("*.js")))
    if api_count!=12: raise SystemExit(f"[FAIL] API function count changed: {api_count}")
    for p in list((root/"api").rglob("*.js"))+list((root/"lib").rglob("*.js")):
        text=p.read_text(encoding="utf-8")
        if "req.query" in text or "url.parse(" in text: raise SystemExit(f"[FAIL] query-parser regression token in {p.relative_to(root)}")
    app_path.write_text(app,encoding="utf-8"); index_path.write_text(index,encoding="utf-8"); health_path.write_text(health,encoding="utf-8")
    print("[PASS] vNext.7.4.14 R5.1 2026 annual ledger UI")
    print("[PASS] reconstructed vs canonical Forward SHADOW provenance separated")
    print("[PASS] API function count = 12")
    return 0


if __name__ == "__main__": raise SystemExit(main())
