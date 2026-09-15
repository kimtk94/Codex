from __future__ import annotations

import ast
import base64
import hashlib
import json
import lzma
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"
EXPECTED_SHA256 = "e1d68ef0744b1083be8c4ba32908f090e0f0b70742cb224df75c9596d06540f8"
PARTS = [ENGINE / f"_unified_payload_{i:02d}.b64" for i in range(15)]

encoded = "".join("".join(p.read_text(encoding="ascii").split()) for p in PARTS)
source_bytes = lzma.decompress(base64.b64decode(encoded, validate=True))
sha = hashlib.sha256(source_bytes).hexdigest()
if sha != EXPECTED_SHA256:
    raise SystemExit(f"payload sha mismatch: {sha}")
source = source_bytes.decode("utf-8")
tree = ast.parse(source, filename="Investment_Hub_Unified_Colab_v1.server.py")
lines = source.splitlines()

defs = []
imports = []
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        defs.append({
            "kind": type(node).__name__,
            "name": node.name,
            "lineno": node.lineno,
            "end_lineno": getattr(node, "end_lineno", node.lineno),
        })
    elif isinstance(node, ast.Import):
        imports.extend(a.name for a in node.names)
    elif isinstance(node, ast.ImportFrom):
        imports.append((node.module or "") + ":" + ",".join(a.name for a in node.names))

patterns = [
    "R5.1",
    "R5_1",
    "HGB",
    "HistGradientBoosting",
    "shadow_entry_this_signal",
    "selected_symbol",
    "reference_price",
    "target_price_4h",
    "score_semantics",
    "PREDICTED_RELATIVE_RET_4B",
    "60m",
    "1h",
    "interval",
    "yfinance",
    "yf.download",
    "history(",
    "model_output",
    "strategy_signal",
    "today_selector",
    "latest_model_picks",
    "allow_trade_shadow",
    "data_as_of",
    "RUN_MODE",
]

occurrences = []
seen = set()
for pat in patterns:
    for i, line in enumerate(lines, start=1):
        if pat.lower() in line.lower():
            key = (i, pat)
            if key in seen:
                continue
            seen.add(key)
            lo = max(1, i - 5)
            hi = min(len(lines), i + 5)
            occurrences.append({
                "pattern": pat,
                "lineno": i,
                "context": [
                    {"lineno": j, "text": lines[j - 1][:500]}
                    for j in range(lo, hi + 1)
                ],
            })

interesting_defs = [
    d for d in defs
    if re.search(
        r"(us|model|score|select|signal|feature|price|history|market|shadow|hgb|train|predict|rank)",
        d["name"],
        flags=re.I,
    )
]

report = {
    "payload_sha256": sha,
    "source_lines": len(lines),
    "imports": sorted(set(imports)),
    "interesting_definitions": sorted(interesting_defs, key=lambda x: x["lineno"]),
    "occurrences": sorted(occurrences, key=lambda x: (x["lineno"], x["pattern"])),
}

out = Path("unified_r5_introspection.json")
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({
    "status": "READY",
    "payload_sha256": sha,
    "source_lines": len(lines),
    "interesting_definitions": len(interesting_defs),
    "occurrences": len(occurrences),
    "artifact": str(out),
}, indent=2))
