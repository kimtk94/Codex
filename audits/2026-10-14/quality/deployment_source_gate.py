"""Read-only Kalman Vercel repository-attestation preflight.

Accepts pre-collected Vercel get_git_deployment_context/get_deployment metadata.
It NEVER connects to Vercel, changes any deployment, or reads credentials.
Output is a gate verdict, not authority to deploy.
"""
from __future__ import annotations


def deployment_source_gate(snapshot: dict) -> dict:
    def hold(reason):
        return {"verdict": "RELEASE_HOLD", "reason": reason, "can_deploy": False}

    if not isinstance(snapshot, dict):
        return hold("INVALID_SOURCE_EVIDENCE")
    if snapshot.get("project_name") != "kalman-investment-hub-v2":
        return hold("WRONG_PROJECT")
    if snapshot.get("project_id") != "prj_KCDIl7qLqtBloI7pjRFQk2Itq7V1":
        return hold("PROJECT_ID_MISMATCH")
    expected = "kimtk94/Codex"
    if snapshot.get("expected_source_repository") != expected:
        return hold("EXPECTED_SOURCE_MISMATCH")
    if snapshot.get("linked_source_repository") != expected:
        return hold("LINKED_REPOSITORY_MISMATCH")
    if snapshot.get("production_deployment_source_repository") != expected:
        return hold("DEPLOYED_REPOSITORY_MISMATCH")
    commit = snapshot.get("production_deployment_commit")
    if not isinstance(commit, str) or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        return hold("DEPLOYED_COMMIT_UNVERIFIED")
    if snapshot.get("production_alias") != "kalman-investment-hub-v2.vercel.app":
        return hold("PRODUCTION_ALIAS_UNVERIFIED")
    if snapshot.get("runtime_js_attested") is not True:
        return hold("DEPLOYED_RUNTIME_JS_UNVERIFIED")
    return {"verdict": "SOURCE_ATTESTATION_PASS", "reason": "SOURCE_MATCHED",
            "can_deploy": False}  # passing provenance is NOT approval to release
