#!/usr/bin/env python3
"""Read-only verification of Vercel Hobby team's automatic Preview settings and rolling load.

Never creates deployments, modifies projects, authenticates as a web user, or emits tokens.
"""
import json
import os
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

TEAM = "team_eklxTMfdySLBHexmheTiWGCE"
PROJECTS = {
    "CSS": "prj_OmMNFDQA3dfpAAbCdKvfFtwD9IBO",
    "Kalman Lab": "prj_l66LJnDZKiHtCAIf8fpJpTFCALji",
    "Kalman Hub": "prj_KCDIl7qLqtBloI7pjRFQk2Itq7V1",
}
KNOWN_LIMIT = 100


def validate_projects(projects):
    """True only if all intended Vercel resources report Preview disabled."""
    states = {}
    for label, pid in PROJECTS.items():
        project = projects.get(label) or {}
        correct = project.get("id") == pid and project.get("accountId") == TEAM
        state = project.get("previewDeploymentsDisabled")
        sso = project.get("ssoProtection") or {}
        protected = sso.get("deploymentType") == "all_except_custom_domains"
        states[label] = {
            "project_identity_matches": bool(correct),
            "preview_deployments_disabled": state if isinstance(state, bool) else "UNKNOWN",
            "sso_protection_unchanged": protected,
        }
    return states, all(
        x["project_identity_matches"]
        and x["preview_deployments_disabled"] is True
        and x["sso_protection_unchanged"]
        for x in states.values()
    )


def classify_usage(deployments, start_ms, now_ms):
    """Count recorded attempts only, not internal quota chargeable events."""
    records = [x for x in deployments if start_ms <= int(x.get("created") or 0) <= now_ms]
    states = Counter(str(x.get("state") or x.get("readyState") or "UNKNOWN") for x in records)
    counts = Counter(str(x.get("name") or "OTHER") for x in records)
    return {"total_attempt_records": len(records),
            "state_counts": dict(sorted(states.items())),
            "project_counts": dict(sorted(counts.items())),
            "exceeds_100_record_reference": len(records) >= KNOWN_LIMIT,
            "count_is_not_authoritative_quota_charge": True}


def fetch(url, token):
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "css-team-deployment-readonly-audit"})
    with urllib.request.urlopen(req, timeout=25) as rep:
        return json.load(rep)


def read_deployments(token, now):
    end_ms = int(now.timestamp() * 1000)
    start_ms = int((now - timedelta(hours=24)).timestamp() * 1000)
    collected = []
    seen = set()
    # Four six-hour UTC ranges so the first page is not silently truncated.
    for i in range(4):
        lower = start_ms + i * 6 * 3600000
        upper = start_ms + (i + 1) * 6 * 3600000
        cursor = upper
        for _ in range(8):
            qs = urllib.parse.urlencode({
                "teamId": TEAM, "limit": 100, "since": lower, "until": cursor})
            result = fetch("https://api.vercel.com/v6/deployments?" + qs, token)
            page = result.get("deployments") or []
            if not page:
                break
            for item in page:
                uid = item.get("uid") or item.get("id")
                if uid and uid not in seen:
                    seen.add(uid)
                    collected.append(item)
            if len(page) < 100:
                break
            oldest = min(int(x.get("created") or cursor) for x in page)
            if oldest <= lower or oldest >= cursor:
                raise RuntimeError("DEPLOYMENT_PAGINATION_UNTRUSTWORTHY")
            cursor = oldest - 1
        else:
            raise RuntimeError("DEPLOYMENT_PAGINATION_LIMIT")
    return collected, start_ms, end_ms


def main():
    token = os.environ.get("VERCEL_TOKEN")
    if not token:
        raise RuntimeError("VERCEL_TOKEN_MISSING")
    projects = {}
    for name, pid in PROJECTS.items():
        qs = urllib.parse.urlencode({"teamId": TEAM})
        projects[name] = fetch(
            "https://api.vercel.com/v9/projects/" + pid + "?" + qs, token)
    states, all_disabled = validate_projects(projects)
    now = datetime.now(timezone.utc)
    records, start_ms, now_ms = read_deployments(token, now)
    usage = classify_usage(records, start_ms, now_ms)
    output = {
        "checked_utc": now.isoformat(timespec="seconds"),
        "projects": states,
        "all_three_preview_disabled": all_disabled,
        "rolling_24h": usage,
        "production_deployment_created": False,
        "production_approved": False,
    }
    path = Path("audit-results/css-vercel-preview-quota.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    print("CSS_VERCEL_PREVIEW_QUOTA=" + json.dumps(output, sort_keys=True))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("## Vercel team Preview generation audit\n\n")
            stream.write("| Project | Disabled Preview | Identity | SSO unchanged |\n")
            stream.write("|---|---|---|---|\n")
            for name, entry in states.items():
                stream.write(f"| {name} | {entry['preview_deployments_disabled']} | "
                             f"{entry['project_identity_matches']} | "
                             f"{entry['sso_protection_unchanged']} |\n")
            stream.write(f"\nRolling 24-hour recorded deployments: **{usage['total_attempt_records']}** "
                         "(not identical to provider quota counter).\n\n")
            stream.write("This read-only job did not deploy or promote production.\n")
    if not all_disabled:
        raise RuntimeError("PREVIEW_DISABLING_NOT_CONFIRMED")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("CSS_VERCEL_AUDIT_FAILED=" + type(exc).__name__)
        raise SystemExit(1)
