#!/usr/bin/env python3
"""Authorized PC SFDC command queue consumer. Never posts Salesforce credentials.

Calls the existing local UI automation using an authenticated Chrome session.
FAIL CLOSED: Oppo+Quote SAVE is blocked until both Cloud process quantity write
and Quote total readback can be verified. No partial/Oppo-only pair creation.
"""
import datetime as dt
import json
import math
import os
import pathlib
import subprocess
import sys
import urllib.parse
from sfdc_quote_price_fields import (
    PRICE_INPUT_FIELDS, PRICE_RESULT_FIELDS,
    evaluate as evaluate_price, evaluate_multi as evaluate_multi_price, PriceError,
)

BASE="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
TAB="CSS SFDC Command Queue"
HEAD=["record_id","Request ID","Action","Source Oppo ID","Source Quote ID","Lead ID",
"New Opportunity Name","New Samples","Data Size Gb","Account Name",
"Contact Korean Name","Contact English Name","Approval","Duplicate Checked",
"Price Checked","Run Mode","Status","New Oppo ID","New Quote ID",
"New Contact ID","Error Code","Checked At"]
HEAD+=PRICE_INPUT_FIELDS+PRICE_RESULT_FIELDS
FINAL={"PREFLIGHT_PASS","PREFLIGHT_BLOCK","PASS","PARTIAL","BLOCK","SOURCE_UNAVAILABLE"}
def column_name(zero_index):
    n=zero_index+1
    if n<1:raise ValueError("INVALID_COL")
    out=""
    while n:
        n,r=divmod(n-1,26)
        out=chr(65+r)+out
    return out
LAST_COLUMN=column_name(len(HEAD)-1)
KST=dt.timezone(dt.timedelta(hours=9))
def json_run(script,payload,timeout=100):
    child=subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name(script))],
        input=json.dumps(payload,ensure_ascii=False),text=True,capture_output=True,
        encoding="utf-8",errors="strict",
        env={**os.environ,"PYTHONIOENCODING":"utf-8","PYTHONDONTWRITEBYTECODE":"1"},
        timeout=timeout)
    try:
        response=json.loads(child.stdout)
        if not isinstance(response,dict):raise ValueError()
        return response
    except Exception:
        return {"status":"BLOCK","code":"LOCAL_SCRIPT_UNAVAILABLE"}

def validate(row):
    x=dict(zip(HEAD,row))
    if x.get("Status") not in ("","NEW","QUEUED","REQUESTED"):
        return False
    if x.get("Action") not in ("LEAD_CONVERT","OPPO_QUOTE_PAIR"):return False
    if x.get("Run Mode")=="CHECK":return x.get("Approval")=="PREFLIGHT"
    if x.get("Run Mode")=="SAVE":
        return x.get("Approval")=="APPROVED" and x.get("Duplicate Checked")=="YES" and x.get("Price Checked")=="YES"
    return False

def row_data(row):
    return dict(zip(HEAD,row))

def integer(x):
    try:
        n=int(x)
        return n if n>0 and n<=500 and str(n)==str(x).strip() else None
    except (ValueError,TypeError):return None
def money(x):
    try:
        n=int(x)
        return n if n>0 and n<=1000000000 else None
    except (ValueError,TypeError):return None
def quantity(x):
    try:
        n=float(x)
        return n if math.isfinite(n) and 0<n<=100000 else None
    except (ValueError,TypeError):return None

