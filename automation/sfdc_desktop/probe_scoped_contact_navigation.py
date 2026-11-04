#!/usr/bin/env python3
"""Read-only test: navigate exact labelled Opportunity Contact and Account fields.

Uses an authenticated private opportunity sample, never prints names/IDs/URLs.
Clicking field values only opens existing records, not edit or save controls.
"""
import json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from inspect_oppo_contact_scoped_fields import choose,detail_tab

HOST="novogene.lightning.force.com"


def field_value(page,label,expected=None):
    labels=page.get_by_text(label,exact=True)
    hosts=[]
    for i in range(min(labels.count(),5)):
        h=labels.nth(i).locator("xpath=ancestor::record_flexipage-record-field")
        if h.count()==1:
            hosts.append(h)
    if len(hosts)!=1:
        return {"status":"HOLD_FIELD_HOST_AMBIGUOUS","host_count":len(hosts)},None
    host=hosts[0]
    text=host.inner_text(timeout=4000)
    lines=[x.strip() for x in text.splitlines() if x.strip()]
    value=lines[1] if len(lines)>=2 and lines[0].casefold()==label.casefold() else None
    if expected is not None and value!=expected:
        return {"status":"HOLD_FIELD_VALUE_MISMATCH","line_count":len(lines)},None
    if not value:
        return {"status":"HOLD_FIELD_VALUE_MISSING","line_count":len(lines)},None
    candidate=host.get_by_text(value,exact=True)
    return {"status":"FIELD_FOUND","line_count":len(lines),
            "value_locator_count":candidate.count(),
            "expected_match":expected is None or value==expected},candidate


def follow(page,obj,identifier,field,label,expected=None):
    url="https://"+HOST+"/lightning/r/"+obj+"/"+identifier+"/view"
    page.goto(url,wait_until="domcontentloaded",timeout=34000)
    if not page.url.startswith(url):
        return {"status":"HOLD_BASE_RECORD_ROUTE"},None
    detail_tab(page)
    before=set(id(x) for x in page.context.pages)
    info,loc=field_value(page,label,expected)
    if loc is None or info["value_locator_count"]!=1:
        return info,None
    try:
        loc.click(timeout=7000)
        page.wait_for_timeout(900)
    except Exception as exc:
        return {**info,"status":"HOLD_CLICK_"+type(exc).__name__},None
    current=urlsplit(page.url).path
    # Salesforce may switch the browser console tab in-place or open a window.
    if "/lightning/r/" in current and current!=urlsplit(url).path:
        return {**info,"status":"NAVIGATED","object_route":current.split("/")[3]},current
    return {**info,"status":"HOLD_NO_ROUTE_CHANGE"},None


def main():
    opportunity,contact_id,display=choose()
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=15000)
        if len(browser.contexts)!=1:
            raise SystemExit("HOLD_CONTEXT_COUNT")
        page=browser.contexts[0].new_page()
        try:
            contact,route1=follow(page,"Opportunity",opportunity,"Main Contact","Main Contact",display)
            account_from_opp,route2=follow(page,"Opportunity",opportunity,"Account Name","Account Name")
            account_from_contact,route3=follow(page,"Contact",contact_id,"Account Name","Account Name")
            inventory=json.loads((Path.home()/".sfdc_desktop"/"full_contact_with_names_PRIVATE.json").read_text(encoding="utf-8-sig"))["rows"]
            listed=[x for x in inventory if x.get("id")==contact_id]
            list_names={x.get("name") for x in listed if x.get("name")}
            list_emails={v.strip() for x in listed for v in x.get("cells",[]) if "@" in v and len(v)<255}
            details_url="https://"+HOST+"/lightning/r/Contact/"+contact_id+"/view"
            page.goto(details_url,wait_until="domcontentloaded",timeout=34000)
            detail_tab(page)
            detail_name_exact_count=page.get_by_text(display,exact=True).count()
            check_email=sorted(list_emails)[0] if len(list_emails)==1 else None
            email_info,_=field_value(page,"Email",check_email) if check_email else ({"status":"HOLD_LIST_EMAIL_AMBIGUOUS"},None)
            report={"contact":contact,"contact_id_matches_expected":bool(route1 and contact_id in route1),
                    "opportunity_account":account_from_opp,
                    "contact_account":account_from_contact,
                    "account_route_same":bool(route2 and route3 and route2==route3),
                    "contact_list_name_same":list_names=={display},
                    "contact_details_name_visible":detail_name_exact_count>0,
                    "email_field":email_info,
                    "save_clicked":False}
            print(json.dumps(report,ensure_ascii=True))
        finally:
            page.close()


if __name__=="__main__":
    main()
