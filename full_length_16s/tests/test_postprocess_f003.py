"""Unit test for the Windows post-DADA2 90/87 report splitter.

Synthetic counts only; no user data or actual ASV inference in CI.
"""
from __future__ import annotations
import importlib.util
import shutil
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "full_length_16s" / "src" / "full16s.py"
REPORTER = REPO / "full_length_16s" / "windows" / "postprocess_f003.py"


def test_f003_90_to_87_reports(tmp_path):
    spec = importlib.util.spec_from_file_location("postprocess_f003", REPORTER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    root = tmp_path / "KIST16S_Local"
    code = root / "code"
    meta_path = root / "metadata" / "projects" / "P92_metadata.tsv"
    table = root / "F003_90" / "DADA2" / "feature-table.tsv"
    for folder in (code, meta_path.parent, table.parent):
        folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC, code / "full16s.py")

    names = ([f"KCT_W1_{i:02d}" for i in range(1, 88)]
             + ["K905_W1_10", "KCT_W3_10", "K902_W3_02"])
    assert len(set(names)) == 90
    sample_ids = [f"{n}__FKDN260619{i:03d}-1A" for i, n in enumerate(names)]
    meta = pd.DataFrame({
        "sample-id": sample_ids + ["PC__CONTROL", "NC__CONTROL"],
        "sample-name": names + ["PC", "NC"],
        "cohort": ["KIST"] * 90 + ["CONTROL", "CONTROL"],
        "week": ["W1"] * 90 + ["NA", "NA"],
        "group-name": ["Group"] * 90 + ["NA", "NA"],
    })
    meta.to_csv(meta_path, sep="\t", index=False)

    counts = pd.DataFrame({"ASV_ID": ["ASV000001", "ASV000002", "ASV000003"]})
    for i, name in enumerate(sample_ids):
        counts[name] = [120 + (i % 8), 22 + (i % 13), 1 + (i % 4)]
    counts.to_csv(table, sep="\t", index=False)

    summary = mod.produce(root)
    assert summary["F003_90"]["samples"] == 90
    assert summary["F003_87"]["samples"] == 87
    assert summary["F003_90"]["total_asvs"] == 3
    assert summary["F003_87"]["total_asvs"] == 3
    assert summary["F003_87"]["asv_reads"] < summary["F003_90"]["asv_reads"]
    assert "independent" in summary["F003_87"]["interpretation"]
    for scenario in ("F003_90", "F003_87"):
        output = root / "F003_90" / f"reports_{scenario}"
        assert (output / "summary.json").is_file()
        assert (output / "bray_curtis.csv").is_file()
        assert (output / "pcoa_bray_curtis.png").is_file()
        assert (output / "alpha_diversity.csv").is_file()
