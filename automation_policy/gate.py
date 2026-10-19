"""Fail-closed automation policy gate. Standard library only. Does not execute actions."""
import json
import sys
from pathlib import Path

POLICY = json.loads((Path(__file__).parent / "policy.json").read_text(encoding="utf-8"))

def evaluate(action: str, evidence: dict | None = None) -> dict:
    evidence = evidence or {}
    rule = POLICY["actions"].get(action, POLICY["default"])
    if rule == "allow":
        return {"allowed": True, "reason": "policy_allow"}
    if rule == "allow_if_verified":
        requirements = POLICY["production_deploy_requirements"]
        missing = [k for k in requirements if evidence.get(k) is not True]
        if not missing and evidence.get("target") == "production" and evidence.get("commit_sha"):
            return {"allowed": True, "reason": "verified_release"}
        return {"allowed": False, "reason": "release_evidence_missing", "missing": missing}
    if rule == "approval":
        # Human approval must be validated by an independent approval service.
        # A caller-supplied boolean/token is NOT sufficient authorization.
        return {"allowed": False, "reason": "external_approval_required"}
    return {"allowed": False, "reason": "unknown_or_denied_action"}

def main():
    if len(sys.argv) != 2:
        print("usage: python -m automation_policy.gate '<JSON request>'", file=sys.stderr)
        return 2
    try:
        request = json.loads(sys.argv[1])
        result = evaluate(request["action"], request.get("evidence"))
        print(json.dumps(result, sort_keys=True))
        return 0 if result["allowed"] else 3
    except (ValueError, KeyError, TypeError):
        print(json.dumps({"allowed": False, "reason": "invalid_request"}))
        return 3

if __name__ == "__main__":
    raise SystemExit(main())
