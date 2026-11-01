#!/usr/bin/env python3
"""Read-only CSS protected Preview readiness, never release authorization.

Source: GitHub PR #487, Vercel Preview API, Google acceptance ledger.
Output: no customer names, raw tokens, contract identifiers, OAuth cookies, or emails.
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = "kimtk94/Codex"
PR = 487
PROJECT = "prj_OmMNFDQA3dfpAAbCdKvfFtwD9IBO"
TEAM = "team_eklxTMfdySLBHexmheTiWGCE"
SHEET = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
RELEASE = ("Owner-authenticated Preview E2E", "Production READY SHA parity",
           "Production acceptance")


def evaluate(pr, project, deployments, ledger):
    """Classify evidence, not the right to merge or release."""
    sha = str((pr.get("head") or {}).get("sha") or "")
    open_pr = pr.get("state") == "open" and pr.get("number") == PR
    protection = project.get("ssoProtection") or {}
    # Vercel's native GET schema reports ssoProtection.deploymentType.
    # Some clients normalize this further to an `enabled` boolean, but
    # the raw API is allowed to omit that boolean entirely.
    protected_modes = {"preview", "all", "all_except_custom_domains",
                       "prod_deployment_urls_and_all_previews"}
    sso_enabled = (isinstance(protection, dict)
                   and protection.get("deploymentType") in protected_modes
                   and protection.get("enabled") is not False)
    entries = deployments.get("deployments") or []
    matching = sorted((x for x in entries
                       if x.get("target") != "production"
                       and (x.get("meta") or {}).get("githubCommitSha") == sha
                       and (x.get("state") or x.get("readyState")) == "READY"),
                      key=lambda x: x.get("created", 0), reverse=True)
    preview = matching[0] if matching else {}
    host = str(preview.get("url") or "")
    if host and (not host.endswith(".vercel.app") or "/" in host):
        host = ""
    header = ["Area", "Check", "Result", "Gate", "Evidence KST",
              "Observed", "Next action", "Checked KST"]
    rows = ledger.get("values") or []
    valid_header = bool(rows) and rows[0][:8] == header
    states = {}
    if valid_header:
        for row in rows[1:]:
            if len(row) > 3 and row[1] in RELEASE:
                if row[1] in states or row[3] != "RELEASE":
                    valid_header = False
                    break
                states[row[1]] = row[2]
    gate_complete = valid_header and len(states) == len(RELEASE)
    # A green job says only that evidence was read; the owner E2E still needs
    # a live OAuth browser test with independent manual acceptance.
    source_ready = bool(open_pr and len(sha) == 40 and sso_enabled
                        and preview and host and gate_complete)
    return {
        "state": "READY_FOR_OWNER_OAUTH_E2E" if source_ready else "BLOCK_READINESS",
        "pr_open": open_pr,
        "pr_sha_prefix": sha[:12],
        "exact_sha_preview_ready": bool(preview and host),
        "preview_sha_prefix": str((preview.get("meta") or {}).get("githubCommitSha") or "")[:12],
        "preview_url": "https://" + host if host else "",
        "vercel_sso_enabled": sso_enabled,
        "acceptance_ledger_schema_valid": gate_complete,
        "acceptance_release_states": states if gate_complete else {},
        "owner_authenticated_browser_e2e": "NOT_VERIFIED_BY_THIS_AUDIT",
        "production_approval": False,
        "production_deploy": False,
    }


def get_json(url, token):
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "css-preview-readonly-evidence"})
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def main():
    gh = os.environ.get("GH_READ_TOKEN", "")
    vt = os.environ.get("VERCEL_TOKEN", "")
    sa = os.environ.get("CKD_DRIVE_SA_JSON", "")
    if not (gh and vt and sa):
        raise RuntimeError("REQUIRED_READ_CREDENTIALS_MISSING")
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    creds = service_account.Credentials.from_service_account_info(
        json.loads(sa), scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    creds.refresh(Request())
    params = urllib.parse.urlencode({"teamId": TEAM})
    pr = get_json("https://api.github.com/repos/" + REPO + "/pulls/" + str(PR), gh)
    project = get_json("https://api.vercel.com/v9/projects/" + PROJECT + "?" + params, vt)
    list_q = urllib.parse.urlencode({"teamId": TEAM, "projectId": PROJECT, "limit": 100})
    deployments = get_json("https://api.vercel.com/v6/deployments?" + list_q, vt)
    tab = urllib.parse.quote("'CSS Operational Acceptance'!A1:H20", safe="")
    ledger = get_json("https://sheets.googleapis.com/v4/spreadsheets/" + SHEET
                      + "/values/" + tab, creds.token)
    result = evaluate(pr, project, deployments, ledger)
    result["checked_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    dest = Path("audit-results/css-preview-release-evidence.json")
    dest.parent.mkdir(exist_ok=True, parents=True)
    dest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("CSS_PREVIEW_EVIDENCE=" + json.dumps(result, sort_keys=True))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write("## CSS Preview release evidence — read only\n\n")
            stream.write("Readiness: **" + result["state"] + "**; SHA parity: **"
                         + str(result["exact_sha_preview_ready"]) + "**; SSO: **"
                         + str(result["vercel_sso_enabled"]) + "**.\n\n")
            stream.write("Owner OAuth browser E2E: **NOT_VERIFIED_BY_THIS_AUDIT**. "
                         "Production approval: **BLOCK**. No deployment or Sheets write.\n")
    return result


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # No URLs, credentials, customer content, or exception message.
        print("CSS_PREVIEW_EVIDENCE_READ_FAILED=" + type(exc).__name__)
        raise SystemExit(1)
