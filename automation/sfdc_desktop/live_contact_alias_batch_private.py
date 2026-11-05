#!/usr/bin/env python3
"""Read-only private Contact/Account validation for Opportunity-linked Korean names.

Outputs customer identifiers exclusively under ~/.sfdc_desktop; prints counts
and HOLD reasons only. Never uploads, saves Salesforce records, or retries Save.
"""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
from build_private_contact_aliases import korean_name_from_contact_label, verified_private_aliases
from contact_oppo_selection import ID_CONTACT, ID_OPPORTUNITY, ID_ACCOUNT, excluded_account
from probe_scoped_contact_navigation import HOST, field_value, follow, detail_tab

ROOT=Path.home()/".sfdc_desktop"
OPPO_ROUTE=re.compile(r"^/lightning/r/Opportunity/(006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)/view$")
CONTACT_ROUTE=re.compile(r"^/lightning/r/Contact/(003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)/view$")
ACCOUNT_ROUTE=re.compile(r"^/lightning/r/Account/(001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)/view$")


def account_link_status(info, linked_path, expected_account_id):
    """Separate missing/ambiguous UI navigation from real Account ID mismatch."""
    if not isinstance(info, dict) or info.get("status") != "NAVIGATED":
        return "HOLD_CONTACT_ACCOUNT_NAVIGATION"
    match=ACCOUNT_ROUTE.fullmatch(str(linked_path))
    if not match:
        return "HOLD_CONTACT_ACCOUNT_ROUTE_INVALID"
    if not isinstance(expected_account_id,str) or not ID_ACCOUNT.fullmatch(expected_account_id):
        return "HOLD_EXPECTED_ACCOUNT_ID_INVALID"
    if match.group(1) != expected_account_id:
        return "HOLD_ACCOUNT_ID_DIFFERENT"
    return "PASS_ACCOUNT_ID"


def candidates():
    manifest={x["opportunity_id"]:x for x in json.loads(
        (ROOT/"oppo_linked_contact_candidate_manifest_PRIVATE.json").read_text(encoding="utf-8-sig"))}
    inspected=json.loads((ROOT/"oppo_main_contact_identity_batch180_PRIVATE.json").read_text(encoding="utf-8-sig"))
    registry=json.loads((ROOT/"full_contact_with_names_PRIVATE.json").read_text(encoding="utf-8-sig"))["rows"]
    by_id={}
    for r in registry:by_id.setdefault(r.get("id"),[]).append(r)
    chosen={}
    for r in inspected:
        opp=r.get("opportunity_id")
        details=manifest.get(opp)
        ids=r.get("actual_contact_ids",[])
        if (r.get("result")!="PASS_ID_AND_CANDIDATE" or not details or
            len(ids)!=1 or not ID_CONTACT.fullmatch(str(ids[0])) or
            not ID_OPPORTUNITY.fullmatch(str(opp))):
            continue
        display=details.get("contact_display") or ""
        if not korean_name_from_contact_label(display):
            continue
        contact_list=by_id.get(ids[0],[])
        names={x.get("name") for x in contact_list if x.get("name")}
        emails={v.strip() for x in contact_list for v in x.get("cells",[])
                if isinstance(v,str) and "@" in v and len(v)<255}
        if names!={display} or len(emails)!=1:
            continue
        row={"contact_id":ids[0],"opportunity_id":opp,"display_name":display,
             "contact_email":next(iter(emails))}
        prev=chosen.get(ids[0])
        if prev and (prev["display_name"]!=display or prev["contact_email"]!=row["contact_email"]):
            chosen.pop(ids[0],None)
            continue
        chosen.setdefault(ids[0],row)
    return list(chosen.values())


