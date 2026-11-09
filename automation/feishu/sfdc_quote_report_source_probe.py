"""Read-only report-source discovery in the user-owned Feishu Sales Base.

Run only with explicit GitHub Actions Feishu credentials. Never prints any
customer records, amounts, identifiers, secrets, or report attachment content.
Report-line pricing is verified only if required process-level fields exist.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse as up
import urllib.request as ur

ROOT="https://open.feishu.cn"
TARGET_TABLES=("Quotes","Weekly Quote KPI","QQ Mail Intake","SFDC_COMMAND_QUEUE")
REPORT_HINTS=("quote","quotation","report","sfdc","pricing","process")
SENSITIVE=re.compile(r"access_token|secret|password|authorization",re.I)


def request(method,path,token=None,payload=None):
    headers={"Content-Type":"application/json"}
    if token:headers["Authorization"]="Bearer "+token
    body=json.dumps(payload).encode() if payload is not None else None
    with ur.urlopen(ur.Request(ROOT+path,method=method,headers=headers,data=body),timeout=25) as res:
        data=json.load(res)
    if data.get("code")!=0:
        raise RuntimeError("FEISHU_API_REJECTED_"+str(data.get("code")))
    # Feishu auth returns tenant_access_token at top level, whereas Bitable
    # response payloads normally nest their data under a data key.
    return data.get("data") or data


def paginate(root,token,cap=300):
    items=[]
    cursor=None
    for _ in range(20):
        query=up.urlencode({"page_size":100,**({"page_token":cursor} if cursor else {})})
        r=request("GET",root+"?"+query,token)
        items.extend(r.get("items") or [])
        if len(items)>cap:raise RuntimeError("FEISHU_PAGINATION_LIMIT")
        if not r.get("has_more"):return items
        newer=r.get("page_token")
        if not newer or newer==cursor:raise RuntimeError("FEISHU_PAGE_INVALID")
        cursor=newer
    raise RuntimeError("FEISHU_PAGE_CAP")


def auth():
    app=os.environ["FEISHU_APP_ID"]
    secret=os.environ["FEISHU_APP_SECRET"]
    data=request("POST","/open-apis/auth/v3/tenant_access_token/internal",
                 payload={"app_id":app,"app_secret":secret})
    token=data.get("tenant_access_token")
    if not token:raise RuntimeError("FEISHU_AUTH_BLOCK")
    return token


def normalized(name):
    return re.sub(r"[^a-z0-9가-힣]","",str(name).lower())


def report_coverage(fields):
    names={normalized(f.get("field_name","")) for f in fields}
    def present(*keywords):
        return any(any(word in x for word in keywords) for x in names)
    return {
        "quote_identifier":present("quotationid","quoteid","sfdcquotationid","salesforcerecordid"),
        "product_identifier":present("quotationproductid","quoteproductid","productid"),
        "process_identifier":present("processid","sfdcprocessid","processname","processkey"),
        "unit_price":present("unitprice","단가"),
        "sample_quantity":present("samplequantity","sampleqty","samples","샘플수량"),
        "currency":present("currency","통화","unitpriceusd"),
        "source_updated_at":present("exportedat","sourceexportedkst","lastmodified","수집시각","reporttime","원본시각"),
    }


def main():
    base=os.environ.get("FEISHU_BASE_APP_TOKEN","").strip()
    if not base:raise RuntimeError("FEISHU_SALES_BASE_TOKEN_MISSING")
    token=auth()
    root="/open-apis/bitable/v1/apps/"+up.quote(base,safe="")
    tables=paginate(root+"/tables",token,300)
    found=[]
    for item in tables:
        name=item.get("name","")
        if name not in TARGET_TABLES and not any(s in name.lower() for s in REPORT_HINTS):
            continue
        tid=item.get("table_id")
        if not tid:continue
        fields=paginate(root+"/tables/"+up.quote(tid,safe="")+"/fields",token,200)
        coverage=report_coverage(fields)
        process_ready=all(coverage[k] for k in
            ("quote_identifier","product_identifier","process_identifier","unit_price","sample_quantity","currency"))
        found.append({"table_name":name,
                      "table_id":tid if name in (
                          "SFDC Quote Process Dictionary","SFDC Quote Product Templates",
                          "SFDC Quote Report Lines") else "",
                      "readonly_column_ids":{
                          x.get("field_name"):x.get("field_id")
                          for x in fields
                          if name in ("SFDC Quote Report Lines",
                                       "SFDC Quote Process Dictionary",
                                       "SFDC Quote Product Templates")
                          and x.get("field_name") in (
                              "Line Key","Quote ID","Quote Record ID",
                              "Quote Product ID","Product Template Key","Process Keys","Process Count",
                              "Process Key","Process ID","Process Name","Data Unit",
                              "Unit Price USD","Sales Price USD",
                              "Process Total USD","Sample Qty","Data Size",
                              "Active","Quote Created","Source Exported KST",
                              "Source Row Hash","Source Status")
                      },
                      "field_count":len(fields),
                      "report_line_schema_complete":process_ready,
                      "report_field_coverage":coverage})
    quote_tables=[r for r in found if r["table_name"]=="Quotes"]
    ready=any(r["report_line_schema_complete"] for r in found)
    print(json.dumps({
        "status":"PASS" if found else "BLOCK",
        "base_access":"PASS",
        "total_base_tables":len(tables),
        "quote_table_found":len(quote_tables)==1,
        "report_line_source":"FEISHU_PROCESS_LINES_PRESENT" if ready else "FEISHU_AGGREGATE_OR_REPORT_LINE_MISSING",
        "tables":found,"crm_writes":0,"feishu_writes":0,"print_customer_records":False,
    },ensure_ascii=False,sort_keys=True))


if __name__=="__main__":
    try:main()
    except Exception as exc:
        print(json.dumps({"status":"BLOCK","error_type":type(exc).__name__,
                          "code":str(exc) if isinstance(exc,RuntimeError) and re.fullmatch(r"[A-Z0-9_]{5,100}",str(exc)) else "FEISHU_SOURCE_UNAVAILABLE",
                          "crm_writes":0,"feishu_writes":0}),file=sys.stderr)
        sys.exit(2)
