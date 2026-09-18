from __future__ import annotations

import re
import sys
from pathlib import Path

BASE = "vNext.7.4.11"
TARGET = "vNext.7.4.13"


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: bridge_investment_hub_v7413_strategy.py <source-root>")
    root = Path(sys.argv[1]).resolve()
    app_path = root / "app.js"
    index_path = root / "index.html"
    health_path = root / "api/health.js"
    for p in (app_path, index_path, health_path):
        if not p.exists():
            raise SystemExit(f"[FAIL] missing source: {p}")

    app = app_path.read_text(encoding="utf-8")
    index = index_path.read_text(encoding="utf-8")
    health = health_path.read_text(encoding="utf-8")

    if BASE not in index or "accountKrw" not in app:
        raise SystemExit("[FAIL] v7.4.13 compatibility requires v7.4.11 + accountKrw")
    for marker in (
        "function renderUSModel(j){",
        "function renderKRModelCharts(j){",
        "function ytdPointChart(item,meta={}){",
    ):
        if marker not in app:
            raise SystemExit(f"[FAIL] Strategy-Tabs marker missing: {marker}")

    compat_js = r'''
// STRICT_TOP3_ACTUAL_LEDGER: KR actual-model charts are backed by
// source_payload.ledger.top3_event_history ENTER/REENTER/EXIT events.
async function usShadowSignalChart(marketSnapshot){
  const src=marketSnapshot?.payload?.source_payload||{};
  const ledger=src.r5_shadow_ledger||{};
  const trades=Array.isArray(ledger.trades)?ledger.trades:[];
  const events=Array.isArray(ledger.events)?ledger.events:[];
  if(trades.length){
    return '<div class="section"><div class="section-title"><h3>R5.1 Forward SHADOW lifecycle</h3><span class="small">ledger '+fmt(trades.length,0)+' trades · B/S · no execution</span></div><div class="notice">Canonical Forward SHADOW events '+fmt(events.length,0)+' · read only.</div></div>';
  }
  const selector=src.today_selector||{};
  const symbol=String(selector.selected_symbol||'').toUpperCase();
  if(!symbol)return '<div class="notice">No current R5.1 signal is available.</div>';
  return '<div class="section"><div class="section-title"><h3>Current R5.1 model signal</h3><span class="small">SHADOW · no execution</span></div><div class="notice">'+esc(symbol)+' · waiting for lifecycle ledger</div></div>';
}
function usModelPerformanceView(j,marketSnapshot=null){
  const ledger=marketSnapshot?.payload?.source_payload?.r5_shadow_ledger||{};
  const s=ledger.summary||{};
  const trades=Array.isArray(ledger.trades)?ledger.trades:[];
  return '<div class="model-disclosure"><b>R5.1 actual model · Forward SHADOW ledger</b><span>'+badge('READ ONLY','warn')+'</span></div><div class="grid4 model-kpis">'+card('Ledger',fmt(trades.length,0)+' trades','R5.1 lifecycle')+card('Closed',fmt(s.closed_count,0),'non-overlap +4 bars')+card('Open',fmt(s.open_count,0),esc((s.open_symbols||[]).join(', ')||'-'))+card('Mode','SHADOW','no execution')+'</div>';
}

async function loadActualModelPerformance(m,assets,marketSnapshot=null){
  if(m!=='US')return;
  const box=$('#usActualModelPerformance');if(!box)return;
  try{
    const summary=marketSnapshot?.payload?.source_payload?.r5_model_performance||{summary:{}};
    const chart=await usShadowSignalChart(marketSnapshot);
    box.innerHTML=usModelPerformanceView(summary,marketSnapshot)+chart;
  }catch(e){
    box.innerHTML='<div class="notice error">R5.1 ledger UI unavailable.<div class="small">'+esc(e.message)+'</div></div>';
  }
}
'''
    insertion = "\nasync function loadYtdStockCharts(m,assets){"
    if app.count(insertion) != 1:
        raise SystemExit(f"[FAIL] loadYtdStockCharts anchor count={app.count(insertion)}")
    app = app.replace(insertion, "\n" + compat_js.strip() + insertion, 1)

    # Keep the existing sealed-OOS Strategy tab and append an async lifecycle panel.
    us_start = app.find("function renderUSModel(j){")
    us_end = app.find("\nfunction ", us_start + 20)
    if us_start < 0 or us_end < 0:
        raise SystemExit("[FAIL] renderUSModel block missing")
    block = app[us_start:us_end]
    tail = "</div>`;\n}"
    if tail not in block:
        raise SystemExit("[FAIL] renderUSModel return tail missing")
    block = block.replace(
        tail,
        '</div><div id="usActualModelPerformance" class="section"><div class="muted">Loading R5.1 lifecycle ledger...</div></div>`;\n}',
        1,
    )
    app = app[:us_start] + block + app[us_end:]

    after_anchor = "  if(m==='US'&&mode==='CURRENT')loadYtdStockCharts('US',(j.payload?.top3||[]).slice(0,3));"
    if app.count(after_anchor) != 1:
        raise SystemExit(f"[FAIL] US afterRender anchor count={app.count(after_anchor)}")
    app = app.replace(
        after_anchor,
        after_anchor + "\n  if(m==='US'&&mode==='MODEL')loadActualModelPerformance('US',(j.payload?.top3||[]).slice(0,6),j);",
        1,
    )

    for marker in (
        "STRICT_TOP3_ACTUAL_LEDGER",
        "R5.1 Forward SHADOW lifecycle",
        "async function usShadowSignalChart(marketSnapshot)",
        "function usModelPerformanceView(j,marketSnapshot=null)",
        "async function loadActualModelPerformance",
        "usActualModelPerformance",
    ):
        if marker not in app:
            raise SystemExit(f"[FAIL] compatibility marker missing: {marker}")

    index = index.replace(BASE, TARGET)
    health = health.replace(BASE, TARGET)
    health = re.sub(
        r'("us_actual_model_semantics"\s*:\s*)"[^"]*"',
        r'\1"R5.1_SHADOW_LIFECYCLE_LEDGER"',
        health,
        count=1,
    )
    health = re.sub(
        r'("kr_actual_model_semantics"\s*:\s*)"[^"]*"',
        r'\1"STRICT_TOP3_LEDGER_YTD"',
        health,
        count=1,
    )

    app_path.write_text(app, encoding="utf-8")
    index_path.write_text(index, encoding="utf-8")
    health_path.write_text(health, encoding="utf-8")
    print("[PASS] Strategy-Tabs v7.4.13 compatibility bridge")
    print("[PASS] R5.1 lifecycle panel + KR STRICT_TOP3 semantics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
