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


def run(
    cmd: list[str | Path],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> int:
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
    out = subprocess.check_output(args, cwd=cwd, text=True, stderr=subprocess.STDOUT)
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


def create_venv(path: Path, *, python_executable: str | Path | None = None) -> None:
    if path.exists():
        shutil.rmtree(path)
    py = str(python_executable or sys.executable)
    try:
        run([py, "-m", "venv", path])
    except subprocess.CalledProcessError:
        run([sys.executable, "-m", "pip", "install", "-q", "virtualenv"])
        run([sys.executable, "-m", "virtualenv", "-p", py, path])
    if not (path / "bin/python").exists():
        raise RuntimeError(f"failed to create virtualenv: {path}")


def ensure_uv() -> str:
    uv = shutil.which("uv")
    if uv:
        return uv
    run([sys.executable, "-m", "pip", "install", "-q", "uv"])
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv installation succeeded but executable was not found")
    return uv


def locate_source_run(drive_root: Path, source_run_tag: str) -> Path:
    candidates = [
        drive_root / "Market_Model_V2" / "historical_quant_2017_v1" / source_run_tag,
        drive_root / "Kalman" / "Market_Model_V2" / "historical_quant_2017_v1" / source_run_tag,
        drive_root / "kalman" / "Market_Model_V2" / "historical_quant_2017_v1" / source_run_tag,
    ]
    for candidate in candidates:
        if (candidate / "historical_resume_complete.json").exists():
            return candidate
    raise FileNotFoundError(f"source historical run not found: {source_run_tag}")


def locate_matrix_dir(source_run: Path) -> Path:
    model_root = source_run.parents[1]
    candidate = model_root / "historical_matrices_v1"
    if all((candidate / f"{m}_matrix.parquet").exists() for m in ("us", "kr", "btc")):
        return candidate
    raise FileNotFoundError(f"historical matrix directory not found: {candidate}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kalman Historical V2 nested candidate Colab runner")
    p.add_argument("--drive-root", default="/content/drive/MyDrive")
    p.add_argument("--source-run-tag", default="20260913_042850")
    p.add_argument("--candidate-tag", default="20260913_nested_v2_001")
    p.add_argument("--pinned-code-sha", required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    drive_root = Path(args.drive_root)
    if not drive_root.exists():
        raise FileNotFoundError(f"Drive root not mounted: {drive_root}")

    app_root = Path(__file__).resolve().parents[1]
    repo_root = app_root.parent
    code_sha = capture(["git", "-C", repo_root, "rev-parse", "HEAD"])
    if code_sha != args.pinned_code_sha:
        raise RuntimeError(f"pinned code mismatch: {code_sha} != {args.pinned_code_sha}")

    source_run = locate_source_run(drive_root, args.source_run_tag)
    matrix_dir = locate_matrix_dir(source_run)
    model_root = source_run.parents[1]
    output_root = model_root / "historical_quant_2017_v2_candidate" / args.candidate_tag
    output_root.mkdir(parents=True, exist_ok=True)
    status_path = output_root / "candidate_colab_status.json"

    source_complete = json.loads(
        (source_run / "historical_resume_complete.json").read_text(encoding="utf-8")
    )
    if source_complete.get("status") != "COMPLETE":
        raise RuntimeError("source historical run is not COMPLETE")
    if source_complete.get("market_backtests_rerun") is not False:
        raise RuntimeError("source provenance invariant failed")

    def status(phase: str, state: str = "RUNNING", **extra: Any) -> None:
        write_json(
            status_path,
            {
                "status": state,
                "phase": phase,
                "source_run_tag": args.source_run_tag,
                "candidate_tag": args.candidate_tag,
                "code_sha": code_sha,
                "source_historical_reused": True,
                "source_backtests_rerun": False,
                "research_only": True,
                "live_execution": False,
                "toss_execution": False,
                "neon_write": False,
                **extra,
            },
        )

    core_venv = Path("/content/.venv-kalman-historical-v2-candidate")
    risk_venv = Path("/content/.venv-kalman-historical-v2-candidate-riskfolio")
    qlib_venv = Path("/content/.venv-kalman-historical-v2-candidate-qlib312")

    spec = app_root / "config/model-v2-historical-candidate-spec.json"
    pypfopt_req = app_root / "research/quant_stack/requirements-pypfopt.txt"
    risk_req = app_root / "research/quant_stack/requirements-riskfolio.txt"
    qlib_req = app_root / "research/quant_stack/requirements-qlib.txt"

    tool_status: dict[str, str] = {}

    try:
        status("CORE_ENV")
        create_venv(core_venv)
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
        run([
            core_py,
            "-m",
            "py_compile",
            app_root / "research/quant_stack/historical_v2_candidate.py",
            app_root / "research/quant_stack/historical_v2_candidate_riskfolio.py",
            app_root / "research/quant_stack/historical_v2_candidate_qlib.py",
        ])

        status("NESTED_CANDIDATE")
        run([
            core_py,
            "-m",
            "research.quant_stack.historical_v2_candidate",
            "--matrix-dir",
            matrix_dir,
            "--spec",
            spec,
            "--output-dir",
            output_root,
            "--git-sha",
            code_sha,
        ], cwd=app_root)
        tool_status["nested_candidate"] = "READY"

        status("RISKFOLIO")
        try:
            create_venv(risk_venv)
            risk_py = risk_venv / "bin/python"
            risk_pip = risk_venv / "bin/pip"
            run([risk_pip, "install", "-q", "-r", risk_req])
            run([risk_pip, "check"])
            env = os.environ.copy()
            env["PYTHONPATH"] = str(app_root)
            run([
                risk_py,
                "-m",
                "research.quant_stack.historical_v2_candidate_riskfolio",
                "--output-dir",
                output_root,
            ], cwd=app_root, env=env)
            tool_status["riskfolio"] = "READY"
        except Exception as exc:
            tool_status["riskfolio"] = f"FAIL: {type(exc).__name__}: {exc}"
            print("RISKFOLIO DEGRADED:", tool_status["riskfolio"])

        status("QLIB_PYTHON_3_12")
        try:
            uv = ensure_uv()
            run([uv, "python", "install", "3.12"])
            if qlib_venv.exists():
                shutil.rmtree(qlib_venv)
            run([uv, "venv", "--python", "3.12", qlib_venv])
            qlib_py = qlib_venv / "bin/python"
            run([
                uv,
                "pip",
                "install",
                "--python",
                qlib_py,
                "-q",
                "pandas",
                "numpy",
                "pyarrow",
                "scikit-learn",
                "-r",
                qlib_req,
            ])
            run([uv, "pip", "check", "--python", qlib_py])
            py_version = capture([
                qlib_py,
                "-c",
                "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
            ])
            if py_version != "3.12":
                raise RuntimeError(f"Qlib environment must use Python 3.12, got {py_version}")

            tracking_root = model_root / "qlib_mlruns_historical_v2_candidate"
            provider_root = Path("/content/qlib_provider_historical_v2_candidate")
            run([
                qlib_py,
                "-m",
                "research.quant_stack.historical_v2_candidate_qlib",
                "--output-dir",
                output_root,
                "--tracking-root",
                tracking_root,
                "--provider-root",
                provider_root,
                "--experiment-name",
                "kalman_historical_v2_nested_candidate",
            ], cwd=app_root)
            tool_status["qlib"] = "READY"
        except Exception as exc:
            tool_status["qlib"] = f"FAIL: {type(exc).__name__}: {exc}"
            print("QLIB DEGRADED:", tool_status["qlib"])

        status("FINAL_SUMMARY")
        candidate_status = json.loads(
            (output_root / "candidate_run_status.json").read_text(encoding="utf-8")
        )
        portfolio_rows: list[dict[str, Any]] = []
        for name in ("core_portfolio_comparison.csv", "riskfolio_portfolio_comparison.csv"):
            path = output_root / "portfolio" / name
            if path.exists():
                import pandas as pd
                portfolio_rows.extend(pd.read_csv(path).to_dict("records"))

        if portfolio_rows:
            import pandas as pd
            comparison = pd.DataFrame(portfolio_rows)
            comparison["sharpe"] = pd.to_numeric(comparison["sharpe"], errors="coerce")
            comparison["cagr"] = pd.to_numeric(comparison["cagr"], errors="coerce")
            comparison = comparison.sort_values(
                ["sharpe", "cagr"],
                ascending=[False, False],
                na_position="last",
            )
            comparison.to_csv(output_root / "portfolio_comparison_all.csv", index=False)
            ranking = comparison.to_dict("records")
        else:
            ranking = []

        final = {
            "status": "COMPLETE",
            "source_run_tag": args.source_run_tag,
            "candidate_tag": args.candidate_tag,
            "code_sha": code_sha,
            "candidate": candidate_status,
            "portfolio_ranking": ranking,
            "tool_status": tool_status,
            "research_only": True,
            "live_execution": False,
            "toss_execution": False,
            "neon_write": False,
            "promotion_recommendation": "RESEARCH_ONLY",
        }
        write_json(output_root / "historical_v2_candidate_summary.json", final)
        status(
            "DONE",
            state="COMPLETE",
            tool_status=tool_status,
            summary=str(output_root / "historical_v2_candidate_summary.json"),
        )
        print("\n" + "=" * 90)
        print("KALMAN HISTORICAL V2 NESTED CANDIDATE COMPLETE")
        print("=" * 90)
        print(output_root / "historical_v2_candidate_summary.json")
        print(json.dumps(tool_status, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        status(
            "FAILED",
            state="FAIL",
            error_type=type(exc).__name__,
            error=str(exc),
            traceback=traceback.format_exc(),
            tool_status=tool_status,
        )
        traceback.print_exc()
        raise


if __name__ == "__main__":
    raise SystemExit(main())