def inspect(page,row):
    opp=row["opportunity_id"]
    cid=row["contact_id"]
    name=row["display_name"]
    details={"contact_detail_id_verified":False,"contact_account_link_verified":False,
             "opportunity_contact_link_verified":False,"contact_email_verified":False,
             "contact_display_name_verified":False}
    a,contact_path=follow(page,"Opportunity",opp,"Main Contact","Main Contact",name)
    if a["status"]!="NAVIGATED" or not contact_path or not CONTACT_ROUTE.fullmatch(contact_path):
        return None,"HOLD_MAIN_CONTACT_NAVIGATION"
    if CONTACT_ROUTE.fullmatch(contact_path).group(1)!=cid:
        return None,"HOLD_MAIN_CONTACT_ID_DIFFERENT"
    details["opportunity_contact_link_verified"]=True

    account_source="https://"+HOST+"/lightning/r/Opportunity/"+opp+"/view"
    page.goto(account_source,wait_until="domcontentloaded",timeout=35000)
    if page.url!=account_source:return None,"HOLD_OPPO_ROUTE"
    detail_tab(page)
    acct,loc=field_value(page,"Account Name")
    if acct.get("status")!="FIELD_FOUND" or acct.get("value_locator_count")!=1:
        return None,"HOLD_OPPO_ACCOUNT_FIELD"
    institution=loc.inner_text(timeout=4500).strip()
    if excluded_account(institution) or any(x in institution.casefold() for x in
           ("kaist","한국과학기술원","hannam","한남대")):
        return None,"EXCLUDED_INSTITUTION"
    info,oppo_account_path=follow(page,"Opportunity",opp,"Account Name","Account Name")
    if info["status"]!="NAVIGATED" or not ACCOUNT_ROUTE.fullmatch(str(oppo_account_path)):
        return None,"HOLD_OPPO_ACCOUNT_ID"
    account_id=ACCOUNT_ROUTE.fullmatch(oppo_account_path).group(1)

    contact_url="https://"+HOST+"/lightning/r/Contact/"+cid+"/view"
    page.goto(contact_url,wait_until="domcontentloaded",timeout=35000)
    if page.url!=contact_url:return None,"HOLD_CONTACT_DETAIL_ROUTE"
    detail_tab(page)
    if page.get_by_text(name,exact=True).count()<1:
        return None,"HOLD_CONTACT_DETAIL_DISPLAY"
    details["contact_detail_id_verified"]=True
    details["contact_display_name_verified"]=True
    email,_=field_value(page,"Email",row["contact_email"])
    if email.get("status")!="FIELD_FOUND" or email.get("expected_match") is not True:
        return None,"HOLD_CONTACT_EMAIL_IDENTITY"
    details["contact_email_verified"]=True

    info,contact_account_path=follow(page,"Contact",cid,"Account Name","Account Name")
    account_result=account_link_status(info,contact_account_path,account_id)
    if account_result!="PASS_ACCOUNT_ID":
        return None,account_result
    details["contact_account_link_verified"]=True
    return {**row,"opportunity_ids":[opp],"account_id":account_id,"institution":institution,
            **details,"save_clicked":False},"PASS_ALL_IDENTITY_CHECKS"


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--limit",type=int,default=4)
    args=p.parse_args()
    if not 1<=args.limit<=10:p.error("pilot limit: 1..10")
    available=candidates()
    output=ROOT/"private_verified_contact_details_evidence.json"
    if output.exists():
        prior=json.loads(output.read_text(encoding="utf-8-sig"))
        if not isinstance(prior,list):raise SystemExit("HOLD_INVALID_PRIVATE_EVIDENCE")
    else:prior=[]
    existing={r.get("contact_id") for r in prior if isinstance(r,dict)}
    todo=[r for r in available if r["contact_id"] not in existing][:args.limit]
    counts={"PASS_ALL_IDENTITY_CHECKS":0}
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=16000)
        if len(browser.contexts)!=1:raise SystemExit("HOLD_AUTHENTICATED_CONTEXT_NOT_UNIQUE")
        page=browser.contexts[0].new_page()
        try:
            for i,row in enumerate(todo,1):
                try:
                    result,status=inspect(page,row)
                except Exception as exc:
                    result=None
                    status="HOLD_"+type(exc).__name__
                counts[status]=counts.get(status,0)+1
                if result:
                    prior.append(result)
                    output.write_text(json.dumps(prior,ensure_ascii=False,indent=2),encoding="utf-8")
                print("CONTACT_PILOT",i,"/",len(todo),"STATUS",status,flush=True)
        finally:page.close()
    evidence=verified_private_aliases(prior)
    target=ROOT/"web_contact_aliases_PRIVATE.json"
    target.write_text(json.dumps(evidence["records"],ensure_ascii=False,indent=2),encoding="utf-8")
    print("CONTACT_PILOT_FINAL",json.dumps({
        "candidate_contacts":len(available),"new_tests":len(todo),
        "new_pass":counts.get("PASS_ALL_IDENTITY_CHECKS",0),
        "saved_verified_aliases":len(evidence["records"]),
        "status_counts":counts,"salesforce_writes":0
    },sort_keys=True,ensure_ascii=True))


if __name__=="__main__":
    main()
