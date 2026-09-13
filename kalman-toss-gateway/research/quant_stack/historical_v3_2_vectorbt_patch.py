from __future__ import annotations

import argparse
import json
from pathlib import Path

from .historical_v3_2_portfolio_validation import run_vectorbt_validation_v32


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run only the Kalman V3.2 vectorbt parity validation"
    )
    p.add_argument("--v3-root", required=True)
    p.add_argument("--matrix-dir", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--output-dir", required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    v3_root = Path(args.v3_root).expanduser()
    matrix_dir = Path(args.matrix_dir).expanduser()
    spec_path = Path(args.spec).expanduser()
    output_root = Path(args.output_dir).expanduser()
    output_root.mkdir(parents=True, exist_ok=True)

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    result = run_vectorbt_validation_v32(
        v3_root=v3_root,
        matrix_dir=matrix_dir,
        spec=spec,
        output_root=output_root,
    )
    summary_path = output_root / "vectorbt_patch_summary.json"
    summary_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("status") != "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
