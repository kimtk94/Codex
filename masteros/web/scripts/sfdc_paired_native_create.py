"""Approved paired Salesforce create: live source -> no-save review -> staged writes.

Input: immutable server-loaded, privately queued request canonical only.
CHECK: zero SFDC writes. SAVE: only after one-use browser approval, durable
server journal and explicit per-record authorization. A partial commit is
never retried automatically, even after process failure.
"""
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

KST=ZoneInfo("Asia/Seoul")
NATIVE_ID=re.compile(r"^(?:006|a0P|001|003)[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
REQUEST_ID=re.compile(r"^OPPOQUOTE-[a-f0-9]{24}$")
def failure(code,**extra):return {"status":"BLOCK","code":code,"salesforceWrite":False,**extra}
def _num(x):
    try:return float(str(x).strip())
    except (ValueError,TypeError):return None
def _whole(x):
    if isinstance(x,str) and re.fullmatch(r"\d{1,10}",x):
        return int(x)
    return None
def _ids_match(a,b):return isinstance(a,str) and isinstance(b,str) and a[:15]==b[:15] and len(a)>=15 and len(b)>=15

def request_from_queue(canonical):
    if not isinstance(canonical,dict):raise ValueError("QUEUE_CANONICAL_INVALID")
    source=canonical.get("reference")
    proposed=canonical.get("proposed")
    review=canonical.get("review")
    if not all(isinstance(x,dict) for x in (source,proposed,review)):
        raise ValueError("QUEUE_REVIEW_FIELDS_MISSING")
    if review.get("preflightStatus")!="PREVIEW_READY" or review.get("verifiedNativeRateForUnchangedAmount") is not True:
        raise ValueError("QUEUE_NATIVE_PRICE_NOT_VERIFIED")
    if (proposed.get("accountMode")!="KEEP" or proposed.get("quoteFeeMode")!="EXCLUDE" or
        proposed.get("quoteFeeLines") or not isinstance(proposed.get("products"),list) or
        len(proposed["products"])!=1):
        raise ValueError("SINGLE_PRODUCT_NO_FEE_REQUIRED")
    p=proposed["products"][0]
    if not isinstance(p,dict) or p.get("priceEvidenceStatus")!="LIVE_SFDC_KRW_VERIFIED":
        raise ValueError("SOURCE_KRW_RATE_NOT_APPROVED")
    if (p.get("amplicon",{}).get("enabled") is True or p.get("fixedProcessLines") or
        not isinstance(p.get("processNames"),list) or
        not 1<=len(p["processNames"])<=12 or
        not isinstance(p.get("processIds"),list) or
        len(p["processIds"])!=len(p["processNames"])):
        raise ValueError("SOURCE_PRODUCTS_NEED_NATIVE_REVIEW")
    n=_whole(p.get("samples"))
    unit=_whole(p.get("sampleUnitKrw"))
    cloud_unit=_whole(p.get("cloudUnitKrw"))
    size=_num(p.get("productionGb"))
    if (n is None or not 1<=n<=500 or unit is None or cloud_unit is None or
        not 0<size<=100000 or unit<=0):
        raise ValueError("QUOTE_PRICE_INPUTS_INVALID")
    close=proposed.get("closeDate")
    if not isinstance(close,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",close):
        raise ValueError("OPPO_CLOSE_DATE_REQUIRED")
    name=proposed.get("name")
    description=proposed.get("description")
    if not isinstance(name,str) or not 5<=len(name)<=180 or not isinstance(description,str) or not 12<=len(description)<=3000:
        raise ValueError("OPPO_NAME_PROGRESS_REQUIRED")
    if any(not isinstance(source.get(k),str) or not NATIVE_ID.fullmatch(source[k])
           for k in ("sourceQuoteId","opportunityId")):
        raise ValueError("SOURCE_IDS_INVALID")
    if (not isinstance(proposed.get("account"),dict) or not
        isinstance(proposed.get("contact"),dict) or
        not all(NATIVE_ID.fullmatch(str(proposed[k].get("id",""))) for k in ("account","contact"))):
        raise ValueError("ACCOUNT_CONTACT_NATIVE_IDS_REQUIRED")
    return {"sourceOpportunityId":source["opportunityId"],
        "sourceQuoteId":source["sourceQuoteId"],"sourceQid":source.get("qid"),
        "name":name,"description":description,"closeDate":close,
        "samples":n,"sizeGb":size,"sampleUnitKrw":unit,
        "cloudUnitKrw":cloud_unit,
        "account":proposed["account"],"contact":proposed["contact"],
        "processNames":p["processNames"],"processIds":p["processIds"],
        "expectedNet":n*unit+math.ceil(n*size/100)*cloud_unit}


def build_live_plan(queue):
    from feishu_sfdc_local_worker import prepare_pair
    data=request_from_queue(queue)
    req={"Source Oppo ID":data["sourceOpportunityId"],
        "Source Quote ID":data["sourceQuoteId"],"New Samples":str(data["samples"]),
        "Data Size Gb":str(data["sizeGb"]),"New Opportunity Name":data["name"],
        "Requested Product Unit KRW":"","Requested Cloud Unit KRW":""}
    checked=prepare_pair(req)
    if checked.get("status")!="READY" or checked.get("sourcePackEvidence",{}).get("state")!="PASS":
        return failure(checked.get("code") or "FRESH_SOURCE_PACK_PRICE_UNAVAILABLE"),None
    opp=checked["opportunity"]
    quote=checked["quotation"]
    if (opp["accountId"]!=data["account"]["id"] or opp["contactId"]!=data["contact"]["id"] or
        opp["accountName"]!=data["account"]["name"] or
        opp["contactName"]!=data["contact"]["name"]):
        return failure("CUSTOMER_IDENTITY_DIFFERS_FROM_APPROVED_REQUEST"),None
    if (checked["expectedNet"]!=data["expectedNet"] or
        checked["price_fields"].get("Sample Unit KRW")!=data["sampleUnitKrw"] or
        checked["price_fields"].get("Cloud Unit KRW")!=data["cloudUnitKrw"]):
        return failure("NATIVE_PRICE_MISMATCH_REAPPROVAL_REQUIRED"),None
    if set(quote["processNames"].split(",")) != set(data["processNames"]):
        return failure("SOURCE_PROCESS_NAMES_DIFFERS_FROM_REQUEST"),None
    # Source process lines include *actual customer-specific KRW* rates.
    # Never use Standard Price / USD-converted Report values in this writer.
    lines=checked["sourcePackEvidence"]["process_lines"]
    from sfdc_native_process_writer import validated_price_plan
    price_plan=validated_price_plan(lines,data["samples"],data["sizeGb"],data["expectedNet"])
    opp["progressDescription"]=data["description"]
    opp["closeDate"]=data["closeDate"]
    quote["processPlan"]=price_plan
    quote["quoteName"]=data["name"]
    return {"status":"READY","netKrw":price_plan["expectedNet"],
        "grossKrw":int(price_plan["expectedNet"]*11/10),
        "samples":data["samples"],"dataSizeGb":data["sizeGb"],
        "cloudUnits":price_plan["cloudUnits"],"processCount":len(lines),
        "pricePlan":price_plan,"opportunity":opp,"quotation":quote},data


def dry_run(plan):
    from feishu_sfdc_local_worker import json_run
    opp=json_run("sfdc_action_executor.py",plan["opportunity"],timeout=100)
    if opp.get("status")!="PREFLIGHT_PASS" or opp.get("save_clicked") is not False:
        return failure(opp.get("code") or "OPPORTUNITY_UI_PREFLIGHT_BLOCK")
    quote=json_run("sfdc_action_executor.py",plan["quotation"],timeout=100)
    if quote.get("status")!="PREFLIGHT_PASS" or quote.get("save_clicked") is not False:
        return failure(quote.get("code") or "QUOTE_UI_PREFLIGHT_BLOCK")
    return {"status":"PREFLIGHT_PASS","code":"OPPO_AND_QUOTE_HEADER_UI_VERIFIED",
            "salesforceWrite":False,"expectedNetKrw":plan["netKrw"],
            "expectedGrossKrw":plan["grossKrw"],"samples":plan["samples"],
            "gbPerSample":plan["dataSizeGb"],"cloudUnits":plan["cloudUnits"],
            "processCount":plan["processCount"],"productWriter":"CHECK_AT_NEW_QUOTE_AFTER_HEADER",
            "quoteHeaderPartialRisk":True}


def json_journal(path,state,**extra):
    # Journal is server-owned, request-specific and was exclusively claimed
    # before SAVE subprocess start. Never erase a previous write.
    entry={"state":state,"updatedAtUtc":dt.datetime.now(dt.timezone.utc).isoformat(),**extra}
    tmp=path.with_suffix(".tmp")
    with tmp.open("x",encoding="utf8") as f:
        json.dump(entry,f,ensure_ascii=False)
        f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)


def execute_pair(plan,journal):
    from feishu_sfdc_local_worker import json_run
    opp={**plan["opportunity"],"mode":"save",
         "confirmSave":True,"noDuplicateConfirmed":True}
    json_journal(journal,"OPPORTUNITY_CLICK_POSSIBLE")
    first=json_run("sfdc_action_executor.py",opp,timeout=105)
    if first.get("status")!="PASS" or not re.fullmatch(r"006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?",str(first.get("record_id",""))):
        json_journal(journal,"PARTIAL_UNKNOWN_OPPORTUNITY",stage="OPPORTUNITY",
                     createdOpportunityId=first.get("record_id"),code=first.get("code") or first.get("status"))
        return {"status":"PARTIAL_RECONCILE_REQUIRED","stage":"OPPORTUNITY",
                "opportunityId":first.get("record_id"),"quoteId":None,
                "code":"OPPO_SAVE_OR_READBACK_UNVERIFIED",
                "automaticRetryAllowed":False,"salesforceWrite":"POSSIBLE"}
    opportunity_id=first["record_id"]
    json_journal(journal,"OPPORTUNITY_SAVED",
                 createdOpportunityId=opportunity_id)
    quote={**plan["quotation"],"mode":"save","opportunityId":opportunity_id,
           "confirmSave":True,"noDuplicateConfirmed":True}
    json_journal(journal,"QUOTE_HEADER_CLICK_POSSIBLE",
                 createdOpportunityId=opportunity_id)
    second=json_run("sfdc_action_executor.py",quote,timeout=135)
    quote_id=second.get("record_id")
    if (second.get("status")!="PASS" or not
        re.fullmatch(r"a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?",str(quote_id)) or
        second.get("price_verified") is not True):
        json_journal(journal,"PARTIAL_QUOTE_RECONCILE_REQUIRED",
                     createdOpportunityId=opportunity_id,
                     createdQuoteId=quote_id,code=second.get("status"))
        return {"status":"PARTIAL_RECONCILE_REQUIRED","stage":"QUOTATION",
                "opportunityId":opportunity_id,"quoteId":quote_id,
                "code":second.get("status") or "QUOTE_READBACK_UNVERIFIED",
                "automaticRetryAllowed":False,"salesforceWrite":True}
    json_journal(journal,"COMPLETE",createdOpportunityId=opportunity_id,
                 createdQuoteId=quote_id,
                 verifiedNetKrw=second.get("quote_net_krw"),
                 verifiedGrossKrw=second.get("quote_gross_krw"))
    return {"status":"PAIR_CREATED_VERIFIED","opportunityId":opportunity_id,
            "quoteId":quote_id,"netKrw":second.get("quote_net_krw"),
            "grossKrw":second.get("quote_gross_krw"),
            "salesforceWrite":True,"automaticRetryAllowed":False}


def main():
    try:
        req=json.loads(sys.stdin.buffer.read(45000).decode("utf-8"))
        if not isinstance(req,dict) or set(req)-{"mode","canonical","requestId","journalPath"}:
            raise ValueError("UNKNOWN_REQUEST_KEYS")
        mode=req.get("mode")
        if mode not in ("PREFLIGHT","SAVE"):raise ValueError("WRONG_MODE")
        plan,data=build_live_plan(req["canonical"])
        if plan.get("status")!="READY":result=plan
        elif mode=="PREFLIGHT":result=dry_run(plan)
        else:
            request_id=req.get("requestId")
            journal=req.get("journalPath")
            if not isinstance(request_id,str) or not REQUEST_ID.fullmatch(request_id):
                raise ValueError("REQUEST_ID_REQUIRED")
            base=Path(os.environ["LOCALAPPDATA"])/"SFDC_Oppo_Quote_Approval_Requests"
            expected=base/(request_id+".journal.json")
            if Path(journal)!=expected:
                raise ValueError("JOURNAL_PATH_MISMATCH")
            if expected.exists():raise ValueError("SAVE_RETRY_FORBIDDEN")
            result=execute_pair(plan,expected)
    except Exception as exc:
        code=str(exc) if isinstance(exc,ValueError) and re.fullmatch(r"[A-Z0-9_]{5,90}",str(exc)) else "NATIVE_SAVE_WORKER_UNAVAILABLE"
        result=failure(code)
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
