from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "kalman-hub-recovery/v7.4.20/source_manifest.ndjson"
REPORT = ROOT / "kalman-hub-recovery/v7.4.20/build_report.json"
HOTFIX = ROOT / "kalman-toss-gateway/scripts/runtime_hotfix_v7420_decision_console.js"
MARKER = "KALMAN_DECISION_CONSOLE_HOTFIX_V7422"
UI_VOCAB_VERSION = "kalman-ui-v1"
FORBIDDEN_VISIBLE_LABELS = [
    "DATA LIVE",
    "DATA CHECK",
    "MODEL ELIGIBLE NOW",
    "MODEL NOT ELIGIBLE NOW",
    "LIVE READY",
    "TRADING LINK ONLINE",
    "TRADING LINK OFFLINE",
    "BROKER LINK ONLINE",
    "BROKER LINK OFFLINE",
    "MODEL DATA FRESH",
    "MODEL DATA STALE",
    "MIRROR EMPTY",
]



def main() -> int:
    rows = [json.loads(x) for x in MANIFEST.read_text(encoding="utf-8").splitlines() if x.strip()]
    hit = False
    for row in rows:
        if row.get("file") != "app.js":
            continue
        app = base64.b64decode(row["data_b64"]).decode("utf-8")
        marker_idx = app.find("/* KALMAN_DECISION_CONSOLE_HOTFIX_V7422")
        if marker_idx >= 0:
            app = app[:marker_idx].rstrip()

        # Normalize legacy v7.4.20 visible labels before appending the current UI layer.
        app = app.replace(
            "function staleBadge(x){return x?badge('STALE','warn'):badge('LIVE','ok')}",
            "function staleBadge(x){return x?badge('스냅샷 만료','warn'):badge('스냅샷 유효','ok')}",
        )
        app = app.replace(
            "function stateLabel(stale){return '<span class=\"health-dot '+(stale?'warn-dot':'good-dot')+'\"></span>'+(stale?'STALE':'FRESH');}",
            "function stateLabel(stale){return '<span class=\"health-dot '+(stale?'warn-dot':'good-dot')+'\"></span>'+(stale?'스냅샷 만료':'스냅샷 유효');}",
        )
        app = app.replace("live?'DATA LIVE':'DATA CHECK'", "live?'데이터 정상':'데이터 확인 필요'")
        app = app.replace("LIVE RANKING", "모델 순위")

        patch = HOTFIX.read_text(encoding="utf-8").strip()
        if MARKER not in patch:
            raise SystemExit("hotfix marker missing")
        app = app + "\n\n" + patch + "\n"
        if UI_VOCAB_VERSION not in app:
            raise SystemExit("UI vocabulary marker missing")
        forbidden = [x for x in FORBIDDEN_VISIBLE_LABELS if x in app]
        if forbidden:
            raise SystemExit(f"legacy UI labels remain: {forbidden}")
        row["data_b64"] = base64.b64encode(app.encode("utf-8")).decode("ascii")
        hit = True
        break
    if not hit:
        raise SystemExit("app.js row missing")

    text = "\n".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in rows) + "\n"
    MANIFEST.write_text(text, encoding="utf-8")

    report = json.loads(REPORT.read_text(encoding="utf-8"))
    report["runtime_hotfix"] = "v7.4.22-decision-console"
    report["runtime_hotfix_manifest_only"] = True
    report["ui_vocabulary_contract"] = UI_VOCAB_VERSION
    report["source_manifest_sha256"] = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": "HOTFIXED",
        "manifest": str(MANIFEST.relative_to(ROOT)),
        "marker": MARKER,
        "source_manifest_sha256": report["source_manifest_sha256"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
