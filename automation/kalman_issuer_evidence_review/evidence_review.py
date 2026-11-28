"""Read-only evidence diagnostics; never certifies a payment or promotes a signal."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

TARGETS = {
    "QQQ_2018_SEC_2020_Q3_TABLE": (
        "QQQ|2018-06-18",
        "https://www.sec.gov/Archives/edgar/data/831001/000095010320014313/dp132922_424b2-us2006361.htm",
        "html", 6_000_000),
    "QLD_2025_FORM_8937_SPLIT": (
        "QLD|2023-09-20",
        "https://www.proshares.com/globalassets/proshares/form-8937/qld-form-8937.pdf",
        "pdf", 20_000_000),
}
VERIFIED = "PINNED_BYTES_REPORTED_ANCHORS_PAYMENT_UNCERTIFIED"
TRANSIENT = {"HTTP_403_SOURCE_HOLD", "HTTP_429_SOURCE_HOLD",
             "TimeoutError_SOURCE_HOLD", "URLError_SOURCE_HOLD"} | {
                 f"HTTP_{n}_SOURCE_HOLD" for n in range(500, 600)}
REPORT_SUFFIX = "issuer_ca_primary/report.json"

def sha(data):
    return hashlib.sha256(data).hexdigest()

def read_member(z, name, maximum):
    info = z.getinfo(name)
    if info.file_size > maximum:
        raise ValueError("ZIP_MEMBER_TOO_LARGE")
    with z.open(info) as f:
        data = f.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError("ZIP_MEMBER_TOO_LARGE")
    return data

def inspect_archive(path, expected_sha256):
    """The expected hash must come from independently trusted run metadata."""
    if not re.fullmatch("[a-f0-9]{64}", expected_sha256):
        raise ValueError("EXTERNAL_PIN_REQUIRED")
    path = Path(path)
    if path.stat().st_size > 100_000_000:
        raise ValueError("ZIP_TOO_LARGE")
    payload = path.read_bytes()
    if sha(payload) != expected_sha256:
        raise ValueError("ARCHIVE_PIN_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError("DUPLICATE_ZIP_MEMBER")
        matches = [n for n in names if n == REPORT_SUFFIX or n.endswith("/" + REPORT_SUFFIX)]
        if len(matches) != 1:
            raise ValueError("REPORT_MISSING_OR_AMBIGUOUS")
        report_path = matches[0]
        if "\\" in report_path or any(p in ("..", "") for p in report_path.split("/")):
            raise ValueError("UNSAFE_REPORT_PATH")
        prefix = str(PurePosixPath(report_path).parent)
        doc = json.loads(read_member(z, report_path, 2_000_000))
        # An archive can be diagnostic even if incomplete; no self-certification.
        result = {}
        for sid, (claim, url, kind, limit) in TARGETS.items():
            s = doc.get("source_results", {}).get(sid)
            item = {"state": "SOURCE_MISSING_HOLD", "fetch_status": None, "sha256": None}
            result[sid] = item
            if not isinstance(s, dict):
                continue
            status = s.get("status")
            item["fetch_status"] = status
            if s.get("source_id") != sid or s.get("url") != url:
                item["state"] = "SOURCE_IDENTITY_MISMATCH_HOLD"
                continue
            if s.get("source_claim_independently_certified") is not False:
                item["state"] = "SOURCE_GOVERNANCE_INVALID_HOLD"
                continue
            digest, rel = s.get("body_sha256"), s.get("raw_archive")
            if status != "FETCHED_SOURCE_UNCERTIFIED":
                # Only a clean absence on a known transient failure is eligible.
                clean = digest is None and rel is None and s.get("body_bytes") == 0
                item["state"] = ("TRANSIENT_UNAVAILABLE_HOLD" if clean and status in TRANSIENT
                                 else "SOURCE_NOT_VERIFIED_HOLD")
                continue
            expected_rel = "raw/" + sid.lower() + "." + kind + ".gz"
            if rel != expected_rel or not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}", digest):
                item["state"] = "SOURCE_PATH_OR_HASH_INVALID_HOLD"
                continue
            name = prefix + "/" + rel
            if name not in names:
                item["state"] = "SOURCE_RAW_MISSING_HOLD"
                continue
            try:
                compressed = read_member(z, name, limit + 1_000_000)
                with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as f:
                    raw = f.read(limit + 1)
            except (OSError, EOFError, ValueError):
                item["state"] = "SOURCE_ARCHIVE_INVALID_HOLD"
                continue
            if not raw or len(raw) > limit or len(raw) != s.get("body_bytes") or sha(raw) != digest:
                item["state"] = "SOURCE_BYTES_MISMATCH_HOLD"
                continue
            if kind == "pdf" and not raw.startswith(b"%PDF"):
                item["state"] = "SOURCE_TYPE_MISMATCH_HOLD"
                continue
            item["sha256"] = digest
            if s.get("anchor_grade_by_claim", {}).get(claim) != "BOTH_NEARBY_ANCHORS_OBSERVED":
                item["state"] = "SOURCE_ANCHORS_MISSING_HOLD"
                continue
            item["state"] = VERIFIED
        return {"archive_sha256": expected_sha256, "sources": result,
                "research_only": True, "production_writes": False,
                "strategy_promoted": False, "issuer_payments_certified": 0,
                "source_finality_verified": 0}

def compare(current, prior=None):
    """Candidate-only reuse classification; prior must be independently reviewed.
    No bytes are copied, no anchors are re-extracted, no writer is invoked.
    """
    prior_pair = prior is not None and all(
        prior["sources"][sid]["state"] == VERIFIED for sid in TARGETS)
    decisions = {}
    for sid in TARGETS:
        now = current["sources"][sid]
        old = prior["sources"][sid] if prior_pair else None
        if now["state"] == VERIFIED:
            decision = ("SOURCE_REVISION_REVIEW_HOLD" if old and now["sha256"] != old["sha256"]
                        else "CURRENT_EVIDENCE_PRESENT_PAYMENT_HOLD")
        elif now["state"] == "TRANSIENT_UNAVAILABLE_HOLD" and old:
            decision = "PRIOR_PINNED_EVIDENCE_REVIEW_CANDIDATE_HOLD"
        else:
            decision = "NO_REUSE_HOLD"
        decisions[sid] = decision
    return {"decisions": decisions, "prior_pair_available": prior_pair,
            "cache_reuse_authorized": False, "research_only": True,
            "production_writes": False, "strategy_promoted": False,
            "issuer_payments_certified": 0, "source_finality_verified": 0}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("archive")
    p.add_argument("--sha256", required=True)
    args = p.parse_args()
    current = inspect_archive(args.archive, args.sha256)
    print(json.dumps({"current": current, "comparison": compare(current)}, sort_keys=True))

if __name__ == "__main__":
    main()
