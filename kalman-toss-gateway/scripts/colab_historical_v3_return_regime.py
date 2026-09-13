from __future__ import annotations

import argparse
import json
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
    out = subprocess.check_output(
        [str(x) for x in cmd],
        cwd=cwd,
        text=True,
        stderr=subprocess.STDOUT,
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
        raise RuntimeError("uv executable not found after installation")
    return uv


def locate_v1_run(drive_root: Path, run_tag: str) -> Path:
    candidates = [
        drive_root / "Market_Model_V2" / "historical_quant_2017_v1" / run_tag,
        drive_root / "Kalman" / "Market_Model_V2" / "historical_quant_2017_v1" / run_tag,
        drive_root / "kalman" / "Market_Model_V2" / "historical_quant_2017_v1" / run_tag,
    ]
    for candidate in candidates:
        if (candidate / "historical_resume_complete.json").exists():
            return candidate
    raise FileNotFoundError(f"V1 historical run not found: {run_tag}")


def locate_matrix_dir(v1_root: Path) -> Path:
    candidate = v1_root.parents[1] / "historical_matrices_v1"
    if all(
        (candidate / f"{market}_matrix.parquet").exists()
        for market in ("us", "kr", "btc")
    ):
        return candidate
    raise FileNotFoundError(candidate)


def locate_v2_root(drive_root: Path, candidate_tag: str) -> Path:
    candidates = [
        drive_root
        / "Market_Model_V2"
        / "historical_quant_2017_v2_candidate"
        / candidate_tag,
        drive_root
        / "Kalman"
        / "Market_Model_V2"
        / "historical_quant_2017_v2_candidate"
        / candidate_tag,
    ]
    for candidate in candidates:
        if (candidate / "historical_v2_candidate_summary.json").exists():
            return candidate
    raise FileNotFoundError(f"V2 candidate not found: {candidate_tag}")


def snapshot_code(repo_root: Path, app_root: Path, output_root: Path) -> None:
    snapshot = output_root / "code_snapshot"
    snapshot.mkdir(parents=True, exist_ok=True)
    paths = [
        app_root / "config/model-v3-historical-return-regime-spec.json",
        app_root / "research/quant_stack/historical_v3_return_regime.py",
        app_root / "research/quant_stack/historical_v3_qlib.py",
        app_root / "scripts/colab_historical_v3_return_regime.py",
        repo_root / "notebooks/Kalman_Historical_V3_Return_Regime_20260913.ipynb",
    ]
    for source in paths:
        if source.exists():
            shutil.copy2(source, snapshot / source.name)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Kalman Historical V3 return-regime Colab runner"
    )
    p.add_argument("--drive-root", default="/content/drive/MyDrive")
    p.add_argument("--v1-run-tag", default="20260913_042850")
    p.add_argument("--v2-candidate-tag", default="20260913_nested_v2_001")
    p.add_argument("--v3-candidate-tag", default="20260913_return_regime_v3_001")
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

    v1_root = locate_v1_run(drive_root, args.v1_run_tag)
    matrix_dir = locate_matrix_dir(v1_root)
    v2_root = locate_v2_root(drive_root, args.v2_candidate_tag)
    model_root = v1_root.parents[1]
    output_root = (
        model_root
        / "historical_quant_2017_v3_candidate"
        / args.v3_candidate_tag
    )
    output_root.mkdir(parents=True, exist_ok=True)
    status_path = output_root / "v3_colab_status.json"

    def status(phase: str, state: str = "RUNNING", **extra: Any) -> None:
        write_json(
            status_path,
            {
                "status": state,
                "phase": phase,
                "v1_run_tag": args.v1_run_tag,
                "v2_candidate_tag": args.v2_candidate_tag,
                "v3_candidate_tag": args.v3_candidate_tag,
                "code_sha": code_sha,
                "research_only": True,
                "live_execution": False,
                "toss_execution": False,
                "neon_write": False,
                **extra,
            },
        )

    core_venv = Path("/content/.venv-kalman-historical-v3")
    qlib_venv = Path("/content/.venv-kalman-historical-v3-qlib312")
    spec = app_root / "config/model-v3-historical-return-regime-spec.json"
    qlib_req = app_root / "research/quant_stack/requirements-qlib.txt"
    tool_status: dict[str, str] = {}

    try:
        status("CODE_SNAPSHOT")
        snapshot_code(repo_root, app_root, output_root)

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
        ])
        run([core_pip, "check"])
        run([
            core_py,
            "-m",
            "py_compile",
            app_root / "research/quant_stack/historical_v3_return_regime.py",
            app_root / "research/quant_stack/historical_v3_qlib.py",
        ])

        status("V3_RETURN_REGIME")
        run([
            core_py,
            "-m",
            "research.quant_stack.historical_v3_return_regime",
            "--matrix-dir",
            matrix_dir,
            "--v2-root",
            v2_root,
            "--spec",
            spec,
            "--output-dir",
            output_root,
            "--code-sha",
            code_sha,
        ], cwd=app_root)
        tool_status["return_regime"] = "READY"

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
            tracking_root = model_root / "qlib_mlruns_historical_v3"
            provider_root = Path("/content/qlib_provider_historical_v3")
            run([
                qlib_py,
                "-m",
                "research.quant_stack.historical_v3_qlib",
                "--output-dir",
                output_root,
                "--tracking-root",
                tracking_root,
                "--provider-root",
                provider_root,
                "--experiment-name",
                "kalman_historical_v3_return_regime",
            ], cwd=app_root)
            tool_status["qlib"] = "READY"
        except Exception as exc:
            tool_status["qlib"] = f"FAIL: {type(exc).__name__}: {exc}"
            print("QLIB DEGRADED:", tool_status["qlib"])

        status("FINAL_SUMMARY")
        candidate = json.loads(
            (output_root / "candidate_run_status.json").read_text(encoding="utf-8")
        )
        v2_equal_path = (
            v2_root / "portfolio/equal_weight/portfolio_performance.json"
        )
        v2_equal = (
            json.loads(v2_equal_path.read_text(encoding="utf-8"))
            if v2_equal_path.exists()
            else None
        )
        final = {
            "status": "COMPLETE",
            "code_sha": code_sha,
            "v1_run_tag": args.v1_run_tag,
            "v2_candidate_tag": args.v2_candidate_tag,
            "v3_candidate_tag": args.v3_candidate_tag,
            "candidate": candidate,
            "v2_equal_weight_legacy": v2_equal,
            "v3_equal_weight": candidate.get("portfolio", {}).get("metrics"),
            "tool_status": tool_status,
            "code_snapshot": str(output_root / "code_snapshot"),
            "research_only": True,
            "live_execution": False,
            "toss_execution": False,
            "neon_write": False,
            "promotion_recommendation": "RESEARCH_ONLY",
        }
        summary_path = output_root / "historical_v3_candidate_summary.json"
        write_json(summary_path, final)
        status(
            "DONE",
            state="COMPLETE",
            tool_status=tool_status,
            summary=str(summary_path),
        )
        print("\nKALMAN HISTORICAL V3 COMPLETE")
        print(summary_path)
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
