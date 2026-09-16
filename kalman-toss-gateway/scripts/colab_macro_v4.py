from __future__ import annotations

import argparse
import json
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any


def run(cmd: list[str | Path], *, cwd: Path | None = None) -> None:
    args = [str(x) for x in cmd]
    print("\n$", " ".join(args))
    subprocess.run(args, cwd=cwd, check=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Kalman Macro Event V4 research runner"
    )
    p.add_argument("--drive-root", default="/content/drive/MyDrive")
    p.add_argument(
        "--macro-input",
        default="Market_Macro/v1/raw/us_macro_events_normalized.parquet",
    )
    p.add_argument(
        "--rates-context",
        default="Market_Macro/v1/rates/fred_rates_context.parquet",
    )
    p.add_argument(
        "--v3-candidate-tag", default="20260913_return_regime_v3_001"
    )
    p.add_argument(
        "--v4-candidate-tag", default="20260916_macro_event_v4_001"
    )
    p.add_argument("--code-sha", required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    app_root = Path(__file__).resolve().parents[1]
    repo_root = app_root.parent

    actual_sha = subprocess.check_output(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    if actual_sha != args.code_sha:
        raise RuntimeError(
            f"code SHA mismatch: {actual_sha} != {args.code_sha}"
        )

    drive = Path(args.drive_root)
    model_root = drive / "Market_Model_V2"
    matrix_v3 = model_root / "historical_matrices_v1"
    v3_root = (
        model_root
        / "historical_quant_2017_v3_candidate"
        / args.v3_candidate_tag
    )
    v4_matrix = model_root / "historical_matrices_v4_macro"
    v4_root = (
        model_root
        / "historical_quant_2017_v4_macro_candidate"
        / args.v4_candidate_tag
    )

    macro_input = drive / args.macro_input
    rates_context = drive / args.rates_context if str(args.rates_context).strip() else None
    macro_root = drive / "Market_Macro" / "v1"
    macro_features = macro_root / "features" / "macro_events_v1.parquet"
    status_path = v4_root / "macro_v4_colab_status.json"

    required = [
        macro_input,
        matrix_v3 / "us_matrix.parquet",
        matrix_v3 / "kr_matrix.parquet",
        matrix_v3 / "btc_matrix.parquet",
        v3_root / "candidate_run_status.json",
    ]
    if rates_context is not None:
        required.append(rates_context)
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "missing prerequisites: " + " | ".join(missing)
        )

    macro_spec = app_root / "config/macro-event-v1-spec.json"
    v4_spec = app_root / "config/model-v4-macro-event-spec.json"
    py = Path(sys.executable)
    v4_root.mkdir(parents=True, exist_ok=True)

    def status(
        phase: str,
        state: str = "RUNNING",
        **extra: Any,
    ) -> None:
        write_json(
            status_path,
            {
                "status": state,
                "phase": phase,
                "code_sha": actual_sha,
                "v4_candidate_tag": args.v4_candidate_tag,
                "macro_input": str(macro_input),
                "rates_context": str(rates_context) if rates_context else None,
                "research_only": True,
                "live_execution": False,
                "toss_execution": False,
                "neon_write": False,
                **extra,
            },
        )

    try:
        status("MACRO_EVENT_FEATURES")
        run(
            [
                py,
                "-m",
                "research.macro_event.build_macro_event_features",
                "--events",
                macro_input,
                "--spec",
                macro_spec,
                "--output",
                macro_features,
            ],
            cwd=app_root,
        )

        status("MERGE_MACRO_MATRIX")
        run(
            [
                py,
                "-m",
                "research.macro_event.merge_macro_v4",
                "--matrix-dir",
                matrix_v3,
                "--macro-events",
                macro_features,
                "--macro-spec",
                macro_spec,
                *(
                    ["--rates-context", rates_context]
                    if rates_context is not None
                    else []
                ),
                "--output-dir",
                v4_matrix,
            ],
            cwd=app_root,
        )

        status("V4_RETURN_REGIME")
        run(
            [
                py,
                "-m",
                "research.macro_event.run_macro_v4",
                "--matrix-dir",
                v4_matrix,
                "--baseline-v3-root",
                v3_root,
                "--spec",
                v4_spec,
                "--output-dir",
                v4_root,
                "--code-sha",
                actual_sha,
            ],
            cwd=app_root,
        )

        status("V3_V4_COMMON_WINDOW")
        comparison = v4_root / "v3_vs_v4_common_window.json"
        run(
            [
                py,
                "-m",
                "research.macro_event.compare_v3_v4",
                "--v3-root",
                v3_root,
                "--v4-root",
                v4_root,
                "--matrix-dir",
                v4_matrix,
                "--spec",
                v4_spec,
                "--output",
                comparison,
            ],
            cwd=app_root,
        )

        status(
            "DONE",
            "COMPLETE",
            comparison=str(comparison),
            macro_features=str(macro_features),
            rates_context=str(rates_context) if rates_context else None,
            matrix_dir=str(v4_matrix),
            output_root=str(v4_root),
        )
        print("\nCOMPLETE")
        print("Comparison:", comparison)
        return 0
    except Exception as exc:
        status(
            "FAILED",
            "FAIL",
            error_type=type(exc).__name__,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
