"""Downstream read-only replay: never substitutes the historical-context sidecar."""
import argparse
import io
import json
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
import zipfile

from origin_sidecar import run as sidecar_run, ROOT, require
from cache_rehearsal import CURRENT_PIN, PRIOR_PIN
from evidence_review import REPORT_SUFFIX, read_member, sha
from official_price_proof_obligations import run as proof_run
from issuer_ca_provider_reconciliation import run as lineage_run

CONFIG = ROOT / "research/kalman_daily20/universe.json"
LINEAGE = ROOT / "research/kalman_daily20/issuer_ca_secondary_vendor_lineage.json"
INPUTS = ("source_finality/report.json", "price_basis_bridge/report.json",
          "corporate_actions/report.json", "issuer_ca_gap_audit.json")
PROVIDER_INPUTS = ("issuer_qld2023_api/report.json", "issuer_qqq2018_rule/report.json")
OPTIONAL = ("issuer_qld2023_api/qld_2023_proshares_api_raw_response.bin.gz",
            "issuer_qqq2018_rule/qqq_2018_amendment_6_original.html.gz")

def archive_inputs(path, pin, root, include_lineage=False):
    payload = Path(path).read_bytes()
    require(sha(payload) == pin, "DOWNSTREAM_ARCHIVE_PIN_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        matches = [n for n in z.namelist() if n == REPORT_SUFFIX or n.endswith("/"+REPORT_SUFFIX)]
        require(len(matches)==1, "DOWNSTREAM_PREFIX_HOLD")
        prefix = PurePosixPath(matches[0]).parent.parent
        wanted = list(INPUTS)
        if include_lineage:
            wanted += list(PROVIDER_INPUTS)
            wanted += [n for n in OPTIONAL if str(prefix/n) in z.namelist()]
        for rel in wanted:
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(read_member(z,str(prefix/rel),10_000_000))
        archived = {}
        for rel in ("official_price_proof_obligations/report.json",
                    "official_price_proof_obligations/evidence_obligations.csv",
                    "issuer_ca_provider_reconciliation.json"):
            name = str(prefix/rel)
            if name in z.namelist():
                archived[rel] = read_member(z,name,10_000_000)
    return wanted,archived

def proof(root, out):
    return proof_run(CONFIG,*(root / p for p in INPUTS),out)

def lineage(root):
    return lineage_run(json.loads(LINEAGE.read_bytes()),
                       json.loads((root / INPUTS[-1]).read_bytes()),
                       root / "issuer_qld2023_api",root / "issuer_qqq2018_rule")

def check_proof(report):
    require(report["required_assets"] == 26 and len(report["rows"]) == 26
            and report["official_close_certified"] == 0
            and report["independent_factor_certified"] == 0
            and report["issuer_specific_cash_gaps"] == 2
            and report["strategy_promoted"] is False
            and report["production_writes"] is False
            and report["live_execution"] is False
            and all(r["close_certified"] is False for r in report["rows"]),
            "DOWNSTREAM_PROOF_PROMOTION_HOLD")

def check_lineage(report):
    require(report["issuer_distribution_payments_certified"] == 0
            and report["source_finality_verified_assets"] == 0
            and report["strategy_promoted"] is False
            and report["production_writes"] is False
            and report["status"] == "TWO_CORPORATE_ACTION_SOURCE_DISAGREEMENTS_HOLD",
            "DOWNSTREAM_LINEAGE_PROMOTION_HOLD")

def run(current, prior):
    with TemporaryDirectory() as t:
        root=Path(t)
        cur=root/"incident"; old=root/"prior"
        wanted,cur_arch=archive_inputs(current,CURRENT_PIN,cur)
        old_wanted,old_arch=archive_inputs(prior,PRIOR_PIN,old,True)
        before={str(p):sha(p.read_bytes()) for p in
                [cur/n for n in wanted]+[old/n for n in old_wanted]}
        old_proof=proof(old,root/"prior-proof")
        old_lineage=lineage(old)
        check_proof(old_proof);check_lineage(old_lineage)
        require(old_proof==json.loads(old_arch["official_price_proof_obligations/report.json"])
                and (root/"prior-proof/evidence_obligations.csv").read_bytes()==
                old_arch["official_price_proof_obligations/evidence_obligations.csv"],
                "PRIOR_PROOF_ARCHIVED_PARITY_HOLD")
        require(old_lineage==json.loads(old_arch["issuer_ca_provider_reconciliation.json"]),
                "PRIOR_LINEAGE_ARCHIVED_PARITY_HOLD")
        baseline=proof(cur,root/"incident-before")
        check_proof(baseline)
        side=sidecar_run(current,prior)
        require(side["baseline_gap_sha256"]==sha((cur/INPUTS[-1]).read_bytes()),
                "SIDECAR_BASELINE_PIN_MISMATCH")
        # Separate sidecar, no consumer path replacement; rerun existing module.
        (cur/"issuer_effective_context_sidecar.json").write_text(json.dumps(side))
        after=proof(cur,root/"incident-after")
        check_proof(after)
        require(after==baseline and
                (root/"incident-before/evidence_obligations.csv").read_bytes()==
                (root/"incident-after/evidence_obligations.csv").read_bytes(),
                "INCIDENT_PROOF_SIDECAR_DRIFT")
        require(lineage(old)==old_lineage,"PRIOR_LINEAGE_SIDECAR_DRIFT")
        require(all(sha(Path(p).read_bytes())==h for p,h in before.items()),
                "DOWNSTREAM_INPUT_MUTATION")
        # Incident stopped before lineage. No mixing prior API outputs into current.
        require("issuer_ca_provider_reconciliation.json" not in cur_arch,
                "INCIDENT_LINEAGE_AVAILABILITY_CHANGED")
        return {"status":"DOWNSTREAM_SHADOW_PARITY_HOLD",
                "prior_proof_archived_equal":True,"prior_lineage_archived_equal":True,
                "incident_proof_before_after_equal":True,"incident_lineage":"NOT_CAPTURED_NOT_RECONSTRUCTED",
                "input_files_unchanged":len(before),"incident_session":baseline["session"],
                "prior_session":old_proof["session"],"official_close_certified":0,
                "independent_factor_certified":0,"issuer_payments_certified":0,
                "research_only":True,"production_writes":False,
                "cache_reuse_authorized":False,"strategy_promoted":False}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("current");p.add_argument("prior")
    a=p.parse_args();print(json.dumps(run(a.current,a.prior),sort_keys=True))
