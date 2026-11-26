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


def make_integrated_wide(path: Path) -> None:
    n = 20
    data = {
        "DIST_ID": [f"P{i:03d}" for i in range(n)],
    }

    for wave in range(1, 6):
        p = f"A{wave:02d}_"
        data[p + "AGE"] = [48 + 2 * (wave - 1) + (i % 7) for i in range(n)]
        data[p + "SEX"] = [1 if i % 2 else 2 for i in range(n)]
        data[p + "EDATE"] = [f"200{wave}-01-01"] * n

        # cardiovascular
        data[p + "BPSIT2S"] = [118 + wave + (i % 10) for i in range(n)]
        data[p + "BPSIT2D"] = [72 + wave + (i % 6) for i in range(n)]
        data[p + "BMI"] = [22 + 0.1 * wave + (i % 4) for i in range(n)]
        data[p + "WAIST1"] = [79 + wave + (i % 8) for i in range(n)]

        # metabolic
        data[p + "GLU0"] = [88 + wave + (i % 12) for i in range(n)]
        data[p + "HBA1C"] = [5.1 + 0.03 * wave + 0.05 * (i % 8) for i in range(n)]
        data[p + "INS0"] = [6 + wave + (i % 5) for i in range(n)]
        data[p + "TCHL"] = [178 + wave + (i % 20) for i in range(n)]
        data[p + "HDL"] = [44 + wave + (i % 8) for i in range(n)]
        data[p + "TG"] = [98 + wave + (i % 20) for i in range(n)]

        # renal
        data[p + "BUN"] = [12 + 0.2 * wave + (i % 5) for i in range(n)]
        data[p + "CREATININ"] = [0.7 + 0.01 * wave + 0.01 * (i % 6) for i in range(n)]

        # hepatic: intentionally only two repeated features
        data[p + "AST"] = [19 + wave + (i % 5) for i in range(n)]
        data[p + "ALT"] = [17 + wave + (i % 5) for i in range(n)]

        # inflammatory / hematologic
        data[p + "WBC_B"] = [5.0 + 0.1 * (i % 8) for i in range(n)]
        data[p + "HB"] = [13.0 + 0.1 * (i % 7) for i in range(n)]
        data[p + "PLAT"] = [220 + (i % 25) for i in range(n)]

        # pulmonary
        data[p + "SP1_2"] = [3.0 + 0.02 * (i % 10) for i in range(n)]
        data[p + "SP2_2"] = [2.5 + 0.02 * (i % 10) for i in range(n)]
        data[p + "SP3_2"] = [0.80 + 0.005 * (i % 10) for i in range(n)]

        # outcomes
        data[p + "HTN"] = [1] * n
        data[p + "DM"] = [1] * n

    pd.DataFrame(data).to_csv(path, sep="\t", index=False)


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


def test_integrated_wide_five_organ_readiness() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = root / "controlled"
        out = root / "results"
        inp.mkdir()

        make_integrated_wide(inp / "koges_integrated.tsv")
        info = run_audit(inp, out)

        assert info["status"] == "ok"
        assert info["integrated_wide_detected"] is True
        assert info["n_waves"] == 5
        assert info["go_no_go"] == "GO"

        ready = set(info["ready_organs"])
        assert {
            "cardiovascular",
            "metabolic",
            "renal",
            "inflammatory_hematologic",
            "pulmonary",
        }.issubset(ready)
        assert "hepatic" not in ready

        organ = pd.read_csv(
            out / "stage0c_controlled_readiness" / "CONTROLLED_ORGAN_READINESS.tsv",
            sep="\t",
        )
        hepatic = organ.loc[organ["organ"].eq("hepatic")].iloc[0]
        assert not bool(hepatic["organ_ready_for_pace"])


if __name__ == "__main__":
    test_missing_dir()
    test_three_organ_go()
    test_integrated_wide_five_organ_readiness()
    print("controlled readiness tests: OK")
