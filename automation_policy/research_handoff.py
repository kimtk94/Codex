"""Read-only research handoff: input must be present, hashed and explicitly stage-scoped."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

REQUIRED={"gene","ancestry","source_url"}
def inspect(path:Path, expected_hash:str)->dict:
    if not path.is_file():
        return {"state":"BLOCKED_EXTERNAL","reason":"INPUT_NOT_PRESENT","analysis_executed":False}
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    if actual!=expected_hash:
        return {"state":"BLOCKED_EXTERNAL","reason":"CHECKSUM_MISMATCH","analysis_executed":False}
    with path.open(encoding="utf-8-sig",newline="") as handle:
        reader=csv.DictReader(handle,delimiter="\t")
        if not REQUIRED.issubset(reader.fieldnames or []):
            return {"state":"BLOCKED_EXTERNAL","reason":"MISSING_COLUMNS","analysis_executed":False}
        rows=list(reader)
    paired={}
    for row in rows:
        gene=(row.get("gene") or "").strip().upper()
        ancestry=(row.get("ancestry") or "").strip().upper()
        if not gene or ancestry not in ("EUR","EAS"):
            return {"state":"BLOCKED_EXTERNAL","reason":"INVALID_ROW","analysis_executed":False}
        paired.setdefault(gene,set()).add(ancestry)
    valid=sorted(g for g,a in paired.items() if {"EUR","EAS"}.issubset(a))
    return {"state":"INPUT_VALIDATED","analysis_executed":False,"sha256":actual,
            "total_rows":len(rows),"paired_genes":valid,
            "next_action":"EXECUTOR_NOT_CONNECTED"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--path",type=Path,required=True)
    p.add_argument("--sha256",required=True)
    p.add_argument("--output",type=Path,default=Path("artifacts/research-handoff.json"))
    a=p.parse_args()
    result=inspect(a.path,a.sha256)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))
    if result["state"]=="BLOCKED_EXTERNAL":
        raise SystemExit(2)
if __name__=="__main__":
    main()
