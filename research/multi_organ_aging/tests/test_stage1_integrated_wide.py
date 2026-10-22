from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "src" / "stage1_build_longitudinal.py"
CONFIG = ROOT / "config" / "multi_organ_aging.json"


def ids(n: int) -> list[str]:
    return [f"P{i:03d}" for i in range(n)]


def make_core(path: Path, n: int = 20) -> None:
    data = {"DIST_ID": ids(n)}
    for visit in range(1, 6):
        p = f"A{visit:02d}_"
        year = 2001 + 2 * (visit - 1)
        data[p + "AGE"] = [50 + 2 * (visit - 1) + (i % 4) for i in range(n)]
        data[p + "EDATE"] = [f"{year}0101"] * n
        if visit == 1:
            data[p + "SEX"] = [1 if i % 2 else 2 for i in range(n)]

        data[p + "BPSIT2S"] = [118 + visit + (i % 8) for i in range(n)]
        data[p + "BPSIT2D"] = [72 + visit + (i % 5) for i in range(n)]
        data[p + "BMI"] = [22 + 0.1 * visit + (i % 4) for i in range(n)]
        data[p + "WAIST1"] = [78 + visit + (i % 7) for i in range(n)]
        data[p + "HTN"] = [1] * n
        data[p + "DM"] = [1] * n
    pd.DataFrame(data).to_csv(path, sep="\t", index=False)


def make_biochem(path: Path, n: int = 20) -> None:
    data = {"DIST_ID": ids(n)}
    for visit in range(1, 6):
        p = f"A{visit:02d}_"
        data[p + "GLU0"] = [88 + visit + (i % 10) for i in range(n)]
        data[p + "HBA1C"] = [5.1 + 0.03 * visit + 0.04 * (i % 6) for i in range(n)]
        data[p + "INS0"] = [6 + visit + (i % 5) for i in range(n)]
        data[p + "TCHL"] = [175 + visit + (i % 18) for i in range(n)]
        data[p + "HDL"] = [45 + (i % 8) for i in range(n)]
        data[p + "TG"] = [95 + visit + (i % 18) for i in range(n)]
        data[p + "BUN"] = [12 + 0.2 * visit + (i % 4) for i in range(n)]
        data[p + "CREATININ"] = [0.70 + 0.01 * visit + 0.01 * (i % 5) for i in range(n)]
        data[p + "AST"] = [19 + visit + (i % 4) for i in range(n)]
        data[p + "ALT"] = [17 + visit + (i % 4) for i in range(n)]
        data[p + "WBC_B"] = [5.0 + 0.1 * (i % 7) for i in range(n)]
        data[p + "HB"] = [13.0 + 0.1 * (i % 6) for i in range(n)]
        data[p + "PLAT"] = [220 + (i % 20) for i in range(n)]
    pd.DataFrame(data).to_csv(path, sep="\t", index=False)


def make_spiro(path: Path, n: int = 20) -> None:
    data = {"DIST_ID": ids(n)}
    for visit in range(1, 6):
        p = f"A{visit:02d}_"
        data[p + "SP1_2"] = [3.0 + 0.02 * (i % 8) for i in range(n)]
        data[p + "SP2_2"] = [2.4 + 0.02 * (i % 8) for i in range(n)]
        # This source ratio is intentionally present, but Stage 1 should derive
        # the canonical ratio from matched measured FEV1/FVC values.
        data[p + "SP3_2"] = [0.80 + 0.002 * (i % 8) for i in range(n)]
    pd.DataFrame(data).to_csv(path, sep="\t", index=False)


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = root / "controlled"
        out = root / "results"
        inp.mkdir()

        make_core(inp / "anthro.tsv")
        make_biochem(inp / "biochem.tsv")
        make_spiro(inp / "spiro.tsv")

        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--config",
                str(CONFIG),
                "--input-dir",
                str(inp),
                "--out-dir",
                str(out),
            ],
            check=True,
        )

        stage = out / "stage1_longitudinal"
        summary = json.loads(
            (stage / "STAGE1_SUMMARY.json").read_text(encoding="utf-8")
        )
        panel = pd.read_csv(
            stage / "LONGITUDINAL_MULTI_ORGAN_PANEL.tsv.gz",
            sep="\t",
            compression="gzip",
            low_memory=False,
        )
        conflicts = pd.read_csv(
            stage / "DUPLICATE_PARTICIPANT_WAVE_CONFLICTS.tsv",
            sep="\t",
        )

        assert summary["rows"] == 100
        assert summary["subjects"] == 20
        assert summary["waves"] == 5
        assert summary["subjects_ge_3_visits"] == 20
        assert summary["integrated_wide_input_files"] == 3
        assert summary["input_modes"] == ["integrated_wide"]
        assert summary["duplicate_value_conflicts_flagged"] == 0
        assert conflicts.empty

        assert set(panel["wave"]) == {
            "base",
            "follow_01",
            "follow_02",
            "follow_03",
            "follow_04",
        }
        assert panel.groupby("person_id")["wave"].nunique().eq(5).all()
        assert panel["year_offset_source"].eq("actual_exam_date").all()
        assert panel["sex_male"].notna().all()

        for col in [
            "sbp",
            "dbp",
            "bmi",
            "waist_cm",
            "glucose",
            "hba1c",
            "insulin",
            "total_cholesterol",
            "hdl",
            "triglyceride",
            "bun",
            "creatinine",
            "ast",
            "alt",
            "wbc",
            "hemoglobin",
            "platelet",
            "fvc",
            "fev1",
            "fev1_fvc",
        ]:
            assert panel[col].notna().all(), col

        derived = panel["fev1"] / panel["fvc"]
        assert (panel["fev1_fvc"] - derived).abs().max() < 1e-12

        dup = panel.duplicated(["person_id", "wave"]).sum()
        assert dup == 0

        print("stage1 integrated-wide longitudinal test: OK")


if __name__ == "__main__":
    main()
