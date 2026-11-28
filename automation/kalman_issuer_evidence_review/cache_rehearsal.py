"""Rehearse a narrowly scoped evidence cache; no production integration."""
import argparse
import gzip
import io
import json
from pathlib import Path, PurePosixPath
import zipfile
from evidence_review import TARGETS, VERIFIED, REPORT_SUFFIX, read_member, sha, compare
from independent_review import independent_review, extract_text, anchors_near, ANCHORS

PRIOR_PIN = "956a7a17c124e98277588c333386634ac66119952f18fcc0a2454b9cdbdd4fe6"
CURRENT_PIN = "ca733ef791d264dcf8f194d00af48d17993d49f02061426ec6fec1eeebe3f60f"
PINS = {
    "QQQ_2018_SEC_2020_Q3_TABLE": "93ebbbd72e4010439f625849262028a61b0060f84a7eed7dbba816c992072c4a",
    "QLD_2025_FORM_8937_SPLIT": "223970087d3561ba6aa29b434066cb6bc8c8d985bb082b12ae4bec9639ad934a",
}

def select(current, prior):
    result = compare(current, prior)
    # Reject the entire pair if any identity, revision or anchor check failed.
    if not result["prior_pair_available"]:
        raise ValueError("PRIOR_PAIR_NOT_VERIFIED")
    for sid in TARGETS:
        old = prior["sources"][sid]
        if old.get("independent_anchors_verified") is not True or old["sha256"] != PINS[sid]:
            raise ValueError("PRIOR_SOURCE_NOT_PINNED")
    choices = {}
    for sid in TARGETS:
        now = current["sources"][sid]
        decision = result["decisions"][sid]
        if (decision == "CURRENT_EVIDENCE_PRESENT_PAYMENT_HOLD"
                and now.get("independent_anchors_verified") is True and now["sha256"] == PINS[sid]):
            choices[sid] = "CURRENT"
        elif (decision == "PRIOR_PINNED_EVIDENCE_REVIEW_CANDIDATE_HOLD"
              and now.get("fetch_status") == "HTTP_403_SOURCE_HOLD"
              and now.get("sha256") is None):
            choices[sid] = "PRIOR_HTTP_403"
        else:
            raise ValueError("SOURCE_REUSE_DENIED:" + sid)
    return choices

def raw_bytes(path, pin, sid):
    payload = Path(path).read_bytes()
    if sha(payload) != pin:
        raise ValueError("ARCHIVE_PIN_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        rp = next(n for n in z.namelist() if n == REPORT_SUFFIX or n.endswith("/"+REPORT_SUFFIX))
        prefix = str(PurePosixPath(rp).parent)
        _, _, kind, limit = TARGETS[sid]
        name = prefix + "/raw/" + sid.lower() + "." + kind + ".gz"
        with gzip.GzipFile(fileobj=io.BytesIO(read_member(z, name, limit+1_000_000))) as f:
            raw = f.read(limit+1)
        if len(raw) > limit or sha(raw) != PINS[sid]:
            raise ValueError("CACHE_BYTES_PIN_MISMATCH")
        if not anchors_near(extract_text(raw, kind), ANCHORS[sid]):
            raise ValueError("CACHE_ANCHORS_NOT_VERIFIED")
        return raw

def rehearse(current_path, prior_path):
    current = independent_review(current_path, CURRENT_PIN)
    prior = independent_review(prior_path, PRIOR_PIN)
    choices = select(current, prior)
    evidence = {}
    # Materialize only in memory, never write source archives or journals.
    for sid, choice in choices.items():
        path, pin = ((current_path, CURRENT_PIN) if choice == "CURRENT"
                     else (prior_path, PRIOR_PIN))
        raw = raw_bytes(path, pin, sid)
        evidence[sid] = {"selection":choice,"source_sha256":sha(raw),
                         "archive_sha256":pin,"body_bytes":len(raw)}
    return {"status":"ISOLATED_CACHE_REHEARSAL_PASS", "evidence":evidence,
            "research_only":True,"production_writes":False,
            "cache_reuse_authorized":False,"strategy_promoted":False,
            "issuer_payments_certified":0,"source_finality_verified":0}

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("current")
    p.add_argument("prior")
    args = p.parse_args()
    print(json.dumps(rehearse(args.current,args.prior),sort_keys=True))
