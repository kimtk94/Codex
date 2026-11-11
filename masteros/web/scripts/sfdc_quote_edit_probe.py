"""Read-only SFDC source Quote editable-control probe.

No Save/New/Pack/UnPack clicks. The existing source Quote Add/Edit panel is
used to verify column-specific editable inputs and is always Cancelled before
a fresh, independent source Quote readback. No customer or price is inferred.
"""
import math
import re
from sfdc_record_catalog import (
    BASE, parse_modal_process_price_rows, _source_modal_money, read_item
)

def audit_controls_snapshot(source_lines, observed, header, flags):
    """Pure strict check for existing source Pack/unit price/Cloud fields."""
    if not isinstance(source_lines,list) or not source_lines or not isinstance(observed,list):
        raise ValueError("SOURCE_PROCESS_LINES_UNVERIFIED")
    if header!=["","","Pack No.","Process Name","Process Type","Sample Number",
               "Data Size","Data Unit","Unit Price","Standard Price","Note","",""]:
        raise ValueError("SOURCE_MODAL_HEADER_UNEXPECTED")
    if len(source_lines)!=len(observed) or len(source_lines)>25:
        raise ValueError("SOURCE_PROCESS_COUNT_MISMATCH")
    if flags.get("pack_button")!=1 or flags.get("unpack_button")!=1 or flags.get("cancel_button")!=1:
        raise ValueError("SOURCE_PACK_OR_CANCEL_CONTROLS_NOT_UNIQUE")
    actual={}
    for row in observed:
        if not isinstance(row,dict):raise ValueError("SOURCE_EDIT_ROW_INVALID")
        key=(row.get("packNo"),row.get("processType"),row.get("processName"))
        if key in actual or not all(isinstance(k,str) for k in key):
            raise ValueError("SOURCE_EDIT_PROCESS_IDENTITY_AMBIGUOUS")
        actual[key]=row
    controls=[]
    cloud_count=0
    for source in source_lines:
        key=(source.get("packNo"),source.get("processType"),source.get("processName"))
        item=actual.get(key)
        if item is None:
            raise ValueError("SOURCE_EDIT_PROCESS_NOT_FOUND")
        is_cloud=source.get("isCloud") is True
        if is_cloud:cloud_count+=1
        if item.get("isCloud") is not is_cloud or item.get("qty")!=source.get("sourceQty"):
            raise ValueError("SOURCE_EDIT_QTY_OR_CLOUD_MISMATCH")
        if item.get("unitPriceKrw")!=source.get("unitPriceKrw"):
            raise ValueError("SOURCE_EDIT_UNIT_RATE_MISMATCH")
        if item.get("price_input_count")!=1 or item.get("price_editable") is not True:
            raise ValueError("SOURCE_PRICE_FIELD_NOT_EDITABLE")
        if item.get("qty_input_count")!=1 or item.get("qty_editable") is not is_cloud:
            raise ValueError("SOURCE_CLOUD_OR_SAMPLE_QTY_CONTROL_INVALID")
        controls.append({"packNo":source.get("packNo",""),
            "processName":source["processName"],"sourceQty":source["sourceQty"],
            "unitPriceKrw":source["unitPriceKrw"],"isCloud":is_cloud,
            "source_unit_price_editable":True,
            "source_qty_editable":is_cloud})
    if cloud_count!=1:raise ValueError("SOURCE_CLOUD_NOT_UNIQUE")
    return {"status":"PASS","code":"SOURCE_QUOTE_INPUT_CONTROLS_VERIFIED",
        "checks":{"source_price_matrix":"PASS","source_unit_price_controls":"PASS",
                  "source_cloud_qty_control":"PASS","source_pack_controls":"PRESENT",
                  "source_cancel":"PENDING","source_original_unchanged":"PENDING"},
        "processes":controls,
        "new_quote_product_wizard":"NOT_TESTED",
        "new_quote_process_writer":"NOT_VERIFIED",
        "salesforce_write":False,"save_permitted":False}


