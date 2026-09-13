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


class Tee:
    def __init__(self, *streams: Any) -> None:
        self.streams = streams

    def write(self, data: str) -> int:
        for stream in self.streams:
            stream.write(data)
            stream.flush()
        return len(data)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def run(cmd: list[str | Path], *, cwd: Path | None = None, env=None) -> None:
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
    if code != 0:
        raise subprocess.CalledProcessError(code, args)


def capture(cmd: list[str | Path], *, cwd: Path | None = None, env=None) -> str:
    args = [str(x) for x in cmd]
    print("\n$", " ".join(args))
    try:
        output = subprocess.check_output(
            args,
            cwd=cwd,
            env=env,
            text=True,
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as exc:
        if exc.output:
            print(exc.output, end="" if exc.output.endswith("\n") else "\n")
        raise
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
        raise RuntimeError(f"virtualenv creation failed: {path}")


def locate_output(drive_root: Path, run_tag: str) -> Path:
    candidates = [
        drive_root / "Market_Model_V2" / "historical_quant_2017_v1" / run_tag,
        drive_root / "Kalman" / "Market_Model_V2" / "historical_quant_2017_v1" / run_tag,
        drive_root / "kalman" / "Market_Model_V2" / "historical_quant_2017_v1" / run_tag,
    ]
    for candidate in candidates:
        if (candidate / "historical_experiment_status.json").exists():
            return candidate
    raise FileNotFoundError(
        f"historical run {run_tag} not found under expected Drive roots"
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Resume Kalman historical post-processing without rerunning markets"
    )
    p.add_argument("--drive-root", default="/content/drive/MyDrive")
    p.add_argument("--run-tag", default="20260913_042850")
    p.add_argument("--keep-venvs", action="store_true")
    p.add_argument("--disable-riskfolio", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    drive_root = Path(args.drive_root)
    if not drive_root.exists():
        raise FileNotFoundError(f"Drive root not mounted: {drive_root}")

    diag_dir = drive_root / "Kalman_Diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)
    log_path = diag_dir / "historical_resume_last.log"
    status_path = diag_dir / "historical_resume_last_status.json"

    log_handle = log_path.open("w", encoding="utf-8", buffering=1)
    sys.stdout = Tee(sys.__stdout__, log_handle)
    sys.stderr = Tee(sys.__stderr__, log_handle)

    def write_status(status: str, **extra: Any) -> None:
        payload = {
            "status": status,
            "run_tag": args.run_tag,
            "historical_rerun": False,
            "research_only": True,
            "live_execution": False,
            "toss_execution": False,
            "neon_write": False,
            **extra,
        }
        status_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

    write_status("RUNNING", phase="LOCATE_OUTPUT", log_path=str(log_path))

    app_root = Path(__file__).resolve().parents[1]
    repo_root = app_root.parent
    output_root = locate_output(drive_root, args.run_tag)
    pypfopt_req = app_root / "research/quant_stack/requirements-pypfopt.txt"
    riskfolio_req = app_root / "research/quant_stack/requirements-riskfolio.txt"

    for required in (pypfopt_req, riskfolio_req):
        if not required.exists():
            raise FileNotFoundError(required)

    current_branch = capture(
        ["git", "-C", repo_root, "branch", "--show-current"]
    )
    if current_branch != "main":
        raise RuntimeError(f"resume notebook must run from main, got {current_branch!r}")

    print("OUTPUT_ROOT:", output_root)
    print("HISTORICAL : REUSED / NOT RERUN")

    core_venv = Path("/content/.venv-kalman-resume-v2")
    risk_venv = Path("/content/.venv-riskfolio-resume-v2")

    try:
        write_status("RUNNING", phase="CORE_ENV_INSTALL", output_root=str(output_root))
        create_venv(core_venv, recreate=not args.keep_venvs)
        core_py = core_venv / "bin/python"
        core_pip = core_venv / "bin/pip"
        run(
            [
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
            ]
        )

        write_status("RUNNING", phase="CORE_ENV_VERIFY", output_root=str(output_root))
        run([core_pip, "check"])
        capture(
            [
                core_py,
                "-c",
                (
                    "import packaging,pandas,numpy,scipy,sklearn,pyarrow,pypfopt;"
                    "print('CORE_IMPORTS_OK', packaging.__version__, pandas.__version__, "
                    "numpy.__version__, scipy.__version__, sklearn.__version__, "
                    "pyarrow.__version__)"
                ),
            ],
            cwd=app_root,
        )

        # Reproduce the exact flat-sleeve class of failure under the actual
        # Colab environment before touching real outputs.
        smoke = """
import numpy as np
import pandas as pd
from research.quant_stack.portfolio import allocate

idx = pd.date_range("2024-01-01", periods=120, freq="D", tz="UTC")
returns = pd.DataFrame({
    "US": np.zeros(len(idx)),
    "KR": np.sin(np.arange(len(idx)) / 7.0) * 0.01,
    "BTC": np.cos(np.arange(len(idx)) / 5.0) * 0.02,
}, index=idx)
weights = allocate(returns, method="hrp")
assert np.isfinite(weights.to_numpy(dtype=float)).all()
assert abs(float(weights.sum()) - 1.0) < 1e-8
assert float(weights["US"]) == 0.0
print("FLAT_HRP_SMOKE_OK", weights.to_dict())
"""
        capture([core_py, "-c", smoke], cwd=app_root)

        write_status("RUNNING", phase="ACTUAL_PREFLIGHT", output_root=str(output_root))
        run(
            [
                core_py,
                "-m",
                "research.quant_stack.resume_postprocess",
                "--output-dir",
                output_root,
                "--preflight-only",
            ],
            cwd=app_root,
        )

        write_status(
            "RUNNING",
            phase="HRP_VALIDATION_LEAN",
            output_root=str(output_root),
        )
        run(
            [
                core_py,
                "-m",
                "research.quant_stack.resume_postprocess",
                "--output-dir",
                output_root,
                "--method",
                "hrp",
                "--lookback-days",
                "180",
                "--min-observations",
                "90",
                "--rebalance",
                "M",
            ],
            cwd=app_root,
        )

        riskfolio_status = "SKIPPED"
        if not args.disable_riskfolio:
            write_status(
                "RUNNING",
                phase="RISKFOLIO_ENV_VERIFY",
                output_root=str(output_root),
            )
            create_venv(risk_venv, recreate=not args.keep_venvs)
            risk_py = risk_venv / "bin/python"
            risk_pip = risk_venv / "bin/pip"
            run([risk_pip, "install", "-q", "-r", riskfolio_req])
            run([risk_pip, "check"])
            capture(
                [
                    risk_py,
                    "-c",
                    (
                        "import riskfolio,pandas,numpy,scipy,pyarrow;"
                        "print('RISKFOLIO_IMPORTS_OK', pandas.__version__, "
                        "numpy.__version__, scipy.__version__, pyarrow.__version__)"
                    ),
                ],
                cwd=app_root,
            )

            write_status(
                "RUNNING",
                phase="RISKFOLIO",
                output_root=str(output_root),
            )
            shutil.rmtree(output_root / "riskfolio", ignore_errors=True)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(app_root)
            run(
                [
                    risk_py,
                    "-m",
                    "research.quant_stack.riskfolio_benchmark_runner",
                    "--output-dir",
                    output_root,
                    "--lookback-days",
                    "180",
                    "--min-observations",
                    "90",
                    "--rebalance",
                    "M",
                ],
                cwd=app_root,
                env=env,
            )
            riskfolio_status = "READY"

        head = capture(["git", "-C", repo_root, "rev-parse", "--short", "HEAD"])
        complete = {
            "status": "COMPLETE",
            "run_tag": args.run_tag,
            "output_root": str(output_root),
            "git_sha": head,
            "historical_reused": True,
            "market_backtests_rerun": False,
            "preflight": "READY",
            "hrp": "READY",
            "validation": "READY",
            "lean_shadow": "READY",
            "riskfolio": riskfolio_status,
            "research_only": True,
            "live_execution": False,
            "toss_execution": False,
            "neon_write": False,
        }
        (output_root / "historical_resume_complete.json").write_text(
            json.dumps(complete, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        write_status("COMPLETE", phase="DONE", output_root=str(output_root))
        print("\n" + "=" * 88)
        print("RESUME COMPLETE")
        print("=" * 88)
        print(json.dumps(complete, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        write_status(
            "FAIL",
            phase="FAILED",
            output_root=str(output_root),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        print("\nRESUME FAILED")
        print("ERROR TYPE:", type(exc).__name__)
        print("ERROR     :", str(exc))
        traceback.print_exc()
        raise


if __name__ == "__main__":
    raise SystemExit(main())
