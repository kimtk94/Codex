#!/usr/bin/env python3
"""Identify pricing field presence in an existing PE250 Quote wizard; no Save."""
import json
import os
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
    source_index=os.environ.get("SFDC_EXISTING_PE250_QUOTE_SAMPLE")
    if source_index is not None:
        manifest=json.loads((ROOT/"oppo_quote_single_product_learning_manifest_PRIVATE.json").read_text(encoding="utf-8-sig"))
        eligible=[r for r in manifest if r.get("quote_status")=="Ready to send"
                  and "PE250" in ((r.get("quote_name") or "")+" "+(r.get("oppo_name") or "")).upper()
                  and r.get("save_clicked") is False]
        index=int(source_index)
        if not 0<=index<len(eligible):
            raise SystemExit("HOLD_NO_MATCHING_HISTORICAL_PE250_QUOTE")
        quote_id=eligible[index]["quote_id"]
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=15000)
        if len(browser.contexts)!=1:
            raise SystemExit("HOLD_CHROME_CONTEXT_AMBIGUOUS")
        page=browser.contexts[0].new_page()
        result={"source_mode":"HISTORICAL_PE250_QUOTE" if source_index is not None else "REFERENCE_QUOTE",
                "status":"HOLD","crm_writes":0,"save_clicked":False,
                "current_price_verified":False,"pricebook_entry_verified":False}
        try:
            result["last_completed_stage"]="PRE_NAVIGATION"
            url="https://"+HOST+"/lightning/r/Quotation__c/"+quote_id+"/view"
            page.goto(url,wait_until="domcontentloaded",timeout=30000)
            if quote_id not in page.url:raise ValueError("QUOTE_ROUTE_MISMATCH")
            result["last_completed_stage"]="QUOTE_ROUTE"
            detail_tab=page.get_by_role("tab",name="Quotation Detail",exact=True)
            detail_tab.wait_for(state="visible",timeout=18000)
            if detail_tab.count()!=1:raise ValueError("QUOTE_DETAIL_TAB_AMBIGUOUS")
            detail_tab.click(timeout=8500)
            result["last_completed_stage"]="QUOTATION_DETAIL_TAB"
            add_edit=page.get_by_role("button",name="Add/Edit",exact=True)
            add_edit.wait_for(state="visible",timeout=18000)
            if add_edit.count()!=1:raise ValueError("ADD_EDIT_AMBIGUOUS")
            if not add_edit.is_enabled():
                result["hold_reason"]="QUOTE_ADD_EDIT_DISABLED"
                raise ValueError("QUOTE_ADD_EDIT_DISABLED")
            add_edit.click(timeout=8500)
            result["last_completed_stage"]="ADD_EDIT_MODAL"
            category=page.get_by_text("AMEA Pre-made libraries sequencing",exact=True)
            result["category_match_count"]=category.count()
            if category.count()==0:
                raise ValueError("PE250_CATEGORY_MISSING_IN_QUOTE_PANEL")
            category.first.wait_for(state="visible",timeout=15000)
            category.first.click(timeout=8500)
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