def prepare_pair(x):
    oppid=x.get("Source Oppo ID","")
    quoteid=x.get("Source Quote ID","")
    n=integer(x.get("New Samples"))
    size=quantity(x.get("Data Size Gb"))
    name=x.get("New Opportunity Name","").strip()
    if not n or not size or len(name)<5 or not oppid.startswith("006") or not quoteid.startswith("a0P"):
        return {"status":"PREFLIGHT_BLOCK","code":"PAIR_REQUEST_INVALID"}
    bundle=json_run("sfdc_record_catalog.py",{
        "resource":"opportunity","mode":"bundle","recordId":oppid})
    if bundle.get("status")!="PASS" or bundle.get("selectionStatus")!="EXACT_ONE" or len(bundle.get("linkedQuotes") or [])!=1:
        return {"status":"PREFLIGHT_BLOCK","code":"SOURCE_QUOTE_NOT_UNIQUE"}
    original=bundle["opportunity"];quote=bundle["linkedQuotes"][0]
    if quote.get("id")!=quoteid or quote.get("opportunityId")!=oppid:
        return {"status":"PREFLIGHT_BLOCK","code":"SOURCE_PAIR_MISMATCH"}
    multi=isinstance(quote.get("productCount"),int) and quote["productCount"]>1
    status="VERIFIED_MULTI_PRODUCT_LINES" if multi else "VERIFIED_PROCESS_LINES"
    if quote.get("pricingStatus")!=status or quote.get("sourceVatRateVerified10Pct") is not True:
        return {"status":"PREFLIGHT_BLOCK","code":
            "SOURCE_MULTI_PRODUCT_LINES_NOT_VERIFIED" if multi else "SOURCE_PRICE_UNVERIFIED"}
    if not multi and (quote.get("cloudLinePresent") is not True or quote.get("productCount")!=1):
        return {"status":"PREFLIGHT_BLOCK","code":"SOURCE_PRODUCT_UNVERIFIED"}
    if size!=float(quote.get("dataSize") or 0):
        return {"status":"PREFLIGHT_BLOCK","code":"DATA_SIZE_RATE_UNVERIFIED"}
    try:
        evaluator=evaluate_multi_price if multi else evaluate_price
        prices=evaluator(quote,n,size,
            x.get("Requested Product Unit KRW",""),
            x.get("Requested Cloud Unit KRW",""))
    except PriceError as exc:
        return {"status":"PREFLIGHT_BLOCK","code":str(exc)}
    if name==original.get("name"):
        return {"status":"PREFLIGHT_BLOCK","code":"NAME_DUPLICATES_SOURCE"}
    cloud_count=prices["Cloud Qty"]
    net=prices["Quote Net KRW"]
    if not all(original.get(k) for k in ("accountId","contactId","accountName","contactName")):
        return {"status":"PREFLIGHT_BLOCK","code":"ACCOUNT_CONTACT_UNVERIFIED"}
    # Reference only: source progress is NEVER copied.
    progress=("New request: "+name+"; "+str(n)+" samples; "+str(size)+
       " Gb/sample. Source Quote reviewed for unit pricing. PO and sample receipt not confirmed.")
    close=(dt.datetime.now(KST).date()+dt.timedelta(days=30)).isoformat()
    opp={"action":"opportunity_create","mode":"check",
       "referenceOpportunityId":oppid,"accountId":original["accountId"],
       "contactId":original["contactId"],"accountName":original["accountName"],
       "contactName":original["contactName"],"opportunityName":name,
       "samples":n,"amountKrw":net,"closeDate":close,
       "progressDescription":progress}
    if multi:
        # The existing Salesforce Quote writer is single-product only.
        # Expose each verified projected unit rate in Feishu, never execute
        # clone/save until the multi-product UI and final Quote readback work.
        return {"status":"PRICE_ONLY","code":"MULTI_PRODUCT_QUOTE_FORM_NOT_VERIFIED",
                "price_fields":prices,"expectedNet":net,
                "expectedCloudUnits":cloud_count}
    if not quote.get("productCategory") or not quote.get("processNames"):
        return {"status":"PREFLIGHT_BLOCK","code":"SOURCE_PRODUCT_CATALOG_UNVERIFIED"}
    quote_req={"action":"quote_create","mode":"check","sourceQuoteId":quoteid,
       "opportunityId":oppid,"quoteName":name,
       "accountName":original["accountName"],"contactName":original["contactName"],
       "productName":quote["productName"],"productCategory":quote["productCategory"],
       "processNames":quote["processNames"],"samples":n,"dataSize":size}
    return {"status":"READY","code":"PRICING_VALIDATED","opportunity":opp,"quotation":quote_req,
       "expectedNet":net,"expectedCloudUnits":cloud_count,
       "expectedGross":prices["Quote Gross KRW"],"price_fields":prices}

def process(x):
    if x.get("Action")=="LEAD_CONVERT":
        if not all(x.get(k) for k in ("Lead ID","Account Name",
                  "Contact Korean Name","Contact English Name")):
            return {"status":"PREFLIGHT_BLOCK","code":"LEAD_FIELDS_MISSING"}
        mode="save" if x["Run Mode"]=="SAVE" else "check"
        req={"action":"lead_convert","mode":mode,"leadId":x["Lead ID"],
             "accountName":x["Account Name"],
             "koreanName":x["Contact Korean Name"],
             "englishName":x["Contact English Name"],
             "confirmSave":mode=="save","noDuplicateConfirmed":mode=="save"}
        r=json_run("sfdc_action_executor.py",req)
        if mode=="check":
            return {"status":"PREFLIGHT_PASS" if r.get("status")=="PREFLIGHT_PASS" else "PREFLIGHT_BLOCK",
                    "code":"LEAD_UI_VALIDATED" if r.get("status")=="PREFLIGHT_PASS" else r.get("code","LEAD_PREFLIGHT_FAILED")}
        if r.get("status")=="PARTIAL_LEAD_CONVERTED_CONTACT_CDMS_UNVERIFIED":
            return {"status":"PARTIAL","code":"CDMS_NOT_VERIFIED"}
        return {"status":"BLOCK","code":r.get("code") or "LEAD_SAVE_READBACK_REQUIRED"}
    if x.get("Action")=="OPPO_QUOTE_PAIR":
        p=prepare_pair(x)
        if p["status"]=="PRICE_ONLY":
            return {"status":"PREFLIGHT_BLOCK","code":"MULTI_PRODUCT_QUOTE_FORM_NOT_VERIFIED",
                    "price_fields":p["price_fields"]}
        if p["status"]!="READY":return p
        if x["Run Mode"]=="SAVE":
            # Do NOT create an Oppo without reliably setting Cloud process
            # quantities on the Quote and independently reading final net.
            return {"status":"BLOCK","code":"CLOUD_PROCESS_SAVE_READBACK_NOT_VERIFIED",
                    "price_fields":p["price_fields"]}
        r=json_run("sfdc_action_executor.py",p["opportunity"])
        return {"status":"PREFLIGHT_PASS" if r.get("status")=="PREFLIGHT_PASS" else "PREFLIGHT_BLOCK",
                "code":("NET_"+str(p["expectedNet"])+"_CLOUD_"+str(p["expectedCloudUnits"]))
                        if r.get("status")=="PREFLIGHT_PASS" else
                        r.get("code","OPPORTUNITY_PREFLIGHT_FAILED"),
                "price_fields":p["price_fields"]}
    return {"status":"BLOCK","code":"ACTION_NOT_SUPPORTED"}

