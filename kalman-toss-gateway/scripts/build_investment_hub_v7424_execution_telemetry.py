from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE_MANIFEST = ROOT / "kalman-hub-recovery/v7.4.23/source_manifest.ndjson"
OUT_DIR = ROOT / "kalman-hub-recovery/v7.4.24"
TARGET = "vNext.7.4.24"


def decode_manifest(manifest: Path, out: Path) -> None:
    rows = [json.loads(x) for x in manifest.read_text(encoding="utf-8").splitlines() if x.strip()]
    if len(rows) != 30:
        raise SystemExit(f"expected 30 files, got {len(rows)}")
    for row in rows:
        rel = Path(row["file"])
        if rel.is_absolute() or ".." in rel.parts:
            raise SystemExit(f"unsafe path: {rel}")
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(base64.b64decode(row["data_b64"]))


def patch_api(src: Path) -> None:
    p = src / "api/assets.js"
    text = p.read_text(encoding="utf-8")
    old = """      sql`SELECT position_id,symbol,strategy_version,state,entry_signal_as_of,entry_order_id,
                 entry_filled_quantity,entry_average_price,exit_order_id,exit_filled_quantity,
                 exit_average_price,exit_reason,realized_return_pct,updated_at
          FROM v_live_trade_ledger ORDER BY updated_at DESC LIMIT 20`,"""
    new = """      sql`SELECT position_id,symbol,strategy_version,state,entry_signal_as_of,entry_order_id,
                 entry_filled_quantity,entry_average_price,exit_order_id,exit_filled_quantity,
                 exit_average_price,exit_reason,realized_return_pct,net_return,round_trip_cost_bps,
                 entry_slippage_bps,exit_slippage_bps,entry_spread_bps,exit_spread_bps,
                 entry_cost_bps,exit_cost_bps,entry_fill_latency_ms,exit_fill_latency_ms,
                 entry_submit_latency_ms,exit_submit_latency_ms,
                 entry_rate_limit_remaining,exit_rate_limit_remaining,updated_at
          FROM v_live_trade_ledger ORDER BY updated_at DESC LIMIT 20`,"""
    if old not in text:
        raise SystemExit("execution ledger SQL anchor missing")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_app(src: Path) -> None:
    p = src / "app.js"
    text = p.read_text(encoding="utf-8")
    start = text.find("function renderExecutionLedger(ctl){")
    end = text.find("\nasync function loadCommandCenter()", start)
    if start < 0 or end < 0:
        raise SystemExit("renderExecutionLedger anchors missing")

    replacement = r"""function renderExecutionLedger(ctl){
  var box=$('#executionLedger'),state=$('#executionLedgerState');if(!box)return;
  var rows=(ctl&&ctl.execution_ledger)||[];
  function bps(v){
    var x=n(v);if(x==null)return '—';
    return (x>0?'+':'')+fmt(x,1)+' bp';
  }
  function pair(a,b,unitFn){
    var aa=unitFn(a),bb=unitFn(b);
    if(aa==='—'&&bb==='—')return '—';
    return '진입 '+aa+' / 청산 '+bb;
  }
  function latency(v){
    var x=n(v);if(x==null)return '—';
    return x>=1000?fmt(x/1000,2)+'s':fmt(x,0)+'ms';
  }
  if(!rows.length){
    if(state){state.className='pill';state.textContent='기록 없음';}
    box.innerHTML='<div class="execution-empty"><div><b>Neon 실매매 미러 기록 없음</b><span>현재 자동매매 주문·체결이 Neon에 기록되지 않았다는 뜻입니다. Toss 전체 거래내역이 0건이라는 뜻은 아닙니다.</span></div></div>';
    return;
  }
  if(state){state.className='pill ok';state.textContent=rows.length+'건 기록';}
  box.innerHTML='<div class="table-scroll"><table class="data-table"><thead><tr><th>신호 시각</th><th>종목</th><th>상태</th><th>진입 / 청산</th><th>가격수익</th><th>순수익</th><th>슬리피지</th><th>실제 비용</th><th>체결 지연</th><th>청산 사유</th></tr></thead><tbody>'+
    rows.map(function(x){
      var gross=n(x.realized_return_pct),net=n(x.net_return),cost=n(x.round_trip_cost_bps);
      var slip=pair(x.entry_slippage_bps,x.exit_slippage_bps,bps);
      var lag=pair(x.entry_fill_latency_ms,x.exit_fill_latency_ms,latency);
      return '<tr>'+
        '<td>'+time(x.entry_signal_as_of)+'</td>'+
        '<td><b>'+esc(x.symbol||'—')+'</b></td>'+
        '<td>'+esc(executionStateLabel(x.state))+'</td>'+
        '<td>'+money(x.entry_average_price,'USD')+' / '+(x.exit_average_price==null?'—':money(x.exit_average_price,'USD'))+'</td>'+
        '<td class="'+(gross==null?'':gross>=0?'good':'bad')+'">'+(gross==null?'—':pct(gross,100))+'</td>'+
        '<td class="'+(net==null?'':net>=0?'good':'bad')+'">'+(net==null?'—':pct(net,100))+'</td>'+
        '<td>'+esc(slip)+'</td>'+
        '<td>'+(cost==null?'—':bps(cost))+'</td>'+
        '<td>'+esc(lag)+'</td>'+
        '<td>'+esc(exitReasonLabel(x.exit_reason))+'</td>'+
      '</tr>';
    }).join('')+
    '</tbody></table></div>'+
    '<div class="next-actions-note"><b>Execution Quality:</b> 슬리피지는 주문 직전 executable touch 대비 실제 평균 체결가 기준이며 양수일수록 불리합니다. 순수익은 Toss가 제공한 실제 commission·tax를 반영합니다. 과거 주문은 당시 호가를 복원할 수 없어 slippage가 비어 있을 수 있습니다.</div>';
}
"""
    text = text[:start] + replacement + text[end:]
    p.write_text(text, encoding="utf-8")


