from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any


def run(cmd: list[str | Path], *, cwd: Path | None = None, env: dict[str, str] | None = None, check: bool = True) -> int:
    args = [str(x) for x in cmd]
    print("\n$", " ".join(args))
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        print(line, end="")
    code = proc.wait()
    if check and code != 0:
        raise subprocess.CalledProcessError(code, args)
    return code


def capture(cmd: list[str | Path], *, cwd: Path | None = None) -> str:
    args = [str(x) for x in cmd]
    print("\n$", " ".join(args))
    output = subprocess.check_output(args, cwd=cwd, text=True, stderr=subprocess.STDOUT)
    print(output, end="" if output.endswith("\n") else "\n")
    return output.strip()


def create_venv(path: Path, *, recreate: bool) -> None:
    if recreate and path.exists():
        shutil.rmtree(path)
    if (path / "bin/python").exists():
        return
    try:
        run([sys.executable, "-m", "venv", path])
    except subprocess.CalledProcessError:
        run([sys.executable, "-m", "pip", "install", "-q", "virtualenv"])
        run([sys.executable, "-m", "virtualenv", path])
    if not (path / "bin/python").exists():
        raise RuntimeError(f"failed to create virtualenv: {path}")


def locate_output(drive_root: Path, run_tag: str) -> Path:
    candidates = [
        drive_root / "Market_Model_V2" / "historical_quant_2017_v1" / run_tag,
        drive_root / "Kalman" / "Market_Model_V2" / "historical_quant_2017_v1" / run_tag,
        drive_root / "kalman" / "Market_Model_V2" / "historical_quant_2017_v1" / run_tag,
    ]
    for candidate in candidates:
        if (candidate / "historical_experiment_status.json").exists():
            return candidate
    raise FileNotFoundError(f"historical run {run_tag} not found under Drive")


