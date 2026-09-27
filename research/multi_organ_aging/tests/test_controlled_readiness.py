from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "src" / "stage0c_controlled_readiness.py"
CONFIG = ROOT / "config" / "multi_organ_aging.json"


def make_wave(path: Path, age_shift: int) -> None:
    n = 20
    df = pd.DataFrame(
        {
            "person_id": [f"P{i:03d}" for i in range(n)],
            "age": [50 + age_shift + (i % 5) for i in range(n)],
            "sex": [1 if i % 2 else 2 for i in range(n)],
            "visit_date": [f"200{1 + age_shift}-01-01"] * n,
            "sbp": [120 + (i % 10) for i in range(n)],
            "dbp": [75 + (i % 6) for i in range(n)],
            "heart_rate": [65 + (i % 8) for i in range(n)],
            "bmi": [22 + (i % 4) for i in range(n)],
            "waist_cm": [80 + (i % 8) for i in range(n)],
            "glucose": [90 + (i % 12) for i in range(n)],
            "hba1c": [5.2 + 0.05 * (i % 8) for i in range(n)],
            "insulin": [7 + (i % 5) for i in range(n)],
            "total_cholesterol": [180 + (i % 20) for i in range(n)],
            "hdl": [45 + (i % 8) for i in range(n)],
            "triglyceride": [100 + (i % 20) for i in range(n)],
            "ast": [20 + (i % 5) for i in range(n)],
            "alt": [18 + (i % 5) for i in range(n)],
            "ggt": [25 + (i % 6) for i in range(n)],
        }
    )
    df.to_csv(path, sep="\t", index=False)


def run_audit(input_dir: Path, out_dir: Path) -> dict:
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--config",
            str(CONFIG),
            "--input-dir",
            str(input_dir),
            "--out-dir",
            str(out_dir),
        ],
        check=True,
    )
    p = out_dir / "stage0c_controlled_readiness" / "CONTROLLED_READINESS_SUMMARY.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_missing_dir() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        info = run_audit(root / "missing", root / "results")
        assert info["status"] == "not_available"
        assert info["multi_organ_ready"] is False


def test_three_organ_go() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = root / "controlled"
        out = root / "results"
        inp.mkdir()

        make_wave(inp / "base.tsv", 0)
        make_wave(inp / "follow_01.tsv", 2)
        make_wave(inp / "follow_02.tsv", 4)

        info = run_audit(inp, out)

        assert info["status"] == "ok"
        assert info["n_waves"] == 3
        assert info["n_ready_organs"] >= 3
        assert info["multi_organ_ready"] is True
        assert info["go_no_go"] == "GO"

        organ = pd.read_csv(
            out / "stage0c_controlled_readiness" / "CONTROLLED_ORGAN_READINESS.tsv",
            sep="\t",
        )
        ready = set(
            organ.loc[organ["organ_ready_for_pace"], "organ"].astype(str)
        )
        assert {"cardiovascular", "metabolic", "hepatic"}.issubset(ready)


if __name__ == "__main__":
    test_missing_dir()
    test_three_organ_go()
    print("controlled readiness tests: OK")