def patch_versions(src: Path) -> None:
    for rel in ("index.html", "api/health.js"):
        p = src / rel
        text = p.read_text(encoding="utf-8")
        if "vNext.7.4.23" not in text:
            raise SystemExit(f"version anchor missing in {rel}")
        p.write_text(text.replace("vNext.7.4.23", TARGET), encoding="utf-8")


def validate(src: Path) -> dict:
    api = sorted((src / "api").rglob("*.js"))
    if len(api) != 12:
        raise SystemExit(f"API count changed: {len(api)}")
    index = (src / "index.html").read_text(encoding="utf-8")
    app = (src / "app.js").read_text(encoding="utf-8")
    assets = (src / "api/assets.js").read_text(encoding="utf-8")
    health = (src / "api/health.js").read_text(encoding="utf-8")
    for marker in (
        "net_return",
        "round_trip_cost_bps",
        "entry_slippage_bps",
        "exit_slippage_bps",
        "entry_fill_latency_ms",
        "exit_fill_latency_ms",
    ):
        if marker not in assets:
            raise SystemExit(f"assets missing {marker}")
    for marker in ("Execution Quality:", "순수익", "슬리피지", "실제 비용", "체결 지연"):
        if marker not in app:
            raise SystemExit(f"app missing {marker}")
    if TARGET not in index or TARGET not in health:
        raise SystemExit("version marker missing")
    if "trade_enabled:false" not in health or "account_trade_execution:false" not in health:
        raise SystemExit("web read-only invariant missing")
    if shutil.which("node"):
        for q in sorted(src.rglob("*.js")):
            subprocess.run(["node", "--check", str(q)], check=True, stdout=subprocess.DEVNULL)
    return {
        "version": TARGET,
        "source_files": len([x for x in src.rglob("*") if x.is_file()]),
        "api_functions": len(api),
        "execution_quality_ui": True,
        "web_read_only": True,
        "base_version": "vNext.7.4.23",
    }


def emit_source_manifest(src: Path, out: Path) -> None:
    rows = []
    for p in sorted(x for x in src.rglob("*") if x.is_file()):
        rows.append(json.dumps({
            "file": p.relative_to(src).as_posix(),
            "data_b64": base64.b64encode(p.read_bytes()).decode("ascii"),
        }, separators=(",", ":"), ensure_ascii=False))
    out.write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kalman-v7424-") as td:
        src = Path(td) / "source"
        src.mkdir()
        decode_manifest(BASE_MANIFEST, src)
        patch_api(src)
        patch_app(src)
        patch_versions(src)
        report = validate(src)
        manifest = OUT_DIR / "source_manifest.ndjson"
        emit_source_manifest(src, manifest)
        report["source_manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
        (OUT_DIR / "build_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
