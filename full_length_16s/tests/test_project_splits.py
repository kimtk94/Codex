"""Regression tests: workbook's top 92 and bottom 18 must NEVER be pooled."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from project_splits import (
    THREE_EXCLUDED_FKDN, PROJECTS, _normalize_columns,
    prepare, run, validate_and_split,
)


def _fixture(tmp_path):
    items = []
    upper_names = [
        f"{cohort}_W{week}_{num:02d}"
        for week in range(1, 4)
        for cohort in ("KCT", "K902", "K905")
        for num in range(1, 11)
    ]
    upper_names += ["PC", "NC"]
    lower_names = [f"{cohort}_{num:02d}" for cohort in ("KUW", "KUD", "KCR", "KDR") for num in range(1, 5)]
    lower_names += ["PC", "NC"]
    assert len(upper_names) == 92 and len(lower_names) == 18
    for i, name in enumerate(upper_names):
        fkdn = f"FKDN260619{13+i:03d}-1A"
        items.append((name, fkdn))
    for i, name in enumerate(lower_names):
        fkdn = f"FKDN260618{712+i:03d}-1A"
        items.append((name, fkdn))
    metadata = pd.DataFrame([
        {"sample-id": name + "__" + fkdn,
         "sample-name": name, "novogene-id": fkdn,
         "cohort": name.split("_")[0] if "_" in name else "CONTROL",
         "week": "NA", "control": name if name in ("PC", "NC") else "NONE"}
        for name, fkdn in items
    ])
    meta_path = tmp_path / "metadata.tsv"
    metadata.to_csv(meta_path, sep="\t", index=False)
    counts = pd.DataFrame({
        sample_id: [50+i % 9, 2+i % 3, 1] for i, sample_id in enumerate(metadata["sample-id"])
    },index=["ASV1","ASV2","ASV3"])
    counts.index.name="#OTU ID"
    feature_path = tmp_path / "feature-table.tsv"
    counts.to_csv(feature_path, sep="\t")
    return metadata, meta_path, feature_path


def test_split_boundaries_and_controls(tmp_path):
    metadata, meta_path, feature_path = _fixture(tmp_path)
    scoped = validate_and_split(meta_path)
    assert list(scoped) == ["P92", "P18"]
    assert len(scoped["P92"]) == 92
    assert len(scoped["P18"]) == 18
    assert scoped["P92"]["sample-name"].iloc[0] == "KCT_W1_01"
    assert scoped["P92"]["sample-name"].iloc[-1] == "NC"
    assert scoped["P18"]["sample-name"].iloc[0] == "KUW_01"
    assert scoped["P18"]["sample-name"].iloc[-1] == "NC"
    assert scoped["P92"]["control"].isin(["PC","NC"]).sum() == 2
    assert scoped["P18"]["control"].isin(["PC","NC"]).sum() == 2
    assert set(THREE_EXCLUDED_FKDN).issubset(set(scoped["P92"]["novogene-id"]))
    expected = {
        "FKDN260619042-1A":"K905_W1_10",
        "FKDN260619082-1A":"KCT_W3_10",
        "FKDN260619084-1A":"K902_W3_02",
    }
    for fid,name in expected.items():
        assert scoped["P92"].loc[scoped["P92"]["novogene-id"]==fid,"sample-name"].item() == name


def test_independent_scenarios(tmp_path):
    metadata, meta_path, feature_path = _fixture(tmp_path)
    plans = [
        ("P92","all",92),("P92","no_controls",90),
        ("P92","no_controls_no_three",87),
        ("P18","all",18),("P18","no_controls",16),
    ]
    for proj, scenario, expected in plans:
        result = run(feature_path,meta_path,proj,scenario,tmp_path/f"{proj}-{scenario}")
        assert result["actual_samples"] == expected
        output = tmp_path/f"{proj}-{scenario}"/"reports"/scenario
        assert (output/"report.html").exists()
        assert (output/"excluded_samples.tsv").exists()
    exclusions = pd.read_csv(tmp_path/"P92-no_controls_no_three"/"reports"/"no_controls_no_three"/"excluded_samples.tsv",sep="\t")
    assert len(exclusions) == 5
    assert set(exclusions["novogene-id"]) == set(THREE_EXCLUDED_FKDN)|{"FKDN260619103-1A","FKDN260619104-1A"}


def test_wrong_spreadsheet_order_rejected(tmp_path):
    metadata, meta_path, feature_path = _fixture(tmp_path)
    metadata.loc[[91, 92]] = metadata.loc[[92, 91]].to_numpy()
    metadata.to_csv(meta_path,sep="\t",index=False)
    with pytest.raises(ValueError,match="boundary"):
        validate_and_split(meta_path)


def test_missing_reads_rejected_not_filled_zero(tmp_path):
    metadata, meta_path, feature_path = _fixture(tmp_path)
    features = pd.read_csv(feature_path,sep="\t")
    features.drop(columns=[metadata.loc[0,"sample-id"]]).to_csv(feature_path,sep="\t",index=False)
    with pytest.raises(ValueError,match="missing 1/92"):
        prepare(feature_path,meta_path,"P92",tmp_path/"p92")


def test_ambiguous_pc_nc_in_mixed_project_rejected(tmp_path):
    metadata, meta_path, feature_path = _fixture(tmp_path)
    scoped = validate_and_split(meta_path)
    all_table = pd.read_csv(feature_path,sep="\t",index_col=0)
    # Bare PC and NC are ambiguous if both projects' samples appear.
    ambiguous = all_table.drop(columns=[
        metadata.loc[90,"sample-id"],metadata.loc[91,"sample-id"],
        metadata.loc[108,"sample-id"],metadata.loc[109,"sample-id"]
    ]).copy()
    ambiguous["PC"] = [10,0,0]
    ambiguous["NC"] = [10,0,0]
    with pytest.raises(ValueError,match="ambiguous bare PC/NC"):
        _normalize_columns(ambiguous,scoped["P92"],scoped["P18"],"P92")


def test_misapplied_3sample_to_p18_rejected(tmp_path):
    _,meta_path,feature_path = _fixture(tmp_path)
    with pytest.raises(ValueError,match="not a valid scenario"):
        run(feature_path,meta_path,"P18","no_controls_no_three",tmp_path/"invalid")
