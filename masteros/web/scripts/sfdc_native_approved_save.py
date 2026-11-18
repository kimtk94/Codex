"""Real SFDC Save click, only after per-record private evidence and explicit approval.

Runs on the operator's authenticated laptop Chrome CDP. No API key and no
GitHub runner writes. The two steps are PRECHECK (no write, 3-minute nonce)
then COMMIT (exact digest + typed confirmation), each validates the private
native source evidence again and reads the real Salesforce New modal.

Every clicked Save is journaled BEFORE the click. Any ambiguous aftermath is
UNKNOWN_AFTER_CLICK; automatic retry is forbidden until manually reconciled.
"""
from __future__ import annotations
import asyncio
from decimal import Decimal, InvalidOperation
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from playwright.async_api import async_playwright
from urllib.parse import urlparse

REPO=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(REPO/"automation"/"sfdc_desktop"))
from native_save_transaction import (
    load_verified_request, read_journal, create_session, consume_session,
    exclusive_transaction, release_lock, before_click, after_click, mark_unknown,
    created_id_is_distinct, native_origin_route_violation, _gate
)

HOST="https://novogene.lightning.force.com"
OPPO_ID=re.compile(r"^006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
QUOTE_ID=re.compile(r"^a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
URL_ID={
 "OPPORTUNITY":re.compile(r"/lightning/r/(?:Opportunity/)?(006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)(?:/|$)"),
 "QUOTATION":re.compile(r"/lightning/r/(?:Quotation__c/)?(a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)(?:/|$)")
}
# Native read-only inspection. Never mutate DOM or shadow-root fields here.
JS=r"""(wanted) => {
 const normal=s=>(s||"").replace(/\s+/g," ").replace(/^\s*\*\s*/,"").trim().toLowerCase();
 const roots=[],seen=new Set(),found=[];
 function visit(root){
  if(!root||seen.has(root))return;seen.add(root);roots.push(root);
  for(const e of root.querySelectorAll("*"))if(e.shadowRoot)visit(e.shadowRoot);
 }
 visit(document);
 for(const root of roots)for(const label of root.querySelectorAll("label,.slds-form-element__label")){
   if(normal(label.textContent)!==normal(wanted))continue;
   let r=label.getRootNode();
   for(let i=0;i<12&&r&&r.host;i++){
    const host=r.host;
    if(host.matches?.("lightning-input,lightning-textarea,lightning-combobox,lightning-grouped-combobox,lightning-input-field,lightning-dual-listbox")){
      let values=[];
      const localRoot=host.shadowRoot||host;
      for(const control of localRoot.querySelectorAll("input,textarea,button,select,[role=combobox]")){
        if(control.type==="hidden")continue;
        const v=("value" in control && control.value ? String(control.value):"")||
          (control.innerText||"")||control.getAttribute("title")||"";
        if(v.trim())values.push(v.trim());
      }
      if(!values.length)values.push((host.innerText||"").trim());
      found.push(values.join(" | ").trim());break;
    }
    r=host.getRootNode();
   }
 }
 for(const root of roots)for(const host of root.querySelectorAll(
   "lightning-input,lightning-textarea,lightning-combobox,lightning-grouped-combobox,lightning-input-field")){
   if(normal(host.getAttribute("label"))!==normal(wanted))continue;
   const localRoot=host.shadowRoot||host;
   const controls=localRoot.querySelectorAll("input:not([type=hidden]),textarea,button,select,[role=combobox]");
   const values=[...controls].map(x=>(x.value||x.innerText||x.getAttribute("title")||"").trim()).filter(Boolean);
   found.push(values.join(" | "));
 }
 return [...new Set(found.filter(Boolean))];
}"""

def safe_number(value):
    try:
        if not isinstance(value,str):return None
        text=value.replace(",","").replace("KRW","").strip()
        if not re.fullmatch(r"\d{1,15}(?:\.\d{1,2})?",text):return None
        return Decimal(text)
    except InvalidOperation:return None

async def fields(page, names):
    output={}
    for name in names:
        try:
            vals=await page.evaluate(JS,name)
            # Different Lightning hosts may mirror the same exact value.
            normalized=[v.strip() for v in vals if v and v.strip()]
            output[name]=normalized[0] if len(set(normalized))==1 else None
        except Exception:
            output[name]=None
    return output

async def find_native_form(browser, stage):
    matching=[]
    for ctx in browser.contexts:
        for page in ctx.pages:
            if page.is_closed() or urlparse(page.url).hostname!="novogene.lightning.force.com":
                continue
            try:
                modal=page.get_by_role("dialog")
                if await modal.count()!=1 or not await modal.is_visible():continue
                text=await modal.inner_text(timeout=3500)
                if stage=="OPPORTUNITY":
                    if "New Opportunity" not in text:continue
                elif "New Quotation: Research-AMEA" not in text:continue
                matching.append((page,modal))
            except Exception:continue
    if len(matching)!=1:
        return None,"NATIVE_FORM_AMBIGUOUS_OR_NOT_OPEN"
    return matching[0],None

async def validate_native_form(page,modal,stage,review,files):
    issues=[]
    if stage=="OPPORTUNITY":
        required=["Opportunity Name","Close Date","Progress Description",
            "Amount","Opportunity Currency","Account Name","Main Contact",
            "Service Line","Stage","Forecast Category"]
        values=await fields(page,required)
        if review["name"] not in str(values["Opportunity Name"]):issues.append("OPPORTUNITY_NAME_MISMATCH")
        if review["close_date_kst"] not in str(values["Close Date"]):
            # Date field can use MM/DD/YYYY; avoid false acceptance.
            issues.append("CLOSE_DATE_NOT_EXACTLY_VERIFIED")
        if str(values["Progress Description"] or "").strip() != review["progress_description"].strip():
            issues.append("PROGRESS_DESCRIPTION_DIFFERS_FROM_APPROVED_TEXT")
        amount=safe_number(str(values["Amount"] or ""))
        if amount is None or amount != Decimal(review["net_krw"]):
            issues.append("OPPORTUNITY_AMOUNT_NOT_RECONCILED")
        for key in ["Account Name","Main Contact","Opportunity Currency","Service Line","Stage","Forecast Category"]:
            if not values.get(key):issues.append("EMPTY_NATIVE_"+key.upper().replace(" ","_"))
        for field,approved in (
            ("Account Name",review["account_name"]),
            ("Main Contact",review["contact_name"]),
            ("Service Line",review["service_line"]),
            ("Stage",review["stage"]),
            ("Forecast Category",review["forecast_category"])
        ):
            if not approved or approved.casefold() not in str(values.get(field) or "").casefold():
                issues.append("NATIVE_"+field.upper().replace(" ","_")+"_DIFFERS_FROM_APPROVED")
        if values.get("Opportunity Currency") and "KRW" not in values["Opportunity Currency"]:
            issues.append("NOT_KRW_CURRENCY")
        # Native contact/account IDs are separately verified in the fresh source
        # readback. The native form must also have a selected visible value.
    else:
        required=["Quotation Name","Opportunity","Quotation Status","GST","Quotation Currency"]
        values=await fields(page,required)
        if review["quote_name"] not in str(values.get("Quotation Name")):
            issues.append("QUOTATION_NAME_MISMATCH")
        journal=read_journal(files)
        if journal["state"]!="OPPORTUNITY_SAVED" or not OPPO_ID.fullmatch(str(journal.get("opportunity_id",""))):
            issues.append("PARENT_OPPORTUNITY_NOT_VERIFIED")
        if not values.get("Opportunity") or (
            review["name"].casefold() not in str(values.get("Opportunity") or "").casefold()
        ):
            issues.append("APPROVED_OPPORTUNITY_PARENT_NAME_NOT_SELECTED")
        # Same names are intentional. A matching name does NOT identify the
        # correct new parent; the native Quote lookup must resolve the newly
        # created 006 ID saved in this request's immutable journal.
        parent_id=str(journal.get("opportunity_id") or "")
        if OPPO_ID.fullmatch(parent_id):
            matching=modal.locator(
                'a[href*="/'+parent_id+'"],[data-recordid="'+parent_id+'"],'+
                '[data-record-id="'+parent_id+'"]'
            )
            if await matching.count()!=1:
                issues.append("QUOTATION_PARENT_NATIVE_006_ID_NOT_VERIFIED")
        else:
            issues.append("QUOTATION_PARENT_NATIVE_006_ID_NOT_VERIFIED")
        if "KRW" not in str(values.get("Quotation Currency") or ""):
            issues.append("QUOTATION_CURRENCY_NOT_VERIFIED")
        if safe_number(str(values.get("GST") or "")) != Decimal("10"):
            issues.append("GST_VAT_NOT_10_PERCENT")
        if not values.get("Quotation Status"):
            issues.append("QUOTATION_STATUS_MISSING")
        # CRITICAL: Source/master Process rows are not automatically added by
        # creating the Quotation header. Require verified live Process rows.
        visible=await modal.inner_text(timeout=6000)
        if ("Quotation Product" not in visible or
             "Quotation Process" not in visible):
            issues.append("QUOTATION_PRODUCT_PROCESS_ROWS_NOT_VERIFIED_IN_FORM")
        # Headers alone are insufficient; native Process IDs must be
        # individually visible/reconciled before a real Quotation Save.
        try:
            from native_save_transaction import _read
            candidate=_read(files["candidate"])
            expected_ids=[
                line["native_process_id"]
                for product in candidate.get("products",[])
                for line in product.get("processes",[])
            ]
            if not expected_ids or len(expected_ids)!=review["native_product_process_rows"] or (
                any(process_id not in visible for process_id in expected_ids)
            ):
                issues.append("QUOTATION_EXACT_NATIVE_PROCESS_ROWS_NOT_RECONCILED")
        except (KeyError,ValueError,TypeError,OSError):
            issues.append("QUOTATION_PROCESS_SOURCE_UNAVAILABLE")
    save=modal.get_by_role("button",name="Save",exact=True)
    if await save.count()!=1 or not await save.is_enabled():
        issues.append("UNIQUE_ENABLED_SAVE_BUTTON_NOT_FOUND")
    # No Save & New; it must never be called.
    return issues,values

async def readback(page,stage,record_name):
    pattern=URL_ID[stage]
    for _ in range(14):
        match=pattern.search(page.url)
        if match:
            record_id=match.group(1)
            # The freshly created record should show its name.
            try:
                body=await page.locator("body").inner_text(timeout=3000)
                if record_name in body:
                    return record_id
            except Exception:pass
        await page.wait_for_timeout(700)
    # Do NOT guess new CRM IDs from unrelated recent list entries.
    return None

async def run(message):
    mode=message.get("mode");stage=message.get("stage")
    request_id=message.get("requestId")
    if mode not in ("PRECHECK","COMMIT") or stage not in ("OPPORTUNITY","QUOTATION"):
        return _gate("INVALID_NATIVE_SAVE_ACTION",stage=stage or "UNKNOWN")
    review,files=load_verified_request(request_id)
    if files is None:return {**review,"stage":stage}
    journal=read_journal(files)
    if journal["state"] in ("UNKNOWN_AFTER_CLICK","HOLD_RECONCILE"):
        return _gate("UNVERIFIED_PRIOR_WRITE_ATTEMPT_NO_RETRY",stage=stage,
            journalState=journal["state"])
    if stage=="OPPORTUNITY" and journal["state"]!="NOT_STARTED":
        return _gate("OPPORTUNITY_ALREADY_SAVED_OR_ATTEMPTED",stage=stage,journalState=journal["state"])
    if stage=="QUOTATION" and journal["state"]!="OPPORTUNITY_SAVED":
        return _gate("OPPORTUNITY_MUST_BE_SAVED_AND_VERIFIED_FIRST",stage=stage,
            journalState=journal["state"])
    try:
        async with async_playwright() as pw:
            browser=await pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=18000)
            try:
                target,err=await find_native_form(browser,stage)
                if err:return _gate(err,stage=stage)
                page,modal=target
                # User-established workflow: existing Contact -> New Opportunity
                # -> saved 006 -> Opportunity Related -> New Quotation.
                # Never silently accept a global-list New modal.
                native_origin_issue=native_origin_route_violation(
                    stage,page.url,review,journal)
                if native_origin_issue:
                    return _gate(native_origin_issue,stage=stage)
                issues,values=await validate_native_form(page,modal,stage,review,files)
                if issues:return _gate("NATIVE_FORM_REVIEW_HOLD",stage=stage,
                    missing=issues,sourceReady=True,
                    approvalDigest=review["approval_digest"])
                # Intentionally do NOT return sensitive field values to JS/web/logs.
                snapshot=(stage+"|"+review["approval_digest"]+"|"+
                   page.url+"|"+review["name"]+"|"+review["net_krw"])
                if mode=="PRECHECK":
                    token=create_session(files,review,stage,snapshot)
                    return {"status":"READY_FOR_EXACT_RECORD_SAVE_CLICK",
                        "stage":stage,"requestId":review["request_id"],
                        "approvalDigest":review["approval_digest"],"nonce":token,
                        "name":review["name"],"quoteName":review["quote_name"],
                        "netKrw":review["net_krw"],"vatKrw":review["vat_krw"],
                        "grossKrw":review["gross_krw"],
                        "productCount":review["quote_product_count"],
                        "processCount":review["native_product_process_rows"],
                        "expiresInSeconds":180,
                        "salesforce_write":False,"save_clicked":False,"crm_writes":0}
                if message.get("approvalDigest")!=review["approval_digest"]:
                    return _gate("DIGEST_CHANGED_SINCE_APPROVAL",stage=stage)
                expected="SAVE "+review["approval_digest"][-8:]
                if message.get("confirmation")!=expected:
                    return _gate("EXACT_SAVE_CONFIRMATION_REQUIRED",stage=stage)
                if message.get("nonce") is None:
                    return _gate("SAVE_SESSION_NONCE_REQUIRED",stage=stage)
                if str(message.get("nonce"))=="":return _gate("SAVE_SESSION_NONCE_REQUIRED",stage=stage)
                if message.get("writeEnabled") is not None:
                    # Caller cannot enable writes by inserting a JSON flag.
                    return _gate("FORGED_WRITE_ENABLE_FLAG",stage=stage)
                issue=consume_session(files,review,stage,message["nonce"],
                   message["approvalDigest"],snapshot=snapshot)
                if issue:return _gate(issue,stage=stage)
                # Both tabs/snapshots must still represent the same exact review.
                # The request cannot replace the URL/record name with client data.
                locked=False
                try:
                    with exclusive_transaction(files):
                        locked=True
                        before=before_click(files,stage,review,
                            opportunity_id=journal.get("opportunity_id"))
                        if before:return _gate(before,stage=stage)
                        try:
                            save=modal.get_by_role("button",name="Save",exact=True)
                            await save.click(timeout=15000)
                            new_id=await readback(page,stage,review["name"])
                            if new_id and not created_id_is_distinct(stage,new_id,review):
                                mark_unknown(files)
                                return {"status":"UNKNOWN_AFTER_CLICK_RECONCILE_REQUIRED",
                                    "stage":stage,"save_clicked":True,
                                    "salesforce_write":True,"crm_writes":"UNVERIFIED",
                                    "code":"RETURNED_ID_IS_EXISTING_RECORD_NOT_NEW",
                                    "automaticRetryAllowed":False}
                            if not new_id:
                                mark_unknown(files)
                                return {"status":"UNKNOWN_AFTER_CLICK_RECONCILE_REQUIRED",
                                    "stage":stage,"save_clicked":True,
                                    "salesforce_write":True,"crm_writes":"UNVERIFIED",
                                    "automaticRetryAllowed":False}
                            if not after_click(files,stage,new_id):
                                return _gate("CREATED_RECORD_ID_NOT_RECONCILED",
                                    stage=stage,save_clicked=True,
                                    salesforce_write=True)
                            return {"status":"NATIVE_SAVE_CREATED_AND_READBACK",
                                "stage":stage,"nativeId":new_id,
                                "requestId":review["request_id"],
                                "save_clicked":True,"salesforce_write":True,
                                "crm_writes":1,
                                "nativeRecordUrl":HOST+"/lightning/r/"+
                                  ("Opportunity/" if stage=="OPPORTUNITY" else "Quotation__c/")+
                                  new_id+"/view",
                                "journalState":read_journal(files)["state"]}
                        except Exception:
                            mark_unknown(files)
                            return {"status":"UNKNOWN_AFTER_CLICK_RECONCILE_REQUIRED",
                                "stage":stage,"save_clicked":"UNCERTAIN",
                                "salesforce_write":"UNCERTAIN",
                                "crm_writes":"UNVERIFIED",
                                "automaticRetryAllowed":False}
                finally:
                    if locked:release_lock(files)
            finally:
                await browser.close()
    except Exception:
        return _gate("NATIVE_SFDC_SESSION_UNAVAILABLE",stage=stage)

async def main():
    try:
        raw=sys.stdin.read(3500)
        message=json.loads(raw)
        if not isinstance(message,dict):
            raise ValueError("INVALID_OBJECT")
        if set(message)-{"mode","stage","requestId","approvalDigest","nonce","confirmation","writeEnabled"}:
            raise ValueError("EXTRA_KEYS_FORBIDDEN")
        result=await run(message)
    except Exception:
        result=_gate("INVALID_NATIVE_SAVE_REQUEST")
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":
    asyncio.run(main())
