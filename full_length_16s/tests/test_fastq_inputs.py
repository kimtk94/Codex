"""FASTQ-only 16S archive extraction and contamination-avoidance regression tests."""
import gzip
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from fastq_inputs import included_metadata, prepare_from_zip, run
from test_project_splits import _fixture


def _zip_fixture(path, rows, skip=None):
    with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_DEFLATED) as archive:
        for _, sample in rows.iterrows():
            if sample["novogene-id"]==skip: continue
            content = gzip.compress(b"@read1\nACGTACGT\n+\nFFFFFFFF\n")
            name = "raw/"+sample["sample-name"]+"_"+sample["novogene-id"]+".fastq.gz"
            archive.writestr(name,content)
    return path


@pytest.mark.parametrize("project,scenario,n",[
    ("P92","no_controls",90),
    ("P92","no_controls_no_three",87),
    ("P18","no_controls",16),
])
def test_zip_only_extracts_approved_fastq(tmp_path,project,scenario,n):
    meta,meta_path,_ = _fixture(tmp_path)
    zip_path=_zip_fixture(tmp_path/"raw_fastqs.zip",meta)
    audit=run(meta_path,project,scenario,tmp_path/"outputs",zip_path=zip_path)
    assert audit["expected_samples"]==n
    assert audit["manifest_samples"]==n
    inv=pd.read_csv(tmp_path/"outputs"/"fastq_inventory.tsv",sep="\t")
    assert len(inv)==n
    assert not inv["source"].str.contains("PC_|NC_",regex=True).any()
    if scenario=="no_controls_no_three":
        assert not inv["source"].str.contains(
            "FKDN260619042-1A|FKDN260619082-1A|FKDN260619084-1A", regex=True).any()
    for p in inv["prepared_path"]:
        with gzip.open(p,"rt") as f:
            assert f.readline()=="@read1\n"


def test_missing_fastq_blocks_strictly(tmp_path):
    metadata,meta_path,_ = _fixture(tmp_path)
    zip_path=_zip_fixture(tmp_path/"missing.zip",metadata,skip="FKDN260619013-1A")
    with pytest.raises(ValueError,match="FASTQ import is incomplete"):
        run(meta_path,"P92","no_controls",tmp_path/"outputs",zip_path=zip_path)


def test_zip_without_fastq_does_not_fake_success(tmp_path):
    metadata,meta_path,_=_fixture(tmp_path)
    zip_path=tmp_path/"not_raw.zip"
    with zipfile.ZipFile(zip_path,"w") as archive:
        archive.writestr("results/report.html","No raw data")
    with pytest.raises(ValueError,match="no .fastq"):
        run(meta_path,"P18","no_controls",tmp_path/"outputs",zip_path=zip_path)


def test_project_specific_controls_not_included_even_if_present_in_zip(tmp_path):
    metadata,meta_path,_=_fixture(tmp_path)
    zip_path=_zip_fixture(tmp_path/"raw_fastqs.zip",metadata)
    subset=included_metadata(meta_path,"P92","no_controls")
    assert len(subset)==90
    assert set(subset["control"])=={"NONE"}
    assert not any(subset["sample-id"].str.contains("PC__|NC__",regex=True))
