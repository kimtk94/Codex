"""Read-only ingest of a reviewed IS manifest from the checked-out research repository.
Never follows source URLs, downloads raw data, or marks missing input as complete.
"""
import argparse
import hashlib
import json
from pathlib import Path
from .is_batch_executor import execute

ALLOWED_PATHS=(
    "data/metadata/ukb_ppp_download_manifest.tsv",
    "metadata/ukb_ppp_download_manifest.tsv",
    "config/ukb_ppp_download_manifest.tsv",
)

def ingest(source:Path, output:Path):
    output.mkdir(parents=True,exist_ok=True)
    evidence={"source":"IS_Analysis_V3","source_kind":"git_checkout",
              "input_discovered":False,"analysis_executed":False,
              "state":"BLOCKED_EXTERNAL","reason":"REVIEWED_MANIFEST_NOT_FOUND"}
    for relative in ALLOWED_PATHS:
        path=source/relative
        if not path.is_file() or path.is_symlink():
            continue
        if path.stat().st_size>1024*1024:
            evidence["reason"]="MANIFEST_TOO_LARGE"
            break
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        try:
            result=execute(source,path,digest,output)
        except (ValueError,FileNotFoundError) as exc:
            evidence["reason"]=type(exc).__name__
            break
        evidence.update({"input_discovered":True,"analysis_executed":True,
                         "state":"COMPUTATION_COMPLETE","reason":"UPSTREAM_BATCH_PLAN_READY",
                         "input_repository_path":relative,"input_sha256":digest,
                         "paired_gene_count":result["paired_gene_count"],
                         "scientific_analysis_completed":False})
        break
    (output/"auto-input-status.json").write_text(json.dumps(evidence,indent=2)+"\n")
    return evidence

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",type=Path,default=Path("research_source"))
    p.add_argument("--out",type=Path,default=Path("artifacts/auto-input"))
    args=p.parse_args()
    print(json.dumps(ingest(args.source,args.out),indent=2))
