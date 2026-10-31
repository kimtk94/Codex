#!/usr/bin/env python3
"""Read-only Vercel CSS project/production SHA evidence. Never deploys or approves."""
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT = "prj_OmMNFDQA3dfpAAbCdKvfFtwD9IBO"
TEAM = "team_eklxTMfdySLBHexmheTiWGCE"
ROOT = "apps/css-sales-workspace"

def classify(main_sha, project, deployments, has_token=True):
    root = str(project.get("rootDirectory") or "")
    all_deploys = deployments.get("deployments", [])
    production = [d for d in all_deploys if d.get("target") == "production"]
    ready = [d for d in production if d.get("state") == "READY"]
    ready.sort(key=lambda x:x.get("created", 0), reverse=True)
    latest = ready[0] if ready else {}
    meta = latest.get("meta") or {}
    sha = str(meta.get("githubCommitSha") or (latest.get("gitSource") or {}).get("sha") or "")
    root_ok = root == ROOT
    parity = bool(has_token and len(main_sha)==40 and root_ok and sha and sha==main_sha)
    return {
        "read_state": "API_READ" if has_token else "NOT_CHECKED_NO_VERCEL_TOKEN",
        "root_status": "MATCH" if root_ok else "MISMATCH_OR_UNSET",
        "ready_production_found": bool(latest),
        "production_sha_parity": "MATCH" if parity else ("NOT_CHECKED" if not has_token else "BLOCK"),
        "production_sha_prefix": sha[:12],
        "main_sha_prefix": main_sha[:12],
        "owner_authenticated_browser_e2e": "NOT_VERIFIED",
        "production_release_approved": False,
        "deployment_created": False,
    }

def get_json(url, token):
    request = urllib.request.Request(
        url, headers={"Authorization":"Bearer "+token,
                      "Accept":"application/json", "User-Agent":"css-p0-readonly-verifier"})
    with urllib.request.urlopen(request, timeout=25) as reply:
        return json.load(reply)

def main():
    sha = os.environ.get("GITHUB_SHA", "")
    token = os.environ.get("VERCEL_TOKEN", "")
    if token:
        params = urllib.parse.urlencode({"teamId": TEAM})
        project = get_json("https://api.vercel.com/v9/projects/"+PROJECT+"?"+params, token)
        dep_params = urllib.parse.urlencode({"projectId":PROJECT,"teamId":TEAM,"target":"production","limit":20})
        deployments = get_json("https://api.vercel.com/v6/deployments?"+dep_params, token)
        output=classify(sha, project, deployments, True)
    else:
        output=classify(sha, {}, {}, False)
    folder=Path("audit-results")
    folder.mkdir(parents=True,exist_ok=True)
    (folder/"css-release-parity.json").write_text(json.dumps(output,indent=2)+"\n",encoding="utf-8")
    print("CSS_VERCEL_READONLY_AUDIT="+json.dumps(output,sort_keys=True))
    step_summary=os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary,"a",encoding="utf-8") as handle:
            handle.write("## CSS Production read-only check\n\n")
            handle.write("Production SHA parity: **"+output["production_sha_parity"]+"**; "
                "project root: **"+output["root_status"]+"**.\n\n")
            handle.write("Owner-authenticated browser E2E remains NOT_VERIFIED. No deploy or promotion.\n")
    if token and not project:
        raise RuntimeError("EMPTY_VERCEL_PROJECT_METADATA")

if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        # Avoid URL/token/customer data exposure in CI.
        print("CSS_VERCEL_READONLY_AUDIT_FAILED="+type(exc).__name__)
        raise SystemExit(1)
