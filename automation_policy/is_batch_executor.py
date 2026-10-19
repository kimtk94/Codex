"""Execute actual IS V3 paired-batch planning on provided non-sensitive manifest.
This is an upstream computational stage, not MR/coloc or biological QC.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

def execute(source: Path, manifest: Path, expected_sha: str, output: Path):
    if not manifest.is_file():
        raise FileNotFoundError("research_manifest_missing")
    if manifest.stat().st_size > 1024*1024:
        raise ValueError("manifest_exceeds_1mb")
    actual=hashlib.sha256(manifest.read_bytes()).hexdigest()
    if actual!=expected_sha:
        raise ValueError("manifest_sha256_mismatch")
    script=source/"scripts"/"ukb_ppp_batch_manifest_runner_fast.py"
    if not script.is_file():
        raise FileNotFoundError("upstream_runner_missing")
    spec=importlib.util.spec_from_file_location("upstream_is_v3_runner",script)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows=module.read_tsv(manifest)
    batches=module.paired_batches(rows,15)
    if not batches:
        raise ValueError("no_paired_eur_eas_genes")
    output.mkdir(parents=True,exist_ok=True)
    report={"state":"COMPUTATION_COMPLETE","operation":"upstream_paired_batches",
            "input_sha256":actual,"upstream_script_sha256":hashlib.sha256(script.read_bytes()).hexdigest(),
            "paired_gene_count":sum(map(len,batches)),"batches":batches,
            "biological_analysis_completed":False,"downstream_mr_completed":False}
    (output/"is-v3-batch-plan.json").write_text(json.dumps(report,indent=2)+"\n")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--sha256",required=True)
    p.add_argument("--out",type=Path,default=Path("artifacts"))
    a=p.parse_args()
    print(json.dumps(execute(a.source,a.manifest,a.sha256,a.out),indent=2))
