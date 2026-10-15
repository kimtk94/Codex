"""Kalman multi-domain release rehearsal (offline, read-only artifacts only).

Comparing captured GET-only Vercel alias snapshots is NOT a deployment.
The only accepted source is a freshly captured, independently reviewed
deployment/alias/config snapshot. No network, tokens, database, or writes.
"""
from __future__ import annotations

import json
from pathlib import Path

MAIN = "kalman-investment-hub-v2.vercel.app"
US = "kalman-investment-hub-us.vercel.app"
KR = "kalman-investment-hub-kr.vercel.app"
STAGING = "kalman-investment-hub-v2-staging.vercel.app"
REQUIRED = (MAIN, US, KR, STAGING)
EXPECTED_REWRITE = f"https://{MAIN}/api/:path*"


def baseline_snapshot_path():
    return Path(__file__).resolve().parents[2] / "2026-10-15/vercel_actual_alias_snapshot.json"


def check_snapshot(snapshot: dict) -> dict:
    def hold(reason, **extra):
        return {"status":"HOLD", "reason":reason,
                "can_deploy":False, **extra}

    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("domains"), dict):
        return hold("INVALID_SNAPSHOT")
    domains = snapshot["domains"]
    if set(domains) != set(REQUIRED):
        return hold("CRITICAL_DOMAIN_SET_MISMATCH")
    for host in REQUIRED:
        d = domains[host]
        if not isinstance(d, dict):
            return hold("INVALID_DOMAIN_METADATA", host=host)
        if not isinstance(d.get("alias_deployment_id"), str) or not d["alias_deployment_id"].startswith("dpl_"):
            return hold("ACTIVE_ALIAS_ID_MISSING", host=host)
        if not isinstance(d.get("project_id"), str) or not d["project_id"].startswith("prj_"):
            return hold("PROJECT_ID_MISSING", host=host)
    if domains[MAIN].get("role") != "shared_api_origin":
        return hold("MAIN_ROLE_CHANGED")
    if not domains[MAIN].get("has_api_assets_file"):
        return hold("MAIN_API_ASSETS_FILE_NOT_ATTESTED")
    for host in (US, KR):
        d=domains[host]
        if d.get("api_rewrite") != EXPECTED_REWRITE:
            return hold("SHARED_API_REWRITE_CHANGED",host=host)
        if d.get("alias_deployment_id") == domains[MAIN].get("alias_deployment_id"):
            return hold("CROSS_PROJECT_ALIAS_COLLISION",host=host)
    affected=(MAIN, US, KR)
    return {"status":"BASELINE_VALIDATED",
            "can_deploy":False,
            "shared_api_clients":list(affected),
            "direct_api_origin":MAIN,
            "release_requires_cross_site_acceptance":True}


def compare_active_aliases(baseline:dict, observed:dict) -> dict:
    first, second=check_snapshot(baseline),check_snapshot(observed)
    if first["status"] != "BASELINE_VALIDATED":
        return {"status":"HOLD","reason":"INVALID_BASELINE","can_deploy":False}
    if second["status"] != "BASELINE_VALIDATED":
        return {"status":"HOLD","reason":"INVALID_OBSERVATION:"+second["reason"],
                "can_deploy":False}
    changed=[]
    for host in REQUIRED:
        old, new=baseline["domains"][host],observed["domains"][host]
        for key in ("project_id","alias_deployment_id","api_rewrite"):
            if old.get(key) != new.get(key):
                changed.append({"site":host,"field":key})
    if baseline.get("linked_repo") != observed.get("linked_repo"):
        changed.append({"site":MAIN,"field":"linked_repo"})
    return {"status":"RECHECK_REQUIRED" if changed else "UNCHANGED",
            "can_deploy":False,"changed":changed,
            "downstream_impacted":list((MAIN,US,KR)) if any(x["site"]==MAIN for x in changed) else []}


def release_verdict(snapshot:dict, *, live_checks:dict|None=None):
    shape=check_snapshot(snapshot)
    if shape["status"] != "BASELINE_VALIDATED":
        return {"verdict":"PRODUCTION_HOLD","reason":shape.get("reason"),
                "release_authorized":False}
    if snapshot.get("linked_repo") != snapshot.get("intended_repo"):
        return {"verdict":"PRODUCTION_HOLD","reason":"MAIN_GIT_SOURCE_MISMATCH",
                "release_authorized":False,
                "affected_domains":[MAIN,US,KR]}
    if not all(snapshot["domains"][h].get("full_runtime_js_attested") is True for h in REQUIRED):
        return {"verdict":"PRODUCTION_HOLD","reason":"LIVE_BUNDLE_NOT_ATTESTED",
                "release_authorized":False}
    if not isinstance(live_checks,dict) or not all(live_checks.get(k) is True for k in (
        "read_only_endpoints_verified",
        "main_api_unverified_net_masked",
        "us_kr_downstream_smoke_pass",
        "rollback_alias_ids_verified",
        "source_sha_matched",
        "no_order_capability_enabled",
    )):
        return {"verdict":"PRODUCTION_HOLD","reason":"CROSS_SITE_SMOKE_NOT_ATTESTED",
                "release_authorized":False}
    if not all(snapshot.get(k) is True for k in (
        "historical_p1_mirror_net_returns_corrected",
        "independent_broker_fee_provenance",
        "server_runtime_sha_verified",
    )):
        return {"verdict":"PRODUCTION_HOLD","reason":"BROKER_OR_SERVER_PROVENANCE_MISSING",
                "release_authorized":False}
    if snapshot.get("operator_approved_production_change") is not True:
        return {"verdict":"PRODUCTION_HOLD","reason":"OPERATOR_APPROVAL_MISSING",
                "release_authorized":False}
    # This is a preflight, not a safe mechanism for executing a deployment.
    return {"verdict":"PREFLIGHT_REVIEW_READY","reason":"REQUIRES_SEPARATE_OPERATOR_RELEASE",
            "release_authorized":False}


def main():
    snap=json.loads(baseline_snapshot_path().read_text(encoding="utf-8"))
    print(json.dumps({"snapshot":check_snapshot(snap),
                      "comparison":compare_active_aliases(snap,snap),
                      "release":release_verdict(snap)},indent=2))


if __name__=="__main__":
    main()