def probe_source_edit_controls(page, quote_id, expected_pack, samples, gb):
    if not re.fullmatch(r"a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?",str(quote_id)):
        raise ValueError("SOURCE_QUOTE_ID_INVALID")
    if not isinstance(expected_pack,dict) or expected_pack.get("state")!="PASS":
        raise ValueError("SOURCE_PACK_UNVERIFIED")
    lines=expected_pack.get("process_lines")
    if not isinstance(lines,list) or len(lines)<2:
        raise ValueError("SOURCE_PROCESS_LINES_UNVERIFIED")
    original_samples={row.get("sourceQty") for row in lines if not row.get("isCloud")}
    if len(original_samples)!=1:
        raise ValueError("SOURCE_SAMPLES_CONFLICT")
    original_samples=next(iter(original_samples))
    if not isinstance(original_samples,int) or original_samples<=0 or not isinstance(gb,(int,float)) or not math.isfinite(gb) or gb<=0:
        raise ValueError("SOURCE_SIZE_UNVERIFIED")
    source_net=sum(x["sourceQty"]*x["unitPriceKrw"] for x in lines)
    url=BASE+"/lightning/r/Quotation__c/"+quote_id+"/view"
    cancelled=False
    evidence=None
    page.goto(url,wait_until="domcontentloaded",timeout=28000)
    try:
        from playwright.sync_api import TimeoutError as PwTimeout
        for attempt in range(3):
            page.get_by_role("tab",name="Quotation Detail",exact=True).click(timeout=12000)
            page.wait_for_timeout(900)
            button=page.get_by_text("Add/Edit",exact=True)
            if button.count()!=1:
                raise ValueError("SOURCE_ADD_EDIT_AMBIGUOUS")
            try:
                button.click(timeout=12500)
                dialog=page.get_by_role("dialog").last
                dialog.wait_for(state="visible",timeout=15000)
                break
            except PwTimeout:
                if attempt==2:
                    raise ValueError("SOURCE_EDIT_MODAL_OPEN_TIMEOUT")
                # Salesforce sometimes rerenders the button over a modal/backdrop.
                # Safe retry is navigation/reload only, never a Save/Pack click.
                page.goto(url,wait_until="domcontentloaded",timeout=28000)
        table=dialog.locator("table").filter(has_text="Pack No.").filter(has_text="Unit Price")
        table.first.wait_for(state="visible",timeout=18000)
        for _ in range(50):
            if table.locator("tr").count()>1 and table.locator("tr").nth(1).locator('input[type="text"]').count()==3:break
            page.wait_for_timeout(300)
        else:raise ValueError("SOURCE_MODAL_ROWS_UNAVAILABLE")
        cells=table.evaluate("""node=>[...node.querySelectorAll('tr')].map(tr=>
           [...tr.querySelectorAll('th,td')].map(c=>({
             text:(c.innerText||'').trim().replace(/\\s+/g,' '),
             value:c.querySelector('input[type=text]')?.value??null
           })))""")
        summary=dialog.locator("table").filter(has_text="Sales Price").filter(has_text="List Price")
        if summary.count()!=1:raise ValueError("SOURCE_SUMMARY_AMBIGUOUS")
        summary_rows=summary.evaluate("""node=>[...node.querySelectorAll('tr')].map(tr=>
           [...tr.querySelectorAll('th,td')].map(c=>(c.innerText||'').trim().replace(/\\s+/g,' ')))""")
        if len(summary_rows)!=2 or summary_rows[0]!=["Total","Sales Price","List Price"]:
            raise ValueError("SOURCE_SUMMARY_CHANGED")
        parsed=parse_modal_process_price_rows({
            "headers":[c["text"] for c in cells[0]],
            "rows":cells[1:],"total":summary_rows[1][0]},
            original_samples,gb,source_net)
        observed=[]
        rowloc=table.locator("tr")
        for i,original in enumerate(parsed["processPriceLines"],start=1):
            row=rowloc.nth(i)
            price=row.locator("th,td").nth(8).locator('input[type="text"]')
            qty=row.locator("th,td").nth(5).locator('input[type="text"]')
            observed.append({
              "packNo":original["packNo"],"processType":original["processType"],
              "processName":original["processName"],"isCloud":original["isCloud"],
              "unitPriceKrw":original["unitPriceKrw"],"qty":original["sourceQty"],
              "price_input_count":price.count(),
              "price_editable":price.is_enabled() if price.count()==1 else False,
              "qty_input_count":qty.count(),
              "qty_editable":qty.is_enabled() if qty.count()==1 else False})
        flags={"pack_button":dialog.get_by_text("Pack",exact=True).count(),
               "unpack_button":dialog.get_by_text("UnPack",exact=True).count(),
               "cancel_button":dialog.get_by_role("button",name="Cancel",exact=True).count()}
        evidence=audit_controls_snapshot(lines,observed,[c["text"] for c in cells[0]],flags)
        # Lightning numeric input's fill() can APPEND instead of clearing:
        # '160,000.00' -> '160,000,160,000.00' and Cloud '1.00' -> '11.00'.
        # Explicit select-all/delete/type/Tab, then compare numeric values.
        # Never Save; Cancel + fresh live readback must still pass.
        first_noncloud=next(i for i,x in enumerate(parsed["processPriceLines"],start=1) if not x["isCloud"])
        cloud=next(i for i,x in enumerate(parsed["processPriceLines"],start=1) if x["isCloud"])
        for row_idx,col in ((first_noncloud,8),(cloud,5)):
            control=rowloc.nth(row_idx).locator("th,td").nth(col).locator('input[type="text"]')
            before=_source_modal_money(control.input_value())
            control.click(timeout=6000)
            control.press("ControlOrMeta+A")
            control.press("Backspace")
            control.type(str(before),delay=25)
            control.press("Tab")
            if _source_modal_money(control.input_value())!=before:
                raise ValueError("SOURCE_NOOP_EDIT_READBACK_MISMATCH")
        cancel=dialog.get_by_role("button",name="Cancel",exact=True)
        cancel.click(timeout=8000)
        dialog.wait_for(state="hidden",timeout=13500)
        cancelled=True
        evidence["checks"]["source_cancel"]="PASS"
    finally:
        # Exit unsaved source dialog even if a price field or load check fails.
        if not cancelled:
            try:page.goto(url,wait_until="domcontentloaded",timeout=28000)
            except Exception:pass
    # Independently fetch original Quote from Salesforce after Cancel.
    independent=read_item(page,"quote",quote_id)
    if independent.get("pricingStatus")!="VERIFIED_PROCESS_LINES" or independent.get("totalPriceKrw")!=source_net:
        raise ValueError("SOURCE_CANCEL_READBACK_MISMATCH")
    original_by_key={(x["packNo"],x["processType"],x["processName"]):
                      (x["sourceQty"],x["unitPriceKrw"])
                     for x in parsed["processPriceLines"]}
    readback_by_key={(x["packNo"],x["processType"],x["processName"]):
                      (x["sourceQty"],x["unitPriceKrw"])
                    for x in independent.get("processPriceLines",[])}
    if original_by_key!=readback_by_key:
        raise ValueError("SOURCE_PRICE_CHANGED_AFTER_CANCEL")
    evidence["checks"]["source_original_unchanged"]="PASS"
    evidence["code"]="SOURCE_EDIT_CONTROLS_DRY_RUN_AND_CANCEL_VERIFIED"
    return evidence
