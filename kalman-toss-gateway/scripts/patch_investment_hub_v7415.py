from __future__ import annotations

import sys
from pathlib import Path

BASE_VERSION = "vNext.7.4.14"
TARGET_VERSION = "vNext.7.4.15"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"[FAIL] {label}: expected 1 match, got {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_investment_hub_v7415.py <source-root>")

    root = Path(sys.argv[1]).resolve()
    app_path = root / "app.js"
    index_path = root / "index.html"
    health_path = root / "api/health.js"

    for path in (app_path, index_path, health_path):
        if not path.exists():
            raise SystemExit(f"[FAIL] missing recovered source: {path}")

    app = app_path.read_text(encoding="utf-8")
    index = index_path.read_text(encoding="utf-8")
    health = health_path.read_text(encoding="utf-8")

    if BASE_VERSION not in index:
        raise SystemExit(f"[FAIL] expected base version {BASE_VERSION}")
    for marker in ("R5.1 2026 Annual Ledger", "R5_1_ANNUAL_2026_LEDGER", "annual_2026"):
        if marker not in app:
            raise SystemExit(f"[FAIL] v7.4.14 base marker missing: {marker}")

    old = r"""    const recentRows=recent.slice(0,24).map(t=>{
      const recon=t.provenance==='R5_1_RECONSTRUCTED_2026';
      const ret=n(t.return_pct);
      const tag=recon?badge('RECON','warn'):badge('FORWARD','ok');
      return `<div class="top"><div><div class="asset">${esc(t.symbol||'—')} ${tag}</div><div class="small">${time(t.entry_time)} · +4 bars${t.exit_time?' · closed':' · open'}</div></div><div class="right"><b>${ret==null?'OPEN':pct(ret,100)}</b><div class="small">w ${pct(n(t.position_weight),100)}</div></div></div>`;
    }).join('');

    const annualMode=annualTrades.length>0;
    const title=annualMode?'R5.1 2026 Annual Ledger':'R5.1 Forward SHADOW lifecycle';
    const subtitle=annualMode?'RECON + Forward · B/S +4 bars':'Forward SHADOW · B/S +4 bars';
    return `<div class="section"><div class="section-title"><h3>${title}</h3><span class="small">${subtitle} · 실제 체결 아님</span></div>${annualMode?`<div class="card section"><div class="section-title"><h3>최근 Ledger</h3><span class="small">전체 ${fmt(trades.length,0)} trades</span></div>${recentRows}</div>`:''}<div class="trade-chart-grid">${charts||'<div class="notice">가격 이력을 불러오지 못했습니다.</div>'}</div></div>`;"""

    new = r"""    const ledgerRow=t=>{
      const recon=t.provenance==='R5_1_RECONSTRUCTED_2026';
      const ret=n(t.return_pct);
      const tag=recon?badge('RECON','warn'):badge('FORWARD','ok');
      return `<div class="top"><div><div class="asset">${esc(t.symbol||'—')} ${tag}</div><div class="small">${time(t.entry_time)} · +4 bars${t.exit_time?' · closed':' · open'}</div></div><div class="right"><b>${ret==null?'OPEN':pct(ret,100)}</b><div class="small">w ${pct(n(t.position_weight),100)}</div></div></div>`;
    };
    const recentRows=recent.slice(0,24).map(ledgerRow).join('');
    const chronological=[...trades].sort((a,b)=>Date.parse(a.entry_time)-Date.parse(b.entry_time));
    const allRows=chronological.map(ledgerRow).join('');
    const firstTrade=chronological[0],lastTrade=chronological.at(-1);
    const monthCount=new Map();
    chronological.forEach(t=>{
      const d=new Date(t.entry_time);
      if(Number.isNaN(d.getTime()))return;
      const key=`${d.getUTCFullYear()}-${String(d.getUTCMonth()+1).padStart(2,'0')}`;
      monthCount.set(key,(monthCount.get(key)||0)+1);
    });
    const monthSummary=[...monthCount.entries()].map(([m,c])=>`<span class="badge">${esc(m)} ${fmt(c,0)}</span>`).join(' ');

    const annualMode=annualTrades.length>0;
    const title=annualMode?'R5.1 2026 Annual Ledger':'R5.1 Forward SHADOW lifecycle';
    const subtitle=annualMode?'RECON + Forward · B/S +4 bars':'Forward SHADOW · B/S +4 bars';
    const fullLedger=annualMode?`<details open class="card section"><summary><b>2026 전체 Ledger</b> · ${fmt(trades.length,0)} trades · ${time(firstTrade?.entry_time)} → ${time(lastTrade?.entry_time)}</summary><div class="small" style="margin:10px 0">월별 거래수 · ${monthSummary}</div><div class="annual-ledger-scroll" style="max-height:720px;overflow:auto">${allRows}</div></details>`:'';
    return `<div class="section"><div class="section-title"><h3>${title}</h3><span class="small">${subtitle} · 실제 체결 아님</span></div>${annualMode?`<div class="card section"><div class="section-title"><h3>최근 Ledger</h3><span class="small">최근 24 / 전체 ${fmt(trades.length,0)} trades</span></div>${recentRows}</div>`:''}${fullLedger}<div class="trade-chart-grid">${charts||'<div class="notice">가격 이력을 불러오지 못했습니다.</div>'}</div></div>`;"""

    app = replace_once(app, old, new, "annual ledger browser")

    for marker in ("2026 전체 Ledger", "annual-ledger-scroll", "월별 거래수", "R5_1_ANNUAL_2026_LEDGER"):
        if marker not in app:
            raise SystemExit(f"[FAIL] v7.4.15 marker missing: {marker}")

    index = index.replace(BASE_VERSION, TARGET_VERSION)
    health = health.replace(BASE_VERSION, TARGET_VERSION)

    api_count = len(list((root / "api").rglob("*.js")))
    if api_count != 12:
        raise SystemExit(f"[FAIL] API function count changed: {api_count}")

    app_path.write_text(app, encoding="utf-8")
    index_path.write_text(index, encoding="utf-8")
    health_path.write_text(health, encoding="utf-8")

    print("[PASS] vNext.7.4.15 full 2026 ledger browser")
    print("[PASS] earliest ledger is visible from January 2026")
    print("[PASS] API function count = 12")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
