"""Novogene CSS P0 release evidence evaluator.

Report-only. No server, Google Sheets, mail, CRM, SQLite or network access.
Never authorizes a production rollout. Missing, stale, or partial evidence
fails closed. Evidence manifests must contain aggregate-only statuses.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

UTC = dt.timezone.utc
MAX_BYTES = 65536
VALID = frozenset({"PASS", "FAIL", "BLOCKED", "PARTIAL", "NOT_RUN", "NOT_REQUESTED", "UNKNOWN"})
MAX_AGE_DAYS = {
    "source_fingerprint": 2,
    "project_sqlite_integrity": 2,
    "mail_sqlite_integrity": 2,
    "offsite_project_mail_restore": 7,
    "manual_hold_skip_regression": 14,
    "sif_large_batch_regression": 14,
    "synthetic_sheet_readback": 14,
    "runtime_health": 1,
    "full_engine_sink_isolation": 7,
    "isolated_full_css_main": 7,
    "manual_deployment_approval": 1,
}

def parse_utc(value: Any) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None or moment.utcoffset() != dt.timedelta(0):
        return None
    return moment.astimezone(UTC)

def evaluate(manifest: Any, *, now: dt.datetime | None = None) -> dict[str, Any]:
    """Return only predefined check names and statuses, never manifest payloads."""
    now = now or dt.datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(UTC)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("unsupported manifest schema")
    if manifest.get("environment") not in ("staging", "synthetic"):
        raise ValueError("production evidence manifests are not accepted")
    checks = manifest.get("checks")
    if not isinstance(checks, dict):
        raise ValueError("checks must be an object")
    summary = {}
    blockers = []
    for gate, limit in MAX_AGE_DAYS.items():
        item = checks.get(gate)
        status = item.get("status") if isinstance(item, dict) else None
        reason = status if isinstance(status, str) and status in VALID else "UNKNOWN"
        if reason == "PASS":
            observed = parse_utc(item.get("observed_at_utc"))
            if observed is None:
                reason = "MISSING_TIMESTAMP"
            elif observed > now + dt.timedelta(minutes=5):
                reason = "FUTURE_TIMESTAMP"
            elif now - observed > dt.timedelta(days=limit):
                reason = "STALE_EVIDENCE"
        summary[gate] = reason
        if reason != "PASS":
            blockers.append({"gate": gate, "reason": reason})
    ready = not blockers
    return {
        "schema_version": 1,
        "generated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "evaluation": "READY_FOR_HUMAN_REVIEW" if ready else "BLOCKED",
        "ready_for_human_review": ready,
        "production_deploy_authorized": False,
        "checks_passed": sum(x == "PASS" for x in summary.values()),
        "checks_required": len(MAX_AGE_DAYS),
        "checks": summary,
        "blocking_checks": blockers,
        "disclaimer": "Evidence report only; not a full CSS E2E test or deployment approval",
    }

def synthetic_example(*, now: dt.datetime | None = None) -> dict[str, Any]:
    stamp = (now or dt.datetime.now(UTC)).astimezone(UTC).isoformat().replace("+00:00", "Z")
    checks = {name: {"status": "PASS", "observed_at_utc": stamp} for name in MAX_AGE_DAYS}
    checks["runtime_health"]["status"] = "UNKNOWN"
    checks["full_engine_sink_isolation"]["status"] = "BLOCKED"
    checks["isolated_full_css_main"]["status"] = "NOT_RUN"
    checks["manual_deployment_approval"]["status"] = "NOT_REQUESTED"
    return {"schema_version": 1, "environment": "synthetic", "checks": checks}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest", type=Path)
    source.add_argument("--synthetic-demo", action="store_true")
    parser.add_argument("--expect-blocked", action="store_true")
    args = parser.parse_args()
    if args.synthetic_demo:
        manifest = synthetic_example()
    else:
        if args.manifest.is_symlink() or not args.manifest.is_file():
            parser.error("manifest must be an existing non-symlink file")
        if args.manifest.stat().st_size > MAX_BYTES:
            parser.error("manifest too large")
        with args.manifest.open(encoding="utf-8") as fh:
            manifest = json.load(fh)
    try:
        result = evaluate(manifest)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return int(args.expect_blocked and result["evaluation"] != "BLOCKED")

if __name__ == "__main__":
    raise SystemExit(main())
