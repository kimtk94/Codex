from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

BASE = "vNext.7.4.15"
TARGET = "vNext.7.4.16"


def load_stock(path: Path):
    spec = importlib.util.spec_from_file_location("kalman_v7416_stock", path)
    if spec is None or spec.loader is None:
        raise SystemExit("[FAIL] cannot load stock v7.4.16 patcher")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"[FAIL] {label}: expected 1 got {n}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: bridge_investment_hub_v7416_strategy.py "
            "<source-root> <stock-v7416-patcher>"
        )

    root = Path(sys.argv[1]).resolve()
    stock_path = Path(sys.argv[2]).resolve()
    stock = load_stock(stock_path)

    app_path = root / "app.js"
    css_path = root / "style.css"
    index_path = root / "index.html"
    health_path = root / "api/health.js"
    for p in (app_path, css_path, index_path, health_path):
        if not p.exists():
            raise SystemExit(f"[FAIL] missing source: {p}")

    app = app_path.read_text(encoding="utf-8")
    css = css_path.read_text(encoding="utf-8")
    index = index_path.read_text(encoding="utf-8")
    health = health_path.read_text(encoding="utf-8")

    if BASE not in index:
        raise SystemExit(f"[FAIL] expected base version {BASE}")
    for marker in (
        "accountKrw",
        "R5.1 2026 Annual Ledger",
        "2026 전체 Ledger",
        "function renderUSCurrent(j){",
        "function renderUSModel(j){",
        "function renderMarket(m,j){",
    ):
        if marker not in app:
            raise SystemExit(f"[FAIL] v7.4.15 Strategy-Tabs marker missing: {marker}")

    # Header / command shell: reuse the audited v7.4.16 constants verbatim.
    start = '<header class="head">'
    end = '    <section class="card account section">'
    a = index.find(start)
    b = index.find(end, a)
    if a < 0 or b < 0:
        raise SystemExit("[FAIL] header anchors")
    index = index[:a] + stock.HEADER + "\n\n    " + index[b:]
    index = index.replace(
        '<nav class="tabs" aria-label="시장 선택">',
        '<nav class="tabs primary-tabs" aria-label="시장 선택">',
        1,
    )

    # Reuse Command Center / ledger / model / Top-1 helpers verbatim.
    app = once(
        app,
        "async function loadAccount(){",
        stock.HELPERS + "\nasync function loadAccount(){",
        "command helpers",
    )
    account_anchor = (
        "    const summary=[\n"
        "      card('총 매입금액',accountUsd(totalPurchaseUsd),accountKrw(totalPurchaseUsd,fx)),"
    )
    app = once(
        app,
        account_anchor,
        "    renderCommandAccount(j,fx);\n\n" + account_anchor,
        "command account",
    )

    # The stock v7.4.16 US workspace expected the older Performance-Tabs
    # implementation. Keep the audited Overview/Ledger/Model workspace but
    # wire its Performance pane to this recovery line's Current + Actual Model
    # loaders instead.
    us_view = stock.US_VIEW
    perf_start = us_view.find("  var perf=top6.length?")
    perf_end = us_view.find("\n  return ", perf_start)
    if perf_start < 0 or perf_end < 0:
        raise SystemExit("[FAIL] stock US performance block not found")
    perf = (
        "  var perf=top6.length?'<div class=\"performance-section\">"
        "<div class=\"section-title\"><h3>Performance</h3>"
        "<span class=\"small\">Current + Actual Model</span></div>"
        "<div id=\"usYtdCharts\" class=\"trade-chart-grid\">"
        "<div class=\"muted\">Current YTD charts loading...</div></div>"
        "<div id=\"usActualModelPerformance\" class=\"section\">"
        "<div class=\"muted\">R5.1 actual-model ledger loading...</div></div>"
        "</div>':'<div class=\"notice\">성과 데이터가 없습니다.</div>';"
    )
    us_view = us_view[:perf_start] + perf + us_view[perf_end:]

    # Keep old renderUSCurrent/renderUSModel as fallback code; add the new
    # unified workspace and route US to it.
    market_anchor = "function renderMarket(m,j){"
    if app.count(market_anchor) != 1:
        raise SystemExit("[FAIL] renderMarket anchor")
    app = app.replace(market_anchor, us_view.rstrip() + "\n\n" + market_anchor, 1)

    old_us_route = (
        "  if(m==='US')return mode==='MODEL'?"
        "renderUSModel(j):renderUSCurrent(j);"
    )
    app = once(
        app,
        old_us_route,
        "  if(m==='US')return renderUS(j);",
        "unified US route",
    )

    old_current = (
        "  if(m==='US'&&mode==='CURRENT')"
        "loadYtdStockCharts('US',(j.payload?.top3||[]).slice(0,3));"
    )
    old_model = (
        "  if(m==='US'&&mode==='MODEL')"
        "loadActualModelPerformance('US',(j.payload?.top3||[]).slice(0,6),j);"
    )
    if old_current not in app or old_model not in app:
        raise SystemExit("[FAIL] Strategy-Tabs US afterRender anchors")
    app = app.replace(old_current, "", 1).replace(old_model, "", 1)

    unified_after = (
        "  if(m==='US'){"
        "const a=(j.payload?.assets||j.payload?.top3||[]).slice(0,6);"
        "bindUsWorkspace();"
        "loadYtdStockCharts('US',a.slice(0,3));"
        "loadActualModelPerformance('US',a,j);"
        "loadUsPrimaryChart(j);"
        "renderCommandModel(j);"
        "}"
    )
    kr_anchor = "  if(m==='KR'&&mode==='CURRENT')"
    if kr_anchor not in app:
        raise SystemExit("[FAIL] KR afterRender insertion anchor")
    app = app.replace(kr_anchor, unified_after + "\n" + kr_anchor, 1)

    app = once(
        app,
        "loadAccount();loadMarket('GLOBAL');",
        "loadAccount();loadCommandCenter();loadMarket('GLOBAL');",
        "boot command center",
    )

    css = css.rstrip() + "\n\n" + stock.CSS.strip() + "\n"
    health = health.replace(BASE, TARGET)
    index = index.replace(BASE, TARGET)
    index = re.sub(
        r"<footer>[^<]*vNext\\.7\\.4\\.16[^<]*</footer>",
        "<footer>vNext.7.4.16 · Command Center + Model Workspace</footer>",
        index,
        count=1,
    )
    if "vNext.7.4.16 · Command Center + Model Workspace" not in index:
        raise SystemExit("[FAIL] v7.4.16 footer normalization")

    if len(list((root / "api").rglob("*.js"))) != 12:
        raise SystemExit("[FAIL] API function count changed")

    for marker in (
        "commandAccount",
        "commandModel",
        "commandHealth",
        "R5.1 Top 6",
        "usLedgerTable",
        "usModelTable",
        "loadUsPrimaryChart",
        "bindUsWorkspace",
        "function renderUS(j){",
        "Current + Actual Model",
    ):
        if marker not in app and marker not in index:
            raise SystemExit(f"[FAIL] v7.4.16 marker missing: {marker}")

    app_path.write_text(app, encoding="utf-8")
    css_path.write_text(css, encoding="utf-8")
    index_path.write_text(index, encoding="utf-8")
    health_path.write_text(health, encoding="utf-8")

    print("[PASS] vNext.7.4.16 Strategy-Tabs -> Command Center bridge")
    print("[PASS] US Overview / Performance / Ledger / Model")
    print("[PASS] Current + Actual Model loaders preserved")
    print("[PASS] API function count = 12")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
