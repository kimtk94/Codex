from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE_BUILDER = ROOT / "kalman-toss-gateway/scripts/build_investment_hub_v7429_neon_selectors.py"
BASE_MANIFEST = ROOT / "kalman-hub-recovery/v7.4.29/source_manifest.ndjson"
OUT_DIR = ROOT / "kalman-hub-recovery/v7.4.30"
TARGET = "vNext.7.4.30"


def build_base() -> None:
    subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
    if not BASE_MANIFEST.is_file():
        raise SystemExit("v7.4.29 base manifest was not generated")


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


def patch_app(src: Path) -> None:
    p = src / "app.js"
    text = p.read_text(encoding="utf-8")
    anchor = "function renderNextActions(){"
    if anchor not in text:
        raise SystemExit("renderNextActions anchor missing")

    helper = r"""
function renderCommandAccount(account,fx){
  kalmanCommandState.account=account||null;
  kalmanCommandState.fx=fx||null;
  var box=$('#commandAccount');if(!box)return;
  var online=Boolean(account&&account.status!=='OFFLINE');
  if(!online){
    box.className='command-kpis';
    box.innerHTML=
      '<div class="command-metric"><span>Toss</span><b>OFFLINE</b><small>계좌 데이터 없음</small></div>'+
      '<div class="command-metric"><span>평가금액</span><b>—</b><small>Broker 연결 필요</small></div>'+
      '<div class="command-metric"><span>평가손익</span><b>—</b><small>Broker 연결 필요</small></div>'+
      '<div class="command-metric"><span>보유 종목</span><b>—</b><small>조회 전용</small></div>';
    renderNextActions();
    return;
  }

  var holdings=asArray(account.holdings),root=unwrap(account.holdings)||{};
  var totalEval=n(root&&root.marketValue&&((root.marketValue.amountAfterCost&&root.marketValue.amountAfterCost.usd)??(root.marketValue.amount&&root.marketValue.amount.usd)));
  var totalPnl=n(root&&root.profitLoss&&((root.profitLoss.amountAfterCost&&root.profitLoss.amountAfterCost.usd)??(root.profitLoss.amount&&root.profitLoss.amount.usd)));
  var krwPower=n(pick(unwrap(account.buying_power_krw),['cashBuyingPower','buyingPower','availableAmount','available','amount','value']));
  var pnlClass=totalPnl==null?'':totalPnl>0?'metric-good':totalPnl<0?'metric-bad':'';
  var bot=botState(account)||{};
  var botLabel=String(bot.executionMode||'SYNC').toUpperCase();

  box.className='command-kpis';
  box.innerHTML=
    '<div class="command-metric"><span>총 평가금액</span><b>'+accountUsd(totalEval,2)+'</b><small>'+accountKrw(totalEval,fx)+'</small></div>'+
    '<div class="command-metric '+pnlClass+'"><span>평가손익</span><b>'+accountUsd(totalPnl,2)+'</b><small>'+accountKrw(totalPnl,fx)+'</small></div>'+
    '<div class="command-metric"><span>매수가능</span><b>'+money(krwPower,'KRW')+'</b><small>보유 '+fmt(holdings.length,0)+'종목</small></div>'+
    '<div class="command-metric"><span>Toss · 서버</span><b>'+esc(botLabel)+'</b><small>'+esc(account.status||'READY')+' · 조회 전용</small></div>';
  renderNextActions();
}

function renderCommandModel(us){
  kalmanCommandState.us=us||null;
  var box=$('#commandModel');if(!box)return;
  var p=us&&us.payload||{},s=p.summary||{},sel=currentUsSelector(us||{});
  var rows=(p.assets||p.top3||[]).slice(0,6);
  var symbol=String(sel.selected_symbol||s.selected_symbol||(rows[0]&&rows[0].symbol)||'—').toUpperCase();
  var score=n(sel.model_score!=null?sel.model_score:(rows[0]&&rows[0].model_score));
  var weight=n(sel.position_weight!=null?sel.position_weight:(rows[0]&&rows[0].position_weight_r4_vol_target));
  var target=n(sel.target_price_4h!=null?sel.target_price_4h:(rows[0]&&rows[0].target_price_4h));
  var ref=n(sel.reference_price!=null?sel.reference_price:(rows[0]&&rows[0].reference_price));
  var agreement=sel.r4_r5_1_agreement||{};
  var topOverlap=n(agreement.top10_overlap);
  var fresh=snapshotValidity(us||{});
  var model=String(sel.primary_lineage||s.primary_lineage||us&&us.model_version||'R5.1');

  var ranks=rows.map(function(x,i){
    var xScore=n(x.model_score);
    return '<div class="command-rank"><b>'+(i+1)+'</b><div><strong>'+esc(x.symbol||'—')+'</strong><small>'+money(x.reference_price,'USD')+' → '+money(x.target_price_4h,'USD')+'</small></div><b>'+(xScore==null?'—':fmt(xScore*10000,2)+'bp')+'</b></div>';
  }).join('');

  box.className='';
  box.innerHTML=
    '<div class="command-model-head"><div><span>Top-1</span><strong>'+esc(symbol)+'</strong><small>'+esc(model)+' · '+(fresh.valid?'스냅샷 유효':'스냅샷 만료')+'</small></div>'+
      '<div class="right"><span>4h 목표</span><strong>'+money(target,'USD')+'</strong><small>기준 '+money(ref,'USD')+'</small></div></div>'+
    '<div class="summary">'+
      badge(score==null?'Score —':fmt(score*10000,2)+' bp',score!=null&&score>0?'ok':'')+' '+
      badge(weight==null?'Weight —':'Weight '+pct(weight,100))+' '+
      (topOverlap==null?'':badge('R4/R5 Top10 '+fmt(topOverlap,0)+'/10'))+
    '</div>'+
    '<div class="command-ranks">'+(ranks||'<div class="muted">모델 순위 데이터가 없습니다.</div>')+'</div>'+
    '<div class="next-actions-note">R5.1 score는 확률이 아니라 universe-relative model score입니다. 기준 '+time(us&&us.data_as_of)+'</div>';
  renderNextActions();
}

"""
    text = text.replace(anchor, helper + anchor, 1)
    p.write_text(text, encoding="utf-8")


