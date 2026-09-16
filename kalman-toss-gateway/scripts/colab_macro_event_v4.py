from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any


def run(cmd: list[str | Path], *, cwd: Path | None = None) -> None:
    args = [str(x) for x in cmd]
    print("\n$", " ".join(args))
    subprocess.run(args, cwd=cwd, check=True)


def capture(cmd: list[str | Path], *, cwd: Path | None = None) -> str:
    out = subprocess.check_output(
        [str(x) for x in cmd], cwd=cwd, text=True, stderr=subprocess.STDOUT
    )
    print(out, end="" if out.endswith("\n") else "\n")
    return out.strip()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Kalman Macro Event V4 historical research runner"
    )
    p.add_argument("--drive-root", default="/content/drive/MyDrive")
    p.add_argument("--start-date", default="2017-01-01")
    p.add_argument(
        "--end-date",
        default=datetime.now().astimezone().date().isoformat(),
    )
    p.add_argument(
        "--normalized-events",
        default="",
        help="Optional prebuilt normalized event parquet. If absent, TE PIT is fetched.",
    )
    p.add_argument(
        "--v3-tag",
        default="20260913_return_regime_v3_001",
    )
    p.add_argument(
        "--v2-tag",
        default="20260913_nested_v2_001",
    )
    p.add_argument(
        "--v4-tag",
        default="20260916_macro_event_v4_001",
    )
    p.add_argument("--pinned-code-sha", default="")
    return p.parse_args()


