"""Fail-closed checkpoint format for bounded CI continuation; no remote writes."""
import hashlib
import hmac
import json
from pathlib import Path
from .plan import Step, validate

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()

def fingerprint(spec):
    return hashlib.sha256(canonical(spec)).hexdigest()

def resume(spec, prior, *, expected_commit):
    steps=[Step(x["id"],x["action"],tuple(x.get("needs",[]))) for x in spec["steps"]]
    order=validate(steps)
    fresh={"version":1,"plan_sha256":fingerprint(spec),"source_commit":expected_commit,
           "completed":[], "next":order[0] if order else None,"status":"NO_TRUSTED_CHECKPOINT"}
    if not isinstance(prior,dict):
        return fresh
    if prior.get("version")!=1 or not hmac.compare_digest(str(prior.get("plan_sha256","")),fresh["plan_sha256"]):
        return fresh
    if not hmac.compare_digest(str(prior.get("source_commit","")),expected_commit):
        return fresh
    # A checkpoint is useful as a hint but may not attest execution.
    # Never trust completed jobs from an untrusted artifact.
    return {**fresh,"status":"CHECKPOINT_METADATA_MATCH_ONLY","claimed_completed":prior.get("completed",[]),
            "completed":[]}

def save(path:Path, report):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
