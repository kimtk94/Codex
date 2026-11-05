#!/usr/bin/env python3
"""Validate HCC research verification ledger and guard manuscript claim upgrades.

This is a structural and provenance lint, NOT a substitute for clinical,
statistical, image-mask registration or RNA QC. PASS cannot be assigned by CI.
"""
import argparse
import csv
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
LEDGER = HERE / "HCC_VERIFICATION_LEDGER.csv"
FIELDS = [
    "id", "track", "checkpoint", "status", "observed",
    "pass_evidence_required", "claim_ceiling", "next_action",
    "evidence_url", "last_checked_kst",
]
STATUSES = {
    "PASS_METADATA", "PASS_TECHNICAL", "PARTIAL", "PENDING",
    "BLOCKED", "NOT_APPLICABLE",
}
EVIDENCE_STATES = {"PASS_METADATA", "PASS_TECHNICAL", "PARTIAL", "BLOCKED"}
EXPECTED_IDS = {"HCC-%02d" % i for i in range(1, 28)}
STRONG = {"PASS_METADATA", "PASS_TECHNICAL"}


def check(rows):
    if not rows:
        raise ValueError("Empty research verification ledger")
    ids = [r.get("id", "") for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate HCC verification IDs")
    if set(ids) != EXPECTED_IDS:
        raise ValueError(f"Unexpected ledger IDs. Missing={sorted(EXPECTED_IDS-set(ids))} Extra={sorted(set(ids)-EXPECTED_IDS)}")
    status_by_id = {}
    for row in rows:
        rid = row["id"]
        status = row["status"]
        if status not in STATUSES:
            raise ValueError(f"{rid}: invalid status {status}")
        if not row["checkpoint"].strip() or not row["pass_evidence_required"].strip():
            raise ValueError(f"{rid}: missing task or specific acceptance evidence")
        if not row["next_action"].strip() or not row["last_checked_kst"].strip():
            raise ValueError(f"{rid}: next action and last check date required")
        if row["claim_ceiling"] not in {"S0", "S1", "S2", "S3", "S4", "S5"}:
            raise ValueError(f"{rid}: invalid manuscript claim ceiling")
        if status in EVIDENCE_STATES and not row["evidence_url"].startswith("https://"):
            raise ValueError(f"{rid}: status {status} lacks evidence URL")
        if status == "NOT_APPLICABLE" and len(row["observed"].strip()) < 12:
            raise ValueError(f"{rid}: N/A requires explicit rationale")
        status_by_id[rid] = status

    # Regression guards against previously observed accidental inference jumps.
    if status_by_id["HCC-07"] != "PASS_TECHNICAL":
        for rid in ("HCC-02", "HCC-03", "HCC-04", "HCC-05", "HCC-06"):
            if next(r for r in rows if r["id"] == rid)["claim_ceiling"] != "S0":
                raise ValueError("CT metadata or organ SEG cannot imply tumor ROI qualified patients")
    if status_by_id["HCC-12"] != "PASS_TECHNICAL":
        for rid in ("HCC-08", "HCC-09", "HCC-10", "HCC-11"):
            if next(r for r in rows if r["id"] == rid)["claim_ceiling"] != "S0":
                raise ValueError("MRI mask CRC/nonzero voxels without registration cannot imply S1")
    if status_by_id["HCC-20"] in STRONG:
        needs=("HCC-12","HCC-14","HCC-15","HCC-16","HCC-17","HCC-18","HCC-19")
        missing=[rid for rid in needs if status_by_id[rid] not in STRONG]
        if missing:
            raise ValueError(f"Associations cannot PASS before upstream gates: {missing}")
    if status_by_id["HCC-22"] in STRONG and status_by_id["HCC-20"] not in STRONG:
        raise ValueError("Replication cannot PASS without valid association")
    if status_by_id["HCC-23"] in STRONG and status_by_id["HCC-22"] not in STRONG:
        raise ValueError("Clinical significance cannot be promoted without replication")
    return len(rows)


def load(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames or list(reader.fieldnames) != FIELDS:
            raise ValueError("Ledger columns differ from expected schema")
        return list(reader)


def offline_test():
    rows=load(LEDGER)
    assert check(rows)==27
    try:
        bad=[dict(x) for x in rows]
        bad[0]["status"]="PASS_UNKNOWN"
        check(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("Unknown status must fail")

    try:
        bad=[dict(x) for x in rows]
        next(x for x in bad if x["id"]=="HCC-10")["claim_ceiling"]="S5"
        check(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("MRI nonempty mask must not imply S5")
    print("HCC_VERIFICATION_LEDGER_OFFLINE_TEST_PASS rows=27")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--file",default=str(LEDGER))
    p.add_argument("--offline-test",action="store_true")
    args=p.parse_args()
    if args.offline_test:
        offline_test()
    else:
        n=check(load(args.file))
        print(f"HCC_VERIFICATION_LEDGER_SCHEMA_AND_CLAIM_GUARDS_PASS rows={n}")


if __name__=="__main__":
    main()
