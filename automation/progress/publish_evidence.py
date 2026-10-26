"""Conservatively publish *only* evidence cells F,H,J of existing progress sheet.

No baseline status, acceptance, owner, blocker, decisions, or business cells are written.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path

from tracker import build, github, sheet_probe, MASTER, SHEET_ID

TAB = "Automation Master Progress"
EXPECTED_IDS = ["A%02d" % n for n in range(1, 51)]
COLUMNS = ["F", "H", "J"]  # Evidence URL, Last Checked KST, CI Run

def payload(report, ids, checked_at):
    if ids != EXPECTED_IDS or len(report["tasks"]) != 50:
        raise ValueError("Sheet task sequence differs from canonical 50-task manifest; abort")
    if [t["id"] for t in report["tasks"]] != EXPECTED_IDS:
        raise ValueError("Source ledger order changed; abort")
    writes = []
    for index, task in enumerate(report["tasks"], start=6):
        prs = task["pr_candidates"]
        evidence = " | ".join(p["url"] for p in prs if p.get("url"))
        runs = [r["url"] for p in prs for r in p.get("recent_runs", []) if r.get("url")]
        # Missing candidate evidence must not erase an existing manually reviewed value.
        if evidence:
            writes.append((f"F{index}", evidence))
        if runs:
            writes.append((f"J{index}", " | ".join(dict.fromkeys(runs))))
        if evidence or runs:
            writes.append((f"H{index}", checked_at))
    return writes

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--out", default="progress-audit/publisher-preview.json")
    args = p.parse_args()
    if args.apply and os.environ.get("PROGRESS_SHEET_APPLY") != "true":
        raise RuntimeError("PROGRESS_SHEET_APPLY=true required")
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    raw = os.environ.get("CKD_DRIVE_SA_JSON") or os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError("Google credentials unavailable")
    creds = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    session = AuthorizedSession(creds)
    base = "https://sheets.googleapis.com/v4/spreadsheets/" + SHEET_ID
    meta = session.get(base, params={"fields": "sheets(properties(sheetId,title))"}, timeout=25)
    meta.raise_for_status()
    names = [s["properties"]["title"] for s in meta.json()["sheets"]]
    if names.count(TAB) != 1:
        raise RuntimeError("Missing or duplicate destination tab")
    existing = session.get(base + "/values/" + TAB.replace(" ", "%20") + "!A6:A55", timeout=25)
    existing.raise_for_status()
    ids = [r[0] if r else "" for r in existing.json().get("values", [])]
    master = Path(MASTER).read_text(encoding="utf-8")
    manifest = json.loads(Path("automation/progress/acceptance_manifest.json").read_text(encoding="utf-8"))
    prs, runs = github(os.environ.get("GITHUB_TOKEN"))
    report = build(master, prs, runs, sheet_probe(), manifest)
    stamp = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S KST")
    edits = payload(report, ids, stamp)
    preview = {"state": "DRY_RUN", "task_count": len(report["tasks"]),
        "candidate_cell_updates": len(edits), "allowed_columns": COLUMNS,
        "target": TAB, "checked_at": stamp}
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(preview, indent=2), encoding="utf-8")
    if not args.apply:
        print(json.dumps(preview))
        return
    # Last second guard: verify IDs remain in the same order.
    verify = session.get(base + "/values/" + TAB.replace(" ", "%20") + "!A6:A55", timeout=25)
    verify.raise_for_status()
    if [r[0] if r else "" for r in verify.json().get("values", [])] != ids:
        raise RuntimeError("Concurrent reorder detected; no writes")
    body = {"valueInputOption": "RAW", "data": [
        {"range": "'" + TAB + "'!" + cell, "values": [[value]]}
        for cell, value in edits]}
    if edits:
        response = session.post(base + "/values:batchUpdate", json=body, timeout=35)
        response.raise_for_status()
    preview["state"] = "APPLIED"
    dest.write_text(json.dumps(preview, indent=2), encoding="utf-8")
    print("Published", len(edits), "evidence-only cells")

if __name__ == "__main__":
    main()
