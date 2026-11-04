#!/usr/bin/env python3
"""Identify pricing field presence in an existing PE250 Quote wizard; no Save."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from audit_existing_quote_product2_link_readonly import ROOT, HOST, unique_record_links

TERMS=("unit price","list price","sales price","price","currency","discount",
       "total amount","amount","quotation","data size","sample number")


def pricing_field_presence(visible_text,labels):
    source=(" ".join(labels)+" "+visible_text).casefold()
    return {key:key in source for key in TERMS}


def run():
    ref=json.loads((ROOT/"quote_source_line_inspect_20261103_PRIVATE.json").read_text(encoding="utf-8-sig"))
    ids=unique_record_links(ref.get("links"))
    if not ids or ref.get("save_clicked") is not False:
        raise SystemExit("HOLD_QUOTE_SOURCE_INVALID")
    quote_id=ids["Quotation__c"]
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=15000)
        if len(browser.contexts)!=1:
            raise SystemExit("HOLD_CHROME_CONTEXT_AMBIGUOUS")
        page=browser.contexts[0].new_page()
        result={"status":"HOLD","crm_writes":0,"save_clicked":False,
                "current_price_verified":False,"pricebook_entry_verified":False}
        try:
            result["last_completed_stage"]="PRE_NAVIGATION"
            url="https://"+HOST+"/lightning/r/Quotation__c/"+quote_id+"/view"
            page.goto(url,wait_until="domcontentloaded",timeout=30000)
            if quote_id not in page.url:raise ValueError("QUOTE_ROUTE_MISMATCH")
            result["last_completed_stage"]="QUOTE_ROUTE"
            page.get_by_role("tab",name="Quotation Detail",exact=True).click(timeout=8500)
            result["last_completed_stage"]="QUOTATION_DETAIL_TAB"
            page.get_by_text("Add/Edit",exact=True).click(timeout=8500)
            result["last_completed_stage"]="ADD_EDIT_MODAL"
            page.get_by_text("AMEA Pre-made libraries sequencing",exact=True).first.click(timeout=8500)
            result["last_completed_stage"]="SERVICE_CATEGORY"
            item=page.get_by_text("Pre-made libraries partial lane sequencing (PE250)",exact=True)
            if item.count()!=1:raise ValueError("EXISTING_PRODUCT_NOT_UNIQUE")
            result["last_completed_stage"]="UNIQUE_PE250_EXISTING_PRODUCT"
            plus=item.locator("xpath=..").locator("button")
            if plus.count()!=1:raise ValueError("PRODUCT_ADD_CONTROL_NOT_UNIQUE")
            plus.click(timeout=6500)
            result["last_completed_stage"]="EXISTING_PRODUCT_DRAFT_MODAL"
            modal=page.get_by_role("dialog").last
            sample=modal.get_by_label("Sample Number",exact=True)
            size=modal.get_by_label("Data Size",exact=True)
            if sample.count()!=1 or size.count()!=1:
                raise ValueError("SAMPLE_DATA_FIELDS_NOT_UNIQUE")
            sample.fill("5")
            size.fill("1")
            if sample.input_value()!="5" or size.input_value()!="1":
                raise ValueError("DRAFT_FIELDS_MISMATCH")
            result["last_completed_stage"]="QUANTITY_DEPTH_SET_UNSAVED"
            modal.get_by_role("button",name="Next",exact=True).click(timeout=6500)
            result["last_completed_stage"]="NEXT_PROCESS_WIZARD"
            page.wait_for_timeout(1000)
            dialog=page.get_by_role("dialog").last
            text=dialog.inner_text(timeout=5500)
            labels=dialog.locator("label").all_text_contents()
            result.update({"status":"UNSAVED_EXISTING_PE250_WIZARD_INSPECTED",
                           "product_option_unique":True,
                           "quantity_and_depth_draft_verified":True,
                           "pricing_labels_present":pricing_field_presence(text,labels),
                           "field_label_count":len(labels)})
        except Exception as exc:
            result["status"]="HOLD_"+type(exc).__name__
        finally:
            page.close()
        (ROOT/"pe250_unsaved_current_price_fields_PRIVATE.json").write_text(
            json.dumps(result,indent=2),encoding="utf-8")
        print("PE250_WIZARD_PRICE_FIELDS",json.dumps(result,sort_keys=True))


if __name__=="__main__":
    run()
