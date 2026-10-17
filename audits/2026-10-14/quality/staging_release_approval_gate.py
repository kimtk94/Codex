"""Fail-closed offline approval contract for any Kalman demo-only Staging deployment.

Never invokes Vercel, reads secrets, deploys, or mutates production.
Attestations are independent operator evidence, not source-code assumptions.
"""
import json
from pathlib import Path
from build_demo_only_staging import create, verify
ROOT=Path(__file__).resolve().parents[3]
PROJECT="prj_MpQ3qSpSW4QBRvw6aPvS3BYUtFFt"
EVIDENCE=ROOT/"audits/2026-10-15/staging_protection_snapshot.json"

def gate(snapshot, attestations=None):
    def hold(reason):
        return {"status":"STAGING_HOLD","reason":reason,"deployment_authorized":False}
    if snapshot.get("staging_project_id")!=PROJECT:
        return hold("WRONG_STAGING_PROJECT")
    files=create()
    verify(files)
    if snapshot.get("staging_sso_enabled") is not True and snapshot.get("staging_password_protection_enabled") is not True:
        return hold("STAGING_ACCESS_PROTECTION_MISSING")
    if not isinstance(attestations,dict):
        return hold("INDEPENDENT_EVIDENCE_MISSING")
    requirements=(
        "protected_alias_reverified",
        "environment_variable_names_audited",
        "zero_production_credentials_attested",
        "no_production_db_access_attested",
        "demo_only_30_file_digest_confirmed",
        "api_handlers_disabled_confirmed",
        "separate_nonproduction_project_confirmed",
        "rollback_target_captured",
        "operator_approved_staging_only",
    )
    for key in requirements:
        if attestations.get(key) is not True:
            return hold("MISSING_ATTESTATION:"+key)
    return {"status":"PREFLIGHT_REVIEW_COMPLETE",
            "reason":"DEPLOYMENT_REQUIRES_SEPARATE_APPROVED_ACTION",
            "deployment_authorized":False}

if __name__=="__main__":
    print(json.dumps(gate(json.loads(EVIDENCE.read_text())),sort_keys=True))
