#!/usr/bin/env python3
"""Read-only evidence tracker: GitHub PRs/Actions plus optional Sheets metadata.

Never upgrades task completion automatically. Output is aggregate-only JSON and Markdown.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = "kimtk94/Codex"
MASTER = "docs/automation-architecture-20261026/AUTOMATION_MASTER_PLAN.md"
SHEET_ID = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
EVIDENCE = {
    "A01": [202], "A03": [202], "A06": [247, 256], "A07": [259, 261],
    "A09": [264, 278], "A10": [283, 285], "A11": [278, 295],
    "A12": [287], "A13": [287, 288], "A14": [220], "A15": [290],
    "A16": [263], "A24": [265, 275], "A25": [269], "A26": [269, 270],
    "A27": [265], "A28": [291, 293, 296], "A31": [242],
    "A32": [242], "A34": [235], "A37": [201, 203], "A38": [235],
    "A42": [286], "A45": [234, 286], "A46": [289],
    "A47": [270], "A48": [256, 270],
}
# Explicit evidence candidates only; a PR is not proof of passing CI or business correctness.

def get(url, token=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "automation-progress-audit"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=18) as r:
        return json.load(r)

def tasks(text):
    pattern = re.compile(r"^\| (A\d{2}) \| ([^|]+) \| ([^|]+) \| (done|partial|todo) \|", re.M)
    matches = pattern.findall(text)
    if len(matches) != 50 or len(set(x[0] for x in matches)) != 50:
        raise ValueError("Expected exactly 50 unique source ledger entries")
    return [{"id":id, "domain":dom.strip(), "task":name.strip(), "baseline":st} for id, dom, name, st in matches]

def github(token):
    api = "https://api.github.com/repos/" + REPO
    prs = get(api + "/pulls?state=all&per_page=100&sort=updated&direction=desc", token)
    runs = get(api + "/actions/runs?per_page=100", token)["workflow_runs"]
    bypr = {int(p["number"]): {"url": p["html_url"], "state": p["state"],
        "merged": bool(p.get("merged_at")), "updated_at": p.get("updated_at"),
        "head_sha": p.get("head", {}).get("sha")} for p in prs}
    bysha = {}
    for r in runs:
        bysha.setdefault(r.get("head_sha"), []).append({
            "url": r.get("html_url"), "conclusion": r.get("conclusion"),
            "status": r.get("status"), "event": r.get("event"),
            "created_at": r.get("created_at")})
    return bypr, bysha

def sheet_probe():
    """Only read harmless metadata, optional credential. Never output raw cells."""
    raw = os.environ.get("CKD_DRIVE_SA_JSON") or os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        return {"state": "NOT_CHECKED", "reason": "service_account_unavailable"}
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
        info = json.loads(raw)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
        session = AuthorizedSession(creds)
        resp = session.get("https://sheets.googleapis.com/v4/spreadsheets/" + SHEET_ID,
            params={"fields": "spreadsheetId,properties(title),sheets(properties(title))"}, timeout=18)
        resp.raise_for_status()
        obj = resp.json()
        names = {x["properties"]["title"] for x in obj["sheets"]}
        required = {"Automation Health", "SFDC Email Ingest Audit", "BI Revenue Coverage 2025-26"}
        return {"state": "METADATA_OK", "sheet_count": len(names),
                "required_tabs_present": sorted(required & names),
                "required_tabs_missing": sorted(required - names)}
    except Exception as exc:
        return {"state": "FAILED", "reason_type": type(exc).__name__}

def build(master, pr_lookup, runs, sheet):
    result = []
    for task in tasks(master):
        prs = []
        for num in EVIDENCE.get(task["id"], []):
            if num in pr_lookup:
                p = dict(pr_lookup[num])
                p["number"] = num
                p["recent_runs"] = runs.get(p.get("head_sha"), [])[:3]
                prs.append(p)
        result.append({**task, "pr_candidates": prs, "accepted": False,
            "acceptance_state": "NOT_VERIFIED",
            "note": "PR/CI observations are candidate evidence; never auto-promote completion"})
    counts = {k: sum(x["baseline"] == k for x in result) for k in ("done", "partial", "todo")}
    score = round(100 * (counts["done"] + .5 * counts["partial"]) / len(result), 1)
    return {"generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": MASTER, "repository": REPO, "counts": counts,
        "baseline_progress_percent": score, "strict_accepted_count": 0,
        "strict_acceptance_note": "0 verified in this audit; not proof that all tasks are unaccepted",
        "google_sheet_probe": sheet, "tasks": result}

def markdown(obj):
    x = obj
    lines = ["# Automation Progress Audit", "",
        "Generated UTC: " + x["generated_at_utc"], "",
        "Historical weighted baseline: **" + str(x["baseline_progress_percent"]) + "%**; "
        "done=" + str(x["counts"]["done"]) + ", partial=" + str(x["counts"]["partial"]) +
        ", todo=" + str(x["counts"]["todo"]) + ".", "",
        "Strict operational completion is **NOT MEASURED**. GitHub green runs and PRs are not automatic acceptance.", "",
        "Google Sheets metadata: " + x["google_sheet_probe"]["state"], "",
        "| ID | Task | Baseline | PR evidence candidates | Acceptance |", "|---|---|---|---|---|"]
    for t in x["tasks"]:
        urls = ", ".join("[#" + str(p["number"]) + "](" + p["url"] + ")" for p in t["pr_candidates"]) or "-"
        lines.append("| " + t["id"] + " | " + t["task"] + " | " + t["baseline"] + " | " + urls +
                     " | " + t["acceptance_state"] + " |")
    lines += ["", "No production or manual-decision writes were performed."]
    return "\n".join(lines) + "\n"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--master", default=MASTER)
    p.add_argument("--out-dir", default="progress-audit")
    p.add_argument("--offline", action="store_true")
    args = p.parse_args()
    master = Path(args.master).read_text(encoding="utf-8")
    github_error = None
    if args.offline:
        prs, runs = {}, {}
        sheet = {"state": "NOT_CHECKED", "reason": "offline"}
    else:
        try:
            prs, runs = github(os.environ.get("GITHUB_TOKEN"))
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
            prs, runs = {}, {}
            github_error = type(exc).__name__
        sheet = sheet_probe()
    output = build(master, prs, runs, sheet)
    if github_error:
        output["github_error_type"] = github_error
    folder = Path(args.out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "report.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "report.md").write_text(markdown(output), encoding="utf-8")
    print("AUDIT_OK", output["counts"], "weighted=", output["baseline_progress_percent"],
          "github_ok=", github_error is None, "sheets=", sheet["state"])
    if github_error and not args.offline:
        sys.exit(2)

if __name__ == "__main__":
    main()
