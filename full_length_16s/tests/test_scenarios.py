import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from subset_analyses import run_variants


def example(tmp_path):
    metadata = []
    named = [("KCT_W1_01", "NONE"), ("KCT_W1_02", "NONE"),
             ("K902_W1_01", "NONE"), ("K905_W1_01", "NONE"),
             ("KUW_01", "NONE"), ("KUD_01", "NONE"),
             ("PC", "PC"), ("NC", "NC"),
             ("PC", "PC"), ("NC", "NC")]
    for i, (name, control) in enumerate(named):
        metadata.append({"sample-id": f"{name}__FKDN260619{i+101:03d}-1A",
            "sample-name": name, "novogene-id": f"FKDN260619{i+101:03d}-1A",
            "cohort": name.split("_")[0], "week": "W1", "control": control})
    md = pd.DataFrame(metadata)
    mpath = tmp_path / "metadata.tsv"; md.to_csv(mpath, sep="\t", index=False)
    counts = pd.DataFrame({r["sample-id"]: [3+i, 10-i, (i%2)+1] for i, r in enumerate(metadata)},
                          index=["ASV_1","ASV_2","ASV_3"])
    counts.index.name = "#OTU ID"
    cpath = tmp_path / "feature-table.tsv"; counts.to_csv(cpath, sep="\t")
    ex_path = tmp_path / "excluded.tsv"
    pd.DataFrame({"sample-id": md["sample-id"][:3]}).to_csv(ex_path,sep="\t",index=False)
    return mpath, cpath, ex_path, md


def test_four_variants_and_controls(tmp_path):
    mpath, cpath, ex_path, metadata = example(tmp_path)
    result = run_variants(cpath, None, mpath, ex_path, tmp_path/"run")
    lookup = {r["scenario"]: r for r in result}
    assert len(lookup) == 4
    assert [lookup[s]["n_samples"] for s in
            ("all", "no_controls", "no_three", "no_controls_no_three")] == [10, 6, 7, 3]
    assert lookup["no_controls"]["controls_excluded"] == 4
    assert lookup["no_three"]["specified_three_excluded"] == 3
    assert lookup["no_controls_no_three"]["n_excluded"] == 7
    for k in lookup:
        assert (tmp_path / "run" / k / "report.html").exists()
    assert (tmp_path / "run" / "scenario_comparison.csv").is_file()


def test_unknown_three_sample_blocks(tmp_path):
    mpath, cpath, ex_path, _ = example(tmp_path)
    result = run_variants(cpath, None, mpath, None, tmp_path/"run")
    lookup = {r["scenario"]: r for r in result}
    assert lookup["all"]["status"] == "PASS"
    assert lookup["no_controls"]["status"] == "PASS"
    assert lookup["no_three"]["status"] == "BLOCKED"
    assert lookup["no_controls_no_three"]["status"] == "BLOCKED"


def test_invalid_three_rejected(tmp_path):
    mpath, cpath, ex_path, md = example(tmp_path)
    pd.DataFrame({"sample-id": ["UNKNOWN", md.loc[0,"sample-id"], md.loc[1,"sample-id"]]}).to_csv(ex_path,sep="\t",index=False)
    with pytest.raises(ValueError, match="do not exist"):
        run_variants(cpath, None, mpath, ex_path, tmp_path/"run")


def test_three_must_be_exactly_three(tmp_path):
    mpath, cpath, ex_path, md = example(tmp_path)
    pd.DataFrame({"sample-id": [md.loc[0,"sample-id"], md.loc[1,"sample-id"]]}).to_csv(ex_path,sep="\t",index=False)
    with pytest.raises(ValueError, match="exactly three"):
        run_variants(cpath, None, mpath, ex_path, tmp_path/"run")


def test_control_names_not_confused(tmp_path):
    mpath, cpath, ex_path, md = example(tmp_path)
    result = run_variants(cpath, None, mpath, ex_path, tmp_path/"run")
    control_report = pd.read_csv(tmp_path / "run"/"no_controls"/"excluded_samples.tsv",sep="\t")
    assert set(control_report["sample-name"]) == {"PC","NC"}
    assert len(control_report) == 4