def patch_versions(src: Path) -> None:
    for rel in ("index.html", "api/health.js"):
        p = src / rel
        text = p.read_text(encoding="utf-8")
        if "vNext.7.4.29" not in text:
            raise SystemExit(f"v7.4.29 version anchor missing in {rel}")
        p.write_text(text.replace("vNext.7.4.29", TARGET), encoding="utf-8")


def unresolved_render_calls(app: str) -> list[str]:
    definitions = set(
        re.findall(r"(?:async\s+)?function\s+(render[A-Z][A-Za-z0-9_$]*)\s*\(", app)
    )
    calls = set(re.findall(r"\b(render[A-Z][A-Za-z0-9_$]*)\s*\(", app))
    return sorted(calls - definitions)


def validate(src: Path) -> dict:
    api_files = sorted((src / "api").rglob("*.js"))
    if len(api_files) != 12:
        raise SystemExit(f"API count changed: {len(api_files)}")

    index = (src / "index.html").read_text(encoding="utf-8")
    app = (src / "app.js").read_text(encoding="utf-8")
    assets = (src / "api/assets.js").read_text(encoding="utf-8")
    health = (src / "api/health.js").read_text(encoding="utf-8")

    for marker in (
        "function renderCommandAccount(",
        "function renderCommandModel(",
        "command-ranks",
        "R5.1 score는 확률이 아니라",
    ):
        if marker not in app:
            raise SystemExit(f"command renderer marker missing {marker}")

    unresolved = unresolved_render_calls(app)
    if unresolved:
        raise SystemExit(f"undefined render function calls: {unresolved}")

    for marker in (
        "augmentAssetsSelectorsFromNeon",
        "NEON_DASHBOARD_SNAPSHOT",
        "_r5CanonicalLedger",
        "canonical_ledger_source",
        "if(v==null||v==='')return null;",
    ):
        if marker not in assets:
            raise SystemExit(f"preserved API marker missing {marker}")

    for marker in ("R5.1 2026 Annual Ledger", "Execution Quality:", "tradeSnapshotValidity"):
        if marker not in app:
            raise SystemExit(f"preserved UI marker missing {marker}")

    if TARGET not in index or TARGET not in health:
        raise SystemExit("version marker missing")
    if "trade_enabled:false" not in health or "account_trade_execution:false" not in health:
        raise SystemExit("web read-only invariant missing")

    if shutil.which("node"):
        for q in sorted(src.rglob("*.js")):
            subprocess.run(["node", "--check", str(q)], check=True, stdout=subprocess.DEVNULL)

    return {
        "version": TARGET,
        "command_account_renderer_restored": True,
        "command_model_renderer_restored": True,
        "undefined_render_calls": [],
        "canonical_r5_ledger_preserved": True,
        "neon_selector_read_model_preserved": True,
        "trade_gate_unchanged": True,
        "web_read_only": True,
        "base_version": "vNext.7.4.29",
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
    build_base()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kalman-v7430-") as td:
        src = Path(td) / "source"
        src.mkdir()
        decode_manifest(BASE_MANIFEST, src)
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
