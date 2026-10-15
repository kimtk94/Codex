"""Pure static audit of complete, generated Kalman Hub 30-file candidate.

This tool does not make HTTP requests, import/execute generated JS, deploy to
Vercel, open a broker account, or access Neon. Static indicators do not prove
actual API availability or auth enforcement. Release decisions fail closed.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from hub_offline_release_gate import decode_manifest, EXPECTED_NAMES

ROOT=Path(__file__).resolve().parents[3]
SNAPSHOT=ROOT/"audits/2026-10-15/staging_protection_snapshot.json"
MANIFEST=ROOT/"kalman-hub-recovery/v7.4.36/source_manifest.ndjson"

# Endpoint names alone are not proof of write capability. They are
# explicitly treated as requiring review, not as confirmed vulnerabilities.
SENSITIVE_API_PATHS={
  "api/analyze.js",
  "api/ingest/etf.js",
  "api/ingest/manual-snapshot.js",
  "api/position-ledger-tick.js",
  "api/position-ledger.js",
  "api/position.js",
}
MUTATING_SQL=re.compile(r"\b(INSERT\s+INTO|UPDATE\s+[A-Za-z_]|DELETE\s+FROM|TRUNCATE\s+|CREATE\s+TABLE|DROP\s+TABLE|ALTER\s+TABLE)\b",re.I)
WRITE_METHOD=re.compile(r"\b(?:POST|PUT|PATCH|DELETE)\b")
METHOD_DISPATCH=re.compile(r"\b(?:req|request)\.method\b")
ENV_NAME=re.compile(r"\bprocess\.env\.([A-Za-z_][A-Za-z0-9_]*)")


def scan_source(files:dict[str,bytes])->dict:
    if set(files)!=EXPECTED_NAMES:
        raise ValueError("INCOMPLETE_30_FILE_BUNDLE")
    apis=sorted(k for k in files if k.startswith("api/") and k.endswith(".js"))
    if len(apis)!=12:
        raise ValueError("UNEXPECTED_API_SURFACE")
    audit=[]
    for path in apis:
        code=files[path].decode("utf-8")
        # Disclosure-safe: report booleans and variable NAMES, never raw
        # JS, literal SQL strings, API credentials, headers or payloads.
        declared_env=sorted(set(ENV_NAME.findall(code)))
        audit.append({
           "route":"/"+path[:-3],
           "file":path,
           "has_http_method_dispatch":bool(METHOD_DISPATCH.search(code)),
           "mentions_mutating_http_verb":bool(WRITE_METHOD.search(code)),
           "mentions_mutating_sql":bool(MUTATING_SQL.search(code)),
           "references_environment_variable_names":declared_env,
           "requires_manual_auth_review":path in SENSITIVE_API_PATHS,
        })
    return {
      "route_count":len(apis),
      "routes":audit,
      "sensitive_route_count":sum(1 for e in audit if e["requires_manual_auth_review"]),
      "mutating_sql_marker_routes":[e["route"] for e in audit if e["mentions_mutating_sql"]],
      "http_write_verb_marker_routes":[e["route"] for e in audit if e["mentions_mutating_http_verb"]],
      "source_only_not_runtime_attested":True,
    }


def stage_decision(snapshot:dict, surface:dict)->dict:
    def hold(reason:str):
        return {"verdict":"STAGING_RELEASE_HOLD","reason":reason,
                "can_deploy":False}
    if not isinstance(snapshot,dict) or not isinstance(surface,dict):
        return hold("INVALID_EVIDENCE")
    if snapshot.get("staging_project_id")!="prj_MpQ3qSpSW4QBRvw6aPvS3BYUtFFt":
        return hold("INCORRECT_STAGING_TARGET")
    if surface.get("route_count")!=12 or surface.get("source_only_not_runtime_attested") is not True:
        return hold("UNVERIFIED_API_SURFACE")
    if snapshot.get("staging_sso_enabled") is not True and (
        snapshot.get("staging_password_protection_enabled") is not True
        and snapshot.get("staging_network_isolation_verified") is not True
    ):
        return hold("STAGING_AUTH_PROTECTION_MISSING")
    if snapshot.get("staging_credentials_isolated_verified") is not True:
        return hold("STAGING_CREDENTIAL_ISOLATION_MISSING")
    if snapshot.get("staging_database_isolation_verified") is not True:
        return hold("STAGING_DATABASE_ISOLATION_MISSING")
    if snapshot.get("staging_runtime_api_access_verified") is not True:
        return hold("STAGING_ACCESS_CONTROL_UNVERIFIED")
    if any(x.get("requires_manual_auth_review") for x in surface.get("routes",[])):
        # All 12 route implementations, especially the six sensitive paths,
        # require independently reviewed runtime auth/method contracts.
        if snapshot.get("staging_endpoint_auth_review_complete") is not True:
            return hold("STAGING_SENSITIVE_API_REVIEW_INCOMPLETE")
    if snapshot.get("staging_operator_approved") is not True:
        return hold("OPERATOR_APPROVAL_MISSING")
    return {"verdict":"READY_FOR_SEPARATE_OPERATOR_REVIEW",
            "reason":"ALL_DECLARED_PREFLIGHT_FIELDS_PRESENT",
            "can_deploy":False}


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--output",default="")
    a=cli.parse_args()
    source=decode_manifest(MANIFEST.read_text(encoding="utf-8"))
    surface=scan_source(source)
    snap=json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    report={"source":"OFFLINE_BUILT_BUNDLE",
            "surface":surface,
            "stage_preflight":stage_decision(snap,surface),
            "deployed":False,"production_changed":False}
    if a.output:
        p=Path(a.output)
        p.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"route_count":surface["route_count"],
                      "sensitive_route_count":surface["sensitive_route_count"],
                      "mutating_sql_marker_routes":surface["mutating_sql_marker_routes"],
                      "http_write_verb_marker_routes":surface["http_write_verb_marker_routes"],
                      "stage_preflight":report["stage_preflight"]},
                     ensure_ascii=False,sort_keys=True))


if __name__=="__main__":
    main()