def locate_matrix_dir(output_root: Path) -> Path:
    model_root = output_root.parents[1]
    candidates = [
        model_root / "historical_matrices_v1",
        output_root.parent.parent / "historical_matrices_v1",
    ]
    for candidate in candidates:
        if all((candidate / f"{m}_matrix.parquet").exists() for m in ("us", "kr", "btc")):
            return candidate
    raise FileNotFoundError("historical_matrices_v1 with US/KR/BTC matrices not found")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kalman Historical V2 analysis Colab runner")
    p.add_argument("--drive-root", default="/content/drive/MyDrive")
    p.add_argument("--run-tag", default="20260913_042850")
    p.add_argument("--pinned-code-sha", required=True)
    p.add_argument("--keep-venvs", action="store_true")
    p.add_argument("--permutation-repeats", type=int, default=3)
    p.add_argument("--disable-qlib", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    drive_root = Path(args.drive_root)
    if not drive_root.exists():
        raise FileNotFoundError(f"Drive root not mounted: {drive_root}")

    app_root = Path(__file__).resolve().parents[1]
    repo_root = app_root.parent
    output_root = locate_output(drive_root, args.run_tag)
    matrix_dir = locate_matrix_dir(output_root)
    analysis_dir = output_root / "analysis_v2"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    status_path = analysis_dir / "analysis_run_status.json"

    head = capture(["git", "-C", repo_root, "rev-parse", "HEAD"])
    if head != args.pinned_code_sha:
        raise RuntimeError(
            f"pinned code mismatch: notebook={args.pinned_code_sha} checkout={head}"
        )

    complete_path = output_root / "historical_resume_complete.json"
    if complete_path.exists():
        complete = json.loads(complete_path.read_text(encoding="utf-8"))
        if complete.get("status") != "COMPLETE":
            raise RuntimeError("historical resume is not COMPLETE")
        if complete.get("market_backtests_rerun") is not False:
            raise RuntimeError("historical provenance invariant failed")

    print("OUTPUT_ROOT :", output_root)
    print("MATRIX_DIR  :", matrix_dir)
    print("CODE_SHA    :", head)
    print("SAFETY      : RESEARCH ONLY / NO NEON WRITE / NO TOSS")

    def status(phase: str, state: str = "RUNNING", **extra: Any) -> None:
        write_json(
            status_path,
            {
                "status": state,
                "phase": phase,
                "run_tag": args.run_tag,
                "code_sha": head,
                "historical_reused": True,
                "market_backtests_rerun": False,
                "research_only": True,
                "live_execution": False,
                "toss_execution": False,
                "neon_write": False,
                **extra,
            },
        )

    core_venv = Path("/content/.venv-kalman-historical-v2-core")
    vector_venv = Path("/content/.venv-kalman-historical-v2-vectorbt")
    risk_venv = Path("/content/.venv-kalman-historical-v2-riskfolio")
    qlib_venv = Path("/content/.venv-kalman-historical-v2-qlib")

    pypfopt_req = app_root / "research/quant_stack/requirements-pypfopt.txt"
    vector_req = app_root / "research/market_tools/requirements.txt"
    risk_req = app_root / "research/quant_stack/requirements-riskfolio.txt"
    qlib_req = app_root / "research/quant_stack/requirements-qlib.txt"

    external_status: dict[str, str] = {}

    try:
        status("CORE_ENV")
        create_venv(core_venv, recreate=not args.keep_venvs)
        core_py = core_venv / "bin/python"
        core_pip = core_venv / "bin/pip"
        run([
            core_pip,
            "install",
            "-q",
            "pandas",
            "numpy",
            "scikit-learn",
            "pyarrow",
            "python-dotenv",
            "-r",
            pypfopt_req,
        ])
        run([core_pip, "check"])

        status("IMMUTABLE_PREFLIGHT")
        run([
            core_py,
            "-m",
            "research.quant_stack.resume_postprocess",
            "--output-dir",
            output_root,
            "--preflight-only",
        ], cwd=app_root)

        status("PROVENANCE")
        run([
            core_py,
            "-m",
            "research.quant_stack.historical_v2_analysis",
            "--output-dir",
            output_root,
            "--mode",
            "provenance",
            "--analysis-git-sha",
            head,
            "--pinned-code-sha",
            args.pinned_code_sha,
        ], cwd=app_root)

        status("CORE_BENCHMARK_AND_FEATURE_OOS")
        run([
            core_py,
            "-m",
            "research.quant_stack.historical_v2_analysis",
            "--output-dir",
            output_root,
            "--matrix-dir",
            matrix_dir,
            "--mode",
            "core",
            "--permutation-repeats",
            str(args.permutation_repeats),
        ], cwd=app_root)
        external_status["core"] = "READY"

        status("VECTORBT")
        try:
            create_venv(vector_venv, recreate=not args.keep_venvs)
            vector_py = vector_venv / "bin/python"
            vector_pip = vector_venv / "bin/pip"
            run([vector_pip, "install", "-q", "-r", vector_req])
            run([vector_pip, "check"])
            code = run([
                vector_py,
                "-m",
                "research.quant_stack.historical_v2_vectorbt",
                "--output-dir",
                output_root,
                "--matrix-dir",
                matrix_dir,
                "--max-hold-bars",
                "20",
            ], cwd=app_root, check=False)
            external_status["vectorbt"] = "READY" if code == 0 else "DEGRADED"
        except Exception as exc:
            external_status["vectorbt"] = f"FAIL: {type(exc).__name__}: {exc}"
            print("VECTORBT DEGRADED:", external_status["vectorbt"])

        status("RISKFOLIO")
        try:
            create_venv(risk_venv, recreate=not args.keep_venvs)
            risk_py = risk_venv / "bin/python"
            risk_pip = risk_venv / "bin/pip"
            run([risk_pip, "install", "-q", "-r", risk_req])
            run([risk_pip, "check"])
            env = os.environ.copy()
            env["PYTHONPATH"] = str(app_root)
            run([
                risk_py,
                "-m",
                "research.quant_stack.historical_v2_riskfolio",
                "--output-dir",
                output_root,
                "--lookback-days",
                "180",
                "--min-observations",
                "90",
                "--rebalance",
                "M",
            ], cwd=app_root, env=env)
            external_status["riskfolio"] = "READY"
        except Exception as exc:
            external_status["riskfolio"] = f"FAIL: {type(exc).__name__}: {exc}"
            print("RISKFOLIO DEGRADED:", external_status["riskfolio"])

        status("QLIB")
        if args.disable_qlib:
            external_status["qlib"] = "DISABLED"
        else:
            try:
                create_venv(qlib_venv, recreate=not args.keep_venvs)
                qlib_py = qlib_venv / "bin/python"
                qlib_pip = qlib_venv / "bin/pip"
                run([
                    qlib_pip,
                    "install",
                    "-q",
                    "pandas",
                    "numpy",
                    "pyarrow",
                    "scikit-learn",
                    "-r",
                    qlib_req,
                ])
                run([qlib_pip, "check"])
                model_root = output_root.parents[1]
                tracking_root = model_root / "qlib_mlruns_historical_v2_analysis"
                provider_root = Path("/content/qlib_provider_historical_v2_analysis")
                run([
                    qlib_py,
                    "-m",
                    "research.quant_stack.historical_v2_analysis",
                    "--output-dir",
                    output_root,
                    "--mode",
                    "qlib",
                    "--qlib-tracking-root",
                    tracking_root,
                    "--qlib-provider-root",
                    provider_root,
                    "--qlib-experiment-name",
                    "kalman_historical_2017_v2_analysis",
                ], cwd=app_root)
                external_status["qlib"] = "READY"
            except Exception as exc:
                external_status["qlib"] = f"FAIL: {type(exc).__name__}: {exc}"
                print("QLIB DEGRADED:", external_status["qlib"])

        status("FINAL_SUMMARY")
        run([
            core_py,
            "-m",
            "research.quant_stack.historical_v2_analysis",
            "--output-dir",
            output_root,
            "--mode",
            "summary",
        ], cwd=app_root)

        summary_path = analysis_dir / "historical_v2_analysis_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["tool_status"] = external_status
        write_json(summary_path, summary)

        status("DONE", state="COMPLETE", tool_status=external_status, summary=str(summary_path))
        print("\n" + "=" * 88)
        print("KALMAN HISTORICAL V2 ANALYSIS COMPLETE")
        print("=" * 88)
        print("SUMMARY:", summary_path)
        print(json.dumps(external_status, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        status(
            "FAILED",
            state="FAIL",
            error_type=type(exc).__name__,
            error=str(exc),
            tool_status=external_status,
        )
        traceback.print_exc()
        raise


if __name__ == "__main__":
    raise SystemExit(main())
