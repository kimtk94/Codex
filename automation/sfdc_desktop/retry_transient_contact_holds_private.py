#!/usr/bin/env python3
"""One-shot retry of transient Salesforce UI HOLDs for Contact verification.

Does not relax Contact name, email, Account, Opportunity, or exclusion rules.
Rechecks every selected record in authenticated Chrome and promotes only
independent PASS_ALL_IDENTITY_CHECKS. PII never leaves the private workstation.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from playwright.sync_api import sync_playwright
from expand_korean_contacts_private import (
    ROOT, EVIDENCE, ATTEMPTS, WEB_ALIASES,
    MANIFEST, HISTORICAL, CONTACTS, load_private, atomic_private_write,
    expand_candidates,
)
from build_private_contact_aliases import verified_private_aliases
import live_contact_alias_batch_private as study

TRANSIENT_REASONS=frozenset({"HOLD_TimeoutError","HOLD_ConnectionError","HOLD_TargetClosedError"})


def select_transient_holds(candidates, approved, attempts, limit=4):
    if not isinstance(candidates,list) or not isinstance(approved,list) or not isinstance(attempts,list):
        raise ValueError("INVALID_PRIVATE_HOLD_SOURCES")
    if not 1<=limit<=8:
        raise ValueError("INVALID_RETRY_LIMIT")
    latest={}
    for item in attempts:
        if isinstance(item,dict) and isinstance(item.get("contact_id"),str):
            latest[item["contact_id"]]=item.get("status")
    accepted={r.get("contact_id") for r in approved if isinstance(r,dict)}
    return [r for r in candidates
            if r["contact_id"] not in accepted
            and latest.get(r["contact_id"]) in TRANSIENT_REASONS][:limit]


def run(limit=4):
    manifest=load_private(MANIFEST)
    historical=load_private(HISTORICAL)
    contacts=load_private(CONTACTS)["rows"]
    approved=load_private(EVIDENCE)
    attempts=load_private(ATTEMPTS) if (ROOT/ATTEMPTS).exists() else []
    candidates=expand_candidates(manifest,historical,contacts)
    todo=select_transient_holds(candidates,approved,attempts,limit)
    counts=Counter()
    if todo:
        with sync_playwright() as pw:
            browser=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=16000)
            if len(browser.contexts)!=1:
                raise ValueError("HOLD_UNIQUE_CHROME_CONTEXT_REQUIRED")
            page=browser.contexts[0].new_page()
            try:
                for idx,item in enumerate(todo,1):
                    try:
                        identity,status=study.inspect(page,item)
                    except Exception as exc:
                        identity,status=None,"HOLD_"+type(exc).__name__
                    counts[status]+=1
                    attempts.append({"contact_id":item["contact_id"],
                                     "opportunity_id":item["opportunity_id"],
                                     "status":status,"read_only":True,
                                     "save_clicked":False,"retry_type":"TRANSIENT_ONLY"})
                    atomic_private_write(ATTEMPTS,attempts)
                    if status=="PASS_ALL_IDENTITY_CHECKS" and identity:
                        approved.append(identity)
                        atomic_private_write(EVIDENCE,approved)
                    print("HOLD_RETRY",idx,"/",len(todo),"STATUS",status,flush=True)
            finally:page.close()
    aliases=verified_private_aliases(approved)
    atomic_private_write(WEB_ALIASES,aliases["records"])
    report={"transient_holds_retested":len(todo),
            "new_pass":counts["PASS_ALL_IDENTITY_CHECKS"],
            "remaining_in_batch":len(todo)-counts["PASS_ALL_IDENTITY_CHECKS"],
            "total_approved":len(aliases["records"]),
            "save_allowed":False,"salesforce_writes":0}
    print("TRANSIENT_HOLD_SUMMARY",json.dumps(report,sort_keys=True),flush=True)
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--limit",type=int,default=4)
    args=p.parse_args()
    run(args.limit)


if __name__=="__main__":
    main()
