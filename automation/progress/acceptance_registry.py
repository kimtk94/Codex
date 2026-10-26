"""Fail-closed signed review registry. Never automatically accept PR or CI results."""
import argparse
import datetime as dt
import json
from pathlib import Path
from gate_evaluator import evaluate
from tracker import tasks, validate_manifest, MASTER

REGISTRY = Path("automation/progress/acceptance_registry.json")
MANIFEST = Path("automation/progress/acceptance_manifest.json")

def verify(registry, manifest, task_ids):
    if registry.get("schema_version") != 1:
        raise ValueError("Invalid registry schema")
    mapping=validate_manifest(manifest,task_ids)
    records=registry.get("records",{})
    if not isinstance(records,dict):
        raise ValueError("Invalid records object")
    for tid, rec in records.items():
        if tid not in mapping or rec.get("gate_id") != mapping[tid]:
            raise ValueError("Unknown task or incorrect gate: "+tid)
        if rec.get("decision") not in ("ACCEPTED","REJECTED"):
            raise ValueError("Review decision must be explicit")
        if not rec.get("reviewer") or not rec.get("reviewed_at"):
            raise ValueError("Reviewer and review timestamp required")
        try:
            timestamp=dt.datetime.fromisoformat(rec["reviewed_at"].replace("Z","+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("Review timestamp must be timezone aware")
        except (TypeError,ValueError) as ex:
            raise ValueError("Invalid timestamp: "+tid) from ex
        if rec["decision"]=="ACCEPTED":
            required=manifest["gates"][mapping[tid]]["required"]
            evidence=rec.get("evidence",{})
            if not isinstance(evidence,dict) or any(not evidence.get(k) for k in required):
                raise ValueError("Incomplete acceptance evidence: "+tid)
    return evaluate(manifest,records)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",default="progress-audit/signed-acceptance-verdicts.json")
    a=ap.parse_args()
    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    registry=json.loads(REGISTRY.read_text(encoding="utf-8"))
    task_ids={x["id"] for x in tasks(Path(MASTER).read_text(encoding="utf-8"))}
    verdicts=verify(registry,manifest,task_ids)
    dest=Path(a.output)
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(verdicts,ensure_ascii=False,indent=2),encoding="utf-8")
    print("SIGNED_REGISTRY_VALID",len(registry["records"]),"review records;",sum(v["state"]=="ACCEPTED" for v in verdicts),"accepted gates")

if __name__=="__main__":
    main()
