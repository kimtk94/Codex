#!/usr/bin/env python3
"""Expand vetted Korean Contact aliases beyond the historical 180-Opportunity sample.

Only exact roster candidates are proposed; every new Contact must independently
pass live, authenticated, read-only Opportunity -> Contact -> Account and email
verification. All records stay under ~/.sfdc_desktop on the authorized PC.
Never creates, edits, or saves Salesforce objects.
"""
import argparse
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from playwright.sync_api import sync_playwright
import live_contact_alias_batch_private as study
from build_private_contact_aliases import korean_name_from_contact_label, verified_private_aliases
from contact_oppo_selection import ID_CONTACT, ID_OPPORTUNITY

ROOT = Path.home() / ".sfdc_desktop"
MANIFEST = "oppo_linked_contact_candidate_manifest_PRIVATE.json"
HISTORICAL = "oppo_main_contact_identity_batch180_PRIVATE.json"
CONTACTS = "full_contact_with_names_PRIVATE.json"
EVIDENCE = "private_verified_contact_details_evidence.json"
ATTEMPTS = "expanded_contact_alias_attempts_PRIVATE.json"
WEB_ALIASES = "web_contact_aliases_PRIVATE.json"


def load_private(filename):
    return json.loads((ROOT / filename).read_text(encoding="utf-8-sig"))


def atomic_private_write(filename, payload):
    path = ROOT / filename
    pending = path.with_name(path.name + ".writing")
    pending.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(pending, path)


def expand_candidates(manifest, historical, registry):
    """Return one eligible existing Opportunity per independently identified Contact.

    Display-name and list membership are candidate evidence only, NOT live proof.
    Inconsistent source rows and ambiguous registry email are excluded.
    """
    if not all(isinstance(x, list) for x in (manifest, historical, registry)):
        raise ValueError("INVALID_SNAPSHOT_SHAPE")
    historical_opps = {x.get("opportunity_id") for x in historical if isinstance(x, dict)}
    roster = defaultdict(list)
    for r in registry:
        if isinstance(r, dict) and isinstance(r.get("id"), str):
            roster[r["id"]].append(r)
    proposed = defaultdict(list)
    for entry in manifest:
        if not isinstance(entry, dict):
            continue
        opp = entry.get("opportunity_id")
        if not isinstance(opp, str) or not ID_OPPORTUNITY.fullmatch(opp) or opp in historical_opps:
            continue
        if entry.get("status") != "UNIQUE_DISPLAY_NAME_PENDING_REAL_LINK":
            continue
        label = entry.get("contact_display")
        if not korean_name_from_contact_label(label):
            continue
        match_ids = entry.get("candidate_contact_ids")
        if not isinstance(match_ids, list) or len(match_ids) != 1:
            continue
        cid = match_ids[0]
        if not isinstance(cid, str) or not ID_CONTACT.fullmatch(cid):
            continue
        source_rows = roster.get(cid, [])
        names = {x.get("name") for x in source_rows if isinstance(x.get("name"), str)}
        emails = {v.strip() for x in source_rows
                  for v in x.get("cells", [])
                  if isinstance(v, str) and "@" in v and 0 < len(v) <= 255}
        if names != {label} or len(emails) != 1:
            continue
        proposed[cid].append({
            "contact_id": cid, "opportunity_id": opp,
            "display_name": label, "contact_email": next(iter(emails)),
        })
    candidates = []
    for cid, rows in proposed.items():
        identities = {(r["display_name"], r["contact_email"]) for r in rows}
        if len(identities) != 1:
            continue
        # Verify only one existing Opportunity per Contact; do not falsely
        # assert that other Opportunity rows have been live independently checked.
        candidates.append(sorted(rows, key=lambda x:x["opportunity_id"])[0])
    return sorted(candidates, key=lambda x:(x["display_name"],x["contact_id"]))


def select_unverified(candidates, evidence, attempts, offset=0, limit=8, retry_holds=False):
    if not 0 <= offset <= len(candidates) or not 1 <= limit <= 20:
        raise ValueError("INVALID_SELECTION_RANGE")
    approved={x.get("contact_id") for x in evidence if isinstance(x,dict)}
    reviewed={x.get("contact_id") for x in attempts if isinstance(x,dict)}
    return [row for row in candidates[offset:]
            if row["contact_id"] not in approved
            and (retry_holds or row["contact_id"] not in reviewed)][:limit]


def run(limit=8, offset=0, retry_holds=False, dry_run=False):
    manifest=load_private(MANIFEST)
    history=load_private(HISTORICAL)
    registry=load_private(CONTACTS)["rows"]
    approved=load_private(EVIDENCE)
    attempts=load_private(ATTEMPTS) if (ROOT/ATTEMPTS).exists() else []
    if not isinstance(approved,list) or not isinstance(attempts,list):
        raise ValueError("INVALID_PRIVATE_EVIDENCE")
    candidates=expand_candidates(manifest,history,registry)
    todo=select_unverified(candidates,approved,attempts,offset,limit,retry_holds)
    stats=Counter()
    if not dry_run and todo:
        with sync_playwright() as pw:
            browser=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=16000)
            if len(browser.contexts)!=1:
                raise ValueError("HOLD_UNIQUE_AUTHENTICATED_CHROME_CONTEXT_REQUIRED")
            page=browser.contexts[0].new_page()
            try:
                for idx,row in enumerate(todo,1):
                    try:
                        verified,status=study.inspect(page,row)
                    except Exception as exc:
                        verified,status=None,"HOLD_"+type(exc).__name__
                    stats[status]+=1
                    attempts.append({"contact_id":row["contact_id"],
                                     "opportunity_id":row["opportunity_id"],
                                     "status":status,"read_only":True,
                                     "save_clicked":False})
                    atomic_private_write(ATTEMPTS,attempts)
                    if status=="PASS_ALL_IDENTITY_CHECKS" and verified is not None:
                        approved.append(verified)
                        atomic_private_write(EVIDENCE,approved)
                    print("EXPANDED_CONTACT",idx,"/",len(todo),"STATUS",status,flush=True)
            finally:
                page.close()
    aliases=verified_private_aliases(approved)
    if not dry_run:
        atomic_private_write(WEB_ALIASES,aliases["records"])
    report={
        "candidate_contacts":len(candidates),
        "reviewed_in_batch":0 if dry_run else len(todo),
        "selected_for_batch":len(todo),
        "new_pass":stats["PASS_ALL_IDENTITY_CHECKS"],
        "new_holds":sum(v for k,v in stats.items() if k!="PASS_ALL_IDENTITY_CHECKS"),
        "total_approved_contacts":len(aliases["records"]),
        "schema_conflicts":aliases["conflicting_identity_keys"],
        "salesforce_writes":0,
        "dry_run":dry_run,
        "status_counts":dict(stats),
    }
    print("EXPANDED_CONTACT_SUMMARY",json.dumps(report,sort_keys=True),flush=True)
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--limit",type=int,default=8)
    p.add_argument("--offset",type=int,default=0)
    p.add_argument("--retry-holds",action="store_true")
    p.add_argument("--dry-run",action="store_true")
    args=p.parse_args()
    run(args.limit,args.offset,args.retry_holds,args.dry_run)


if __name__=="__main__":
    main()
