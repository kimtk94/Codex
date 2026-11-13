#!/usr/bin/env python3
"""Synthetic-only postprocessing smoke test; never writes real analysis output."""
import csv
import json
import shutil
import sys
from pathlib import Path
import pandas as pd
home=Path.home()/"Documents"/"KIST16S_Local"
mock=home/"validation"/"synthetic_test"
(mock/"code").mkdir(parents=True,exist_ok=True)
(mock/"metadata"/"projects").mkdir(parents=True,exist_ok=True)
(mock/"F003_90"/"DADA2").mkdir(parents=True,exist_ok=True)
shutil.copy2(home/"code"/"full16s.py",mock/"code"/"full16s.py")
shutil.copy2(home/"metadata"/"projects"/"P92_metadata.tsv",mock/"metadata"/"projects"/"P92_metadata.tsv")
rows=list(csv.DictReader((home/"F003_90"/"manifest_local.tsv").open(encoding="utf-8"),delimiter="\t"))
assert len(rows)==90
samples=[r["sample-id"] for r in rows]
features=pd.DataFrame({"ASV_ID":["ASV000001","ASV000002","ASV000003"]})
for i,s in enumerate(samples):
    features[s]=[100+i%15,20+(i%11),3+(i%4)]
features.to_csv(mock/"F003_90"/"DADA2"/"feature-table.tsv",sep="\t",index=False)
sys.path.insert(0,str(home))
from postprocess_f003 import produce
r=produce(mock)
assert r["F003_90"]["samples"]==90
assert r["F003_87"]["samples"]==87
assert r["F003_90"]["total_asvs"]==3
print("SYNTHETIC_SMOKE_TEST_PASS",json.dumps({k:{"samples":v["samples"],"asv_reads":v["asv_reads"]} for k,v in r.items() if k in ("F003_90","F003_87")}))
