"""Rehearse an origin-tagged sidecar without changing the Daily20 audit."""
import argparse
import json
import io
from pathlib import Path, PurePosixPath
import sys
from tempfile import TemporaryDirectory
import zipfile

from cache_rehearsal import CURRENT_PIN, PRIOR_PIN, rehearse
from evidence_review import TARGETS, REPORT_SUFFIX, read_member, sha

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "kalman_daily20"))
from issuer_ca_gap_audit import audit

EVENTS = {("QQQ", "2018-06-18"), ("QLD", "2023-09-20")}
GAP_HOLD = "ISSUER_DISTRIBUTIONS_2_EVENTS_HOLD"
FLAGS = ("actual_payment_certified", "independent_adjustment_factor_certified",
         "independent_close_certified", "issuer_ex_date_and_amount_jointly_certified")

def require(cond, reason):
    if not cond:
        raise ValueError(reason)

def make_sidecar(gap, gap_sha, result):
    require(gap.get("version") == "daily20-issuer-ca-gap-audit-v1"
            and gap.get("status") == GAP_HOLD
            and gap.get("research_only") is True
            and gap.get("production_writes") is False
            and gap.get("strategy_promoted") is False
            and gap.get("issuer_payments_certified") == 0
            and gap.get("source_finality_verified") == 0
            and gap.get("unarchived_research_leads_are_certified") is False,
            "BASELINE_GOVERNANCE_HOLD")
    events = gap.get("events", [])
    require(len(events) == 2 and
            {(e.get("symbol"), e.get("ex_date")) for e in events} == EVENTS,
            "BASELINE_EVENT_SET_HOLD")
    require(result.get("status") == "ISOLATED_CACHE_REHEARSAL_PASS"
            and result.get("research_only") is True
            and result.get("production_writes") is False
            and result.get("cache_reuse_authorized") is False
            and result.get("strategy_promoted") is False
            and result.get("issuer_payments_certified") == 0
            and result.get("source_finality_verified") == 0,
            "REHEARSAL_GOVERNANCE_HOLD")
    require(set(result.get("evidence", {})) == set(TARGETS), "EVIDENCE_SET_HOLD")
    out = []
    for event in events:
        sid = event["source_id"]
        claim, url, _, _ = TARGETS[sid]
        require(claim == event["symbol"] + "|" + event["ex_date"]
                and event.get("source_url") == url
                and all(event.get(f) is False for f in FLAGS)
                and event.get("research_hold") is True,
                "BASELINE_EVENT_GOVERNANCE_HOLD")
        e = result["evidence"][sid]
        origin = e["selection"]
        if origin == "CURRENT":
            require(event.get("source_body_sha256") == e["source_sha256"]
                    and event.get("archived_evidence_status") ==
                    "SOURCE_BYTES_AND_ANCHORS_VERIFIED_PAYMENT_UNCERTIFIED"
                    and e["archive_sha256"] == CURRENT_PIN,
                    "CURRENT_EVIDENCE_MISMATCH_HOLD")
        elif origin == "PRIOR_HTTP_403":
            require(event.get("source_body_sha256") is None
                    and event.get("archived_evidence_status") == "SOURCE_NOT_FETCHED_HOLD"
                    and e["archive_sha256"] == PRIOR_PIN,
                    "PRIOR_MUST_NOT_OVERRIDE_CURRENT_HOLD")
        else:
            raise ValueError("UNKNOWN_ORIGIN_HOLD")
        out.append({"source_id": sid, "symbol": event["symbol"], "ex_date":event["ex_date"],
                    "origin":origin, "live_evidence_observed":origin == "CURRENT",
                    "historical_context_only":origin == "PRIOR_HTTP_403",
                    "source_sha256":e["source_sha256"], "archive_sha256":e["archive_sha256"],
                    "actual_payment_certified":False, "research_hold":True})
    return {"version":"issuer-effective-context-sidecar-v1", "status":"SHADOW_CONTEXT_READY_HOLD",
            "baseline_gap_sha256":gap_sha,
            "baseline_both_archived_sources_verified":gap["both_archived_sources_verified"],
            "effective_context_count":len(out), "current_evidence_count":sum(x["live_evidence_observed"] for x in out),
            "historical_context_count":sum(x["historical_context_only"] for x in out),
            "events":out, "research_only":True, "production_writes":False,
            "cache_reuse_authorized":False, "strategy_promoted":False,
            "issuer_payments_certified":0, "source_finality_verified":0}

def run(current_path, prior_path):
    result = rehearse(current_path, prior_path)
    blob = Path(current_path).read_bytes()
    require(sha(blob) == CURRENT_PIN, "INCIDENT_PIN_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(blob)) as z, TemporaryDirectory() as tmp:
        report = next(n for n in z.namelist() if n == REPORT_SUFFIX or n.endswith("/"+REPORT_SUFFIX))
        prefix = PurePosixPath(report).parent
        gap_name = str(prefix.parent / "issuer_ca_gap_audit.json")
        original = read_member(z, gap_name, 2_000_000)
        primary = Path(tmp) / "primary"
        primary.mkdir()
        files = {"report.json": 2_000_000, "unresolved_review.csv": 2_000_000}
        for sid, (_,_,kind,limit) in TARGETS.items():
            rel = "raw/" + sid.lower() + "." + kind + ".gz"
            if str(prefix / rel) in z.namelist():
                files[rel] = limit + 1_000_000
        for rel, limit in files.items():
            dest = primary / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(read_member(z, str(prefix / rel), limit))
        before = {rel:sha((primary / rel).read_bytes()) for rel in files}
        baseline = audit(primary)
        require(baseline == json.loads(original), "BASELINE_REPLAY_MISMATCH")
        sidecar = make_sidecar(baseline, sha(original), result)
        after = {rel:sha((primary / rel).read_bytes()) for rel in files}
        require(before == after and audit(primary) == baseline,
                "BASELINE_MUTATION_HOLD")
        sidecar["baseline_replay_equal"] = True
        sidecar["baseline_inputs_unchanged"] = True
        return sidecar

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("current")
    p.add_argument("prior")
    args = p.parse_args()
    print(json.dumps(run(args.current,args.prior),sort_keys=True))