def session():
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import AuthorizedSession
    raw=os.getenv("GCP_SERVICE_ACCOUNT_JSON","").strip()
    if raw:info=json.loads(raw)
    else:
        p=pathlib.Path(os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or
          pathlib.Path.home()/"CSS_Automation"/"credentials"/"service_account.json")
        if not p.is_file():raise ValueError("LOCAL_DRIVE_AUTH_MISSING")
        info=json.loads(p.read_text(encoding="utf-8"))
    return AuthorizedSession(Credentials.from_service_account_info(info,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]))

def url_range(area):
    return ("https://sheets.googleapis.com/v4/spreadsheets/"+BASE+"/values/"+
      urllib.parse.quote("'"+TAB+"'!"+area,safe="!'"))

def read(s):
    res=s.get(url_range("A1:"+LAST_COLUMN+"2000"),timeout=35)
    res.raise_for_status()
    return res.json().get("values",[])

def cell(s,index,column,value):
    letter=column_name(column)
    url=url_range(letter+str(index))+ "?valueInputOption=RAW"
    res=s.put(url,json={"values":[[value]]},timeout=35)
    res.raise_for_status()
    verify=s.get(url_range(letter+str(index)),timeout=35)
    verify.raise_for_status()
    if verify.json().get("values")!=[[value]]:
        raise ValueError("QUEUE_CELL_READBACK_FAILED")

def write_price(s,index,fields):
    if not fields:return
    if set(fields)!=set(PRICE_RESULT_FIELDS):
        raise ValueError("PRICE_FIELDS_INCOMPLETE")
    start=HEAD.index(PRICE_RESULT_FIELDS[0])
    end=HEAD.index(PRICE_RESULT_FIELDS[-1])
    rng=column_name(start)+str(index)+":"+column_name(end)+str(index)
    values=[str(fields[k]) for k in PRICE_RESULT_FIELDS]
    resp=s.put(url_range(rng)+"?valueInputOption=RAW",
        json={"values":[values]},timeout=35)
    resp.raise_for_status()
    verify=s.get(url_range(rng),timeout=35)
    verify.raise_for_status()
    if verify.json().get("values")!=[values]:
        raise ValueError("PRICE_SINK_READBACK_FAILED")

def run():
    s=session();rows=read(s)
    if not rows or rows[0]!=HEAD:return {"status":"BLOCK","code":"QUEUE_SOURCE_MISSING"}
    eligible_count=0
    for i,row in enumerate(rows[1:],start=2):
        if len(row)<len(HEAD):row=row+[""]*(len(HEAD)-len(row))
        if not validate(row):continue
        eligible_count+=1
        status_col=HEAD.index("Status")
        # Claim first, then never retry automatically after possible CRM writes.
        cell(s,i,status_col,"RUNNING")
        result=process(row_data(row))
        write_price(s,i,result.get("price_fields"))
        stamp=dt.datetime.now(KST).isoformat(timespec="seconds")
        for k,value in [("Error Code",str(result.get("code") or "")),
                        ("Checked At",stamp),("Status",result["status"])]:
            cell(s,i,HEAD.index(k),value)
    return {"status":"PASS","eligible_seen":eligible_count,"processed":eligible_count,
            "writes_to_salesforce":"ONLY_APPROVED_LEAD_CONVERT",
            "pair_save":"BLOCKED_PENDING_PRICE_READBACK"}
if __name__=="__main__":
    try:print(json.dumps(run(),sort_keys=True))
    except Exception as exc:
        print(json.dumps({"status":"BLOCK","error_type":type(exc).__name__}),file=sys.stderr)
        sys.exit(2)
