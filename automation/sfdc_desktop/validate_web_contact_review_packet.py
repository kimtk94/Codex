#!/usr/bin/env python3
"""Validate a browser-downloaded, identity-bound Contact / Oppo review packet.

Offline mode matches only the workstation's previously independently verified
private Contact roster. --live-readonly additionally follows currently
authenticated Salesforce Contact and Account links, without editing or Save.
Never log customer identities or private packet contents.
"""
import argparse
import json
from pathlib import Path

from web_draft_intake import inspect_web_draft

ROOT=Path.home()/".sfdc_desktop"
VERSION="oppo-quote-contact-review-v1"
EXPECTED_GATE={
    "contact_identity_live_verified":False,
    "account_identity_live_verified":False,
    "opportunity_duplicate_check_complete":False,
    "quote_price_and_product_verified":False,
    "salesforce_save_allowed":False,
}
CONTACT_KEYS={"name","institution","contact_id","account_id","contact_email","opportunity_ids"}


def validate_review_packet(packet, aliases):
    if not isinstance(packet,dict) or set(packet)!={
        "version","source","status","selected_contact","draft","gate"}:
        raise ValueError("PACKET_SCHEMA_MISMATCH")
    if packet["version"]!=VERSION or packet["source"]!="authorized_private_browser_json":
        raise ValueError("PACKET_ORIGIN_INVALID")
    if packet["status"]!="HOLD_FRESH_SALESFORCE_IDENTITY_AND_PRICING":
        raise ValueError("PACKET_REVIEW_GATE_INVALID")
    if packet["gate"]!=EXPECTED_GATE:
        raise ValueError("PACKET_SAVE_OR_IDENTITY_GATE_INVALID")
    identity=packet["selected_contact"]
    if not isinstance(identity,dict) or set(identity)!=CONTACT_KEYS:
        raise ValueError("CONTACT_IDENTITY_SCHEMA_INVALID")
    if not isinstance(aliases,list):
        raise ValueError("VERIFIED_ROSTER_INVALID")
    matches=[row for row in aliases if isinstance(row,dict)
             and row.get("contact_id")==identity["contact_id"]]
    if len(matches)!=1 or matches[0]!=identity:
        raise ValueError("CONTACT_NOT_UNIQUELY_VERIFIED_IN_PRIVATE_ROSTER")
    draft=packet["draft"]
    result=inspect_web_draft(draft)
    if draft["request"]["contact_email"]!=identity["contact_email"]:
        raise ValueError("DRAFT_EMAIL_NOT_SELECTED_CONTACT")
    return {"status":"LOCAL_CONTACT_PACKET_MATCH_NO_SAVE",
            "matched_private_roster":True,"live_identity_verified":False,
            "save_allowed":False,"sample_count":result["sample_count"],
            "needs_live_duplicate_product_price_review":True}


def private_json(path,max_size):
    path=Path(path)
    if path.stat().st_size>max_size:
        raise ValueError("FILE_SIZE_EXCEEDED")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def select_live_source_record(packet, evidence):
    """Recheck the *approved* local evidence, not the obsolete 180-Opportunity cohort.

    Each source is independently verified in Salesforce before it is added to
    the private approved evidence file. Reconstructing its alias must exactly
    match the browser's bound identity; no unverifiable contact can pass.
    """
    from build_private_contact_aliases import verified_private_aliases

    if not isinstance(evidence,list) or not isinstance(packet,dict):
        return None
    identity=packet.get("selected_contact")
    if not isinstance(identity,dict):
        return None
    rows=[]
    for row in evidence:
        if not isinstance(row,dict) or row.get("contact_id")!=identity.get("contact_id"):
            continue
        try:
            verified=verified_private_aliases([row])["records"]
        except (TypeError,ValueError,KeyError):
            continue
        if verified==[identity] and row.get("opportunity_id") in identity.get("opportunity_ids",[]):
            rows.append(row)
    if len(rows)!=1:
        return None
    row=rows[0]
    return {
        "contact_id":row["contact_id"],
        "opportunity_id":row["opportunity_id"],
        "display_name":row["display_name"],
        "contact_email":row["contact_email"],
    }


def verify_live_readonly(packet):
    from playwright.sync_api import sync_playwright
    import live_contact_alias_batch_private as study

    identity=packet["selected_contact"]
    try:
        approved_source=private_json(ROOT/"private_verified_contact_details_evidence.json",5_000_000)
        record=select_live_source_record(packet,approved_source)
    except (OSError,ValueError,KeyError,TypeError):
        record=None
    if record is None:
        return {"status":"HOLD_PRIVATE_APPROVED_EVIDENCE_NOT_UNIQUE",
                "live_identity_verified":False,"save_allowed":False}
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=17000)
        if len(browser.contexts)!=1:
            return {"status":"HOLD_AUTHENTICATED_CONTEXT_NOT_UNIQUE",
                    "live_identity_verified":False,"save_allowed":False}
        page=browser.contexts[0].new_page()
        try:
            row,status=study.inspect(page,record)
        except Exception as exc:
            row,status=None,"HOLD_"+type(exc).__name__
        finally:
            page.close()
    if (status!="PASS_ALL_IDENTITY_CHECKS" or not row or
        row.get("account_id")!=identity["account_id"] or
        row.get("institution")!=identity["institution"] or
        row.get("contact_id")!=identity["contact_id"]):
        return {"status":"HOLD_FRESH_SALESFORCE_IDENTITY",
                "reason":status,"live_identity_verified":False,
                "save_allowed":False}
    return {"status":"LIVE_CONTACT_ACCOUNT_PARENT_LINK_MATCH_NO_SAVE",
            "live_identity_verified":True,"save_allowed":False,
            "price_and_product_verified":False,
            "duplicate_quote_check_complete":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--packet",required=True)
    p.add_argument("--roster",default=str(ROOT/"web_contact_aliases_PRIVATE.json"))
    p.add_argument("--live-readonly",action="store_true")
    args=p.parse_args()
    roster_path=Path(args.roster).resolve()
    if ROOT.resolve() not in roster_path.parents:
        raise SystemExit("HOLD_ROSTER_NOT_IN_PRIVATE_WORKSTATION_DIRECTORY")
    try:
        packet=private_json(args.packet,250_000)
        aliases=private_json(roster_path,2_000_000)
        result=validate_review_packet(packet,aliases)
        if args.live_readonly:
            result["live_readback"]=verify_live_readonly(packet)
        # No private names, emails, native IDs, or record URLs emitted.
        print(json.dumps(result,sort_keys=True))
    except (ValueError,TypeError,KeyError,OverflowError,json.JSONDecodeError) as exc:
        raise SystemExit("HOLD_REVIEW_PACKET_INVALID:"+type(exc).__name__)


if __name__=="__main__":
    main()