def locate_model_root(drive_root: Path) -> Path:
    candidates = [
        drive_root / "Market_Model_V2",
        drive_root / "Kalman" / "Market_Model_V2",
        drive_root / "kalman" / "Market_Model_V2",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Market_Model_V2 not found")


def assert_inputs(model_root: Path, v3_tag: str, v2_tag: str) -> tuple[Path, Path, Path]:
    matrix_dir = model_root / "historical_matrices_v1"
    v3_root = (
        model_root
        / "historical_quant_2017_v3_candidate"
        / v3_tag
    )
    v2_root = (
        model_root
        / "historical_quant_2017_v2_candidate"
        / v2_tag
    )
    required = [
        matrix_dir / "us_matrix.parquet",
        matrix_dir / "kr_matrix.parquet",
        matrix_dir / "btc_matrix.parquet",
        v3_root / "us" / "historical_strategy_signal.parquet",
        v3_root / "kr" / "historical_strategy_signal.parquet",
        v3_root / "btc" / "historical_strategy_signal.parquet",
    ]
    missing = [str(x) for x in required if not x.exists()]
    if missing:
        raise FileNotFoundError("missing historical prerequisites: " + " | ".join(missing))
    return matrix_dir, v3_root, v2_root


def main() -> int:
    args = parse_args()
    drive_root = Path(args.drive_root).expanduser()
    if not drive_root.exists():
        raise FileNotFoundError(f"Drive root not mounted: {drive_root}")

    app_root = Path(__file__).resolve().parents[1]
    repo_root = app_root.parent
    code_sha = capture(["git", "-C", repo_root, "rev-parse", "HEAD"])
    if args.pinned_code_sha and code_sha != args.pinned_code_sha:
        raise RuntimeError(
            f"pinned code mismatch: {code_sha} != {args.pinned_code_sha}"
        )

    model_root = locate_model_root(drive_root)
    matrix_dir, v3_root, v2_root = assert_inputs(
        model_root, args.v3_tag, args.v2_tag
    )

    macro_root = drive_root / "Market_Macro" / "v1"
    raw_dir = macro_root / "raw"
    feature_dir = macro_root / "features"
    raw_dir.mkdir(parents=True, exist_ok=True)
    feature_dir.mkdir(parents=True, exist_ok=True)

    out_root = (
        model_root
        / "historical_quant_2017_v4_macro_candidate"
        / args.v4_tag
    )
    out_root.mkdir(parents=True, exist_ok=True)
    matrix_v4_dir = out_root / "macro_matrices"
    model_v4_root = out_root / "model"
    status_path = out_root / "macro_v4_runner_status.json"

    macro_spec = app_root / "config/macro-event-v1-spec.json"
    model_spec = app_root / "config/model-v4-macro-event-spec.json"

    def status(phase: str, state: str = "RUNNING", **extra: Any) -> None:
        write_json(
            status_path,
            {
                "status": state,
                "phase": phase,
                "code_sha": code_sha,
                "v3_tag": args.v3_tag,
                "v4_tag": args.v4_tag,
                "research_only": True,
                "live_execution": False,
                "toss_execution": False,
                "neon_write": False,
                **extra,
            },
        )

    try:
        status("TESTS")
        run(
            [sys.executable, "-m", "pytest", "-q", "tests/test_macro_event_v1.py"],
            cwd=app_root,
        )

        status("EVENT_SOURCE")
        if args.normalized_events:
            normalized_events = Path(args.normalized_events).expanduser()
            if not normalized_events.exists():
                raise FileNotFoundError(normalized_events)
        else:
            normalized_events = raw_dir / (
                f"tradingeconomics_pit_{args.start_date}_{args.end_date}.parquet"
            )
            run(
                [
                    sys.executable,
                    "-m",
                    "research.macro_event.collect_tradingeconomics_pit",
                    "--spec",
                    macro_spec,
                    "--start-date",
                    args.start_date,
                    "--end-date",
                    args.end_date,
                    "--output",
                    normalized_events,
                ],
                cwd=app_root,
            )

        status("MACRO_FEATURES")
        macro_features = feature_dir / (
            f"macro_event_features_{args.start_date}_{args.end_date}.parquet"
        )
        run(
            [
                sys.executable,
                "-m",
                "research.macro_event.build_macro_event_features",
                "--events",
                normalized_events,
                "--spec",
                macro_spec,
                "--output",
                macro_features,
            ],
            cwd=app_root,
        )

        status("MATRIX_MERGE")
        if matrix_v4_dir.exists():
            shutil.rmtree(matrix_v4_dir)
        run(
            [
                sys.executable,
                "-m",
                "research.macro_event.merge_macro_v4",
                "--matrix-dir",
                matrix_dir,
                "--macro-events",
                macro_features,
                "--macro-spec",
                macro_spec,
                "--output-dir",
                matrix_v4_dir,
            ],
            cwd=app_root,
        )

        status("V4_WALK_FORWARD")
        if model_v4_root.exists():
            shutil.rmtree(model_v4_root)
        model_v4_root.mkdir(parents=True, exist_ok=True)
        run(
            [
                sys.executable,
                "-m",
                "research.quant_stack.historical_v3_return_regime",
                "--matrix-dir",
                matrix_v4_dir,
                "--v2-root",
                v2_root,
                "--spec",
                model_spec,
                "--output-dir",
                model_v4_root,
                "--code-sha",
                code_sha,
            ],
            cwd=app_root,
        )

        status("V3_V4_COMMON_WINDOW")
        comparison = out_root / "v3_vs_v4_common_window.json"
        run(
            [
                sys.executable,
                "-m",
                "research.macro_event.compare_v3_v4",
                "--v3-root",
                v3_root,
                "--v4-root",
                model_v4_root,
                "--matrix-dir",
                matrix_dir,
                "--spec",
                model_spec,
                "--output",
                comparison,
            ],
            cwd=app_root,
        )

        status(
            "DONE",
            "COMPLETE",
            normalized_events=str(normalized_events),
            macro_features=str(macro_features),
            matrix_v4_dir=str(matrix_v4_dir),
            model_v4_root=str(model_v4_root),
            comparison=str(comparison),
        )
        print("\nMACRO V4 COMPLETE")
        print(comparison.read_text(encoding="utf-8"))
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
