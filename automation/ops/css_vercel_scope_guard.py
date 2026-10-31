#!/usr/bin/env python3
"""Read-only confirmation of the CSS Vercel monorepo skip guard.

Never deploy, promote, alter SSO, or create protection bypass tokens.
"""
import json
import os
import urllib.parse
import urllib.request

PROJECT="prj_OmMNFDQA3dfpAAbCdKvfFtwD9IBO"
TEAM="team_eklxTMfdySLBHexmheTiWGCE"
ROOT="apps/css-sales-workspace"
IGNORE="git diff --quiet HEAD^ HEAD -- . ../../package.json ../../package-lock.json"

def assess(project):
    if not isinstance(project,dict) or project.get("id")!=PROJECT:
        raise ValueError("UNEXPECTED_VERCEL_PROJECT_ID")
    root=str(project.get("rootDirectory") or "")
    enabled=project.get("enableAffectedProjectsDeployments")
    ignore=str(project.get("commandForIgnoringBuildStep") or "").strip()
    root_match=root==ROOT
    affected=enabled is True
    ignore_match=ignore==IGNORE
    return {"project_root":"MATCH" if root_match else "BLOCK",
            "affected_projects":"ENABLED" if affected else "BLOCK",
            "ignored_build_step":"MATCH" if ignore_match else "BLOCK",
            "skip_guard":"VERIFIED" if (root_match and affected and ignore_match) else "NOT_VERIFIED",
            "preview_authenticated_browser_e2e":"NOT_VERIFIED",
            "production_authorized":False,
            "deployments_created":0}

def read_project(token):
    params=urllib.parse.urlencode({"teamId":TEAM})
    req=urllib.request.Request(
        "https://api.vercel.com/v9/projects/"+PROJECT+"?"+params,
        headers={"Authorization":"Bearer "+token,"Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=25) as reply:
        return json.load(reply)

def main():
    token=os.getenv("VERCEL_TOKEN","")
    if not token:
        print("CSS_VERCEL_SCOPE=NOT_VERIFIED_NO_TOKEN")
        return 2
    try:
        result=assess(read_project(token))
    except Exception as exc:
        # No raw response, token, URLs, or PII in CI logs.
        print("CSS_VERCEL_SCOPE=READ_FAILED:"+type(exc).__name__)
        return 2
    print("CSS_VERCEL_SCOPE="+json.dumps(result,sort_keys=True))
    summary=os.environ.get("GITHUB_STEP_SUMMARY","")
    if summary:
        with open(summary,"a",encoding="utf-8") as f:
            f.write("## CSS deployment scope (read only)\n\n")
            f.write("| Root | Affected-projects skip | Ignore script | Scope |\n")
            f.write("|---|---|---|---|\n")
            f.write("| "+result["project_root"]+" | "+result["affected_projects"]+
                    " | "+result["ignored_build_step"]+" | "+result["skip_guard"]+" |\n\n")
            f.write("Preview E2E: NOT_VERIFIED; Production promotion: NOT_AUTHORIZED.\n")
    return 0 if result["skip_guard"]=="VERIFIED" else 1

if __name__=="__main__":
    raise SystemExit(main())
