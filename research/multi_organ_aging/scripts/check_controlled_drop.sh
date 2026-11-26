#!/usr/bin/env bash
set +e
set +u
set +o pipefail 2>/dev/null || true

BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="/srv/is-analysis"
INPUT_DIR="${1:-$ROOT/data/multi_organ_aging/controlled}"
RESULTS="${2:-$ROOT/results/multi_organ_aging/controlled_analysis}"
CONFIG="${3:-$BASE/config/multi_organ_aging.json}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venvs/multi_organ_aging/bin/python}"

echo "============================================================"
echo "MULTI-ORGAN AGING — CONTROLLED DROP INSPECTOR"
echo "============================================================"
echo "INPUT_DIR=$INPUT_DIR"
echo "RESULTS=$RESULTS"
echo "CONFIG=$CONFIG"
echo

if [ ! -d "$INPUT_DIR" ]; then
  echo "STATUS=HOLD"
  echo "REASON=controlled_input_dir_missing"
  echo "SHELL_STILL_ALIVE"
  return 0 2>/dev/null || true
fi

echo "===== FILE INVENTORY ====="
find "$INPUT_DIR" -maxdepth 2 -type f \
  \( -iname '*.txt' -o -iname '*.txt.gz' -o -iname '*.tsv' -o -iname '*.tsv.gz' -o -iname '*.csv' -o -iname '*.csv.gz' \) \
  -printf '%s\t%p\n' 2>/dev/null | sort -nr

echo
echo "===== PRIVACY-SAFE SCHEMA AUDIT ====="

"$PYTHON_BIN" - "$INPUT_DIR" <<'PY'
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
supported = {".txt", ".tsv", ".csv", ".gz"}
visit_re = re.compile(r"^A(\d{2})_", re.I)

def open_text(path: Path):
    if path.name.lower().endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8-sig", errors="ignore")
    return path.open("r", encoding="utf-8-sig", errors="ignore")

def sniff(line: str) -> str:
    tabs = line.count("\t")
    commas = line.count(",")
    return "\t" if tabs >= commas else ","

rows = []
for path in sorted(root.rglob("*")):
    if not path.is_file():
        continue
    lname = path.name.lower()
    if not any(lname.endswith(x) for x in [".txt", ".txt.gz", ".tsv", ".tsv.gz", ".csv", ".csv.gz"]):
        continue

    size = path.stat().st_size
    sha = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                sha.update(chunk)
    except Exception:
        pass

    header = ""
    try:
        with open_text(path) as fh:
            header = fh.readline(2_000_000).rstrip("\r\n")
    except Exception as exc:
        rows.append({
            "file": str(path),
            "bytes": size,
            "sha256": sha.hexdigest(),
            "status": f"read_error:{type(exc).__name__}",
        })
        continue

    delim = sniff(header)
    try:
        cols = next(csv.reader([header], delimiter=delim))
    except Exception:
        cols = header.split(delim)

    visits = sorted({
        int(m.group(1))
        for c in cols
        for m in [visit_re.match(c.strip())]
        if m
    })

    upper = {c.strip().upper() for c in cols}
    sensitive_name_hits = sorted(
        c for c in upper
        if any(k in c for k in ["NAME", "PHONE", "TEL", "MOBILE", "ADDRESS", "EMAIL", "RRN", "SSN"])
    )

    key_hits = [
        k for k in [
            "DIST_ID",
            "A01_AGE",
            "A01_EDATE",
            "A01_SEX",
            "A01_BUN",
            "A01_CREATININ",
            "A01_GLU0",
            "A01_HBA1C",
            "A01_AST",
            "A01_ALT",
            "A01_WBC_B",
            "A01_HB",
            "A01_PLAT",
            "A01_SP1_2",
            "A01_SP2_2",
            "A01_SP3_2",
        ]
        if k in upper
    ]

    rows.append({
        "file": str(path),
        "bytes": size,
        "sha256": sha.hexdigest(),
        "status": "ok",
        "delimiter": "TAB" if delim == "\t" else "COMMA",
        "n_columns": len(cols),
        "integrated_visit_numbers": visits,
        "n_integrated_visits": len(visits),
        "key_columns_detected": key_hits,
        "possible_direct_identifier_columns": sensitive_name_hits,
    })

print(json.dumps(rows, ensure_ascii=False, indent=2))

files = [x for x in rows if x.get("status") == "ok"]
integrated = [x for x in files if x.get("n_integrated_visits", 0) >= 3]

if not files:
    print("\nSTATUS=HOLD")
    print("REASON=no_supported_files_found")
elif integrated:
    max_visits = max(x["n_integrated_visits"] for x in integrated)
    print("\nSTATUS=DATA_DETECTED")
    print(f"INTEGRATED_WIDE_FILES={len(integrated)}")
    print(f"MAX_INTEGRATED_VISITS={max_visits}")
else:
    print("\nSTATUS=DATA_DETECTED")
    print("INTEGRATED_WIDE_FILES=0")
    print("NOTE=files_present_but_not_detected_as_Axx_integrated_wide")
PY

SCHEMA_RC=$?

echo
echo "SCHEMA_RC=$SCHEMA_RC"

echo
echo "===== READINESS ====="

"$PYTHON_BIN"   "$BASE/src/stage0c_controlled_readiness.py"   --config "$CONFIG"   --input-dir "$INPUT_DIR"   --out-dir "$RESULTS"

READINESS_RC=$?

echo
echo "READINESS_RC=$READINESS_RC"

SUMMARY="$RESULTS/stage0c_controlled_readiness/CONTROLLED_READINESS_SUMMARY.json"

if [ -f "$SUMMARY" ]; then
  echo
  echo "===== READINESS SUMMARY ====="
  cat "$SUMMARY"
fi

echo
echo "============================================================"
echo "NEXT ACTION"
echo "============================================================"

"$PYTHON_BIN" - "$SUMMARY" <<'PY'
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])

if not p.exists():
    print("HOLD — readiness summary missing.")
    raise SystemExit(0)

try:
    x = json.loads(p.read_text(encoding="utf-8"))
except Exception:
    print("HOLD — readiness summary unreadable.")
    raise SystemExit(0)

status = x.get("go_no_go", "HOLD")
print("GO_NO_GO =", status)

if status == "GO":
    print("NEXT = bash scripts/run_controlled_core.sh")
else:
    print("NEXT = do not run Stage 1+; inspect missing schema/data requirements.")
PY

echo
echo "SHELL_STILL_ALIVE"
