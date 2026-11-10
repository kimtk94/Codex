#!/usr/bin/env python3
"""Audit project lifecycle and quote amount candidates without logging customer rows."""
import collections
import json
import re
from sales_home_links import API, PROJECT_BOARD, pages, request, require, extract_token

TABLES = {
    "PROJECT_BOARD": PROJECT_BOARD,
    "QUOTES": "tblaFDb2DZRJjCxy",
    "QUOTE_INDEX": "tblkUTP09Sqy6vKk",
    "QUOTE_LINES": "tblHme64Ccdj4Fwv",
}
VIEWS = {
    "ACTIVE": "vew9v3YnBX",
    "COMPLETED_BILLING": "vewzKSaZ1p",
    "PAID_ARCHIVE": "vewIKJf0Fj",
}
FINANCIAL_RE = re.compile(r"amount|net|price|revenue|krw|usd|vat|tax|value|invoice|quotation|quote|total|subtotal", re.I)
STAGE_RE = re.compile(r"stage|progress|next|status|date|updated|receipt|sample|project", re.I)

def textval(value):
    if isinstance(value,str): return value.strip()
    if isinstance(value,list):
        return "".join(textval(x) for x in value).strip()
    if isinstance(value,dict):
        return str(value.get("text") or value.get("name") or value.get("value") or "").strip()
    return "" if value is None else str(value).strip()

def profile(records, fields):
    counts={}
    for f in fields:
        key=f["field_name"]
        filled=0; numeric=0
        for row in records:
            v=(row.get("fields") or {}).get(key)
            if v is not None and v!="" and v!=[]:
                filled+=1
                if isinstance(v,(float,int)) and not isinstance(v,bool):
                    numeric+=1
        counts[key]={"nonempty":filled,"numeric":numeric,"type":f.get("type")}
    return counts

def collisions(records, key):
    values=[textval((r.get("fields") or {}).get(key)) for r in records]
    filled=[x for x in values if x]
    counts=collections.Counter(filled)
    return {"rows":len(values),"filled":len(filled),"distinct":len(counts),
            "duplicate_values":sum(c>1 for c in counts.values()),
            "duplicate_rows":sum(c-1 for c in counts.values())}

def summarize(schema, records):
    stats=profile(records,schema)
    return {"rows":len(records),
            "finance_fields":[{"name":k,**v} for k,v in stats.items() if FINANCIAL_RE.search(k)],
            "lifecycle_fields":[{"name":k,**v} for k,v in stats.items() if STAGE_RE.search(k) and k not in ("Source Key",)],
            "all_field_count":len(schema)}

def main():
    response=request("POST","/open-apis/auth/v3/tenant_access_token/internal",
                     body={"app_id":require("FEISHU_APP_ID"),"app_secret":require("FEISHU_APP_SECRET")})
    token=extract_token(response)
    results={}
    for label,table_id in TABLES.items():
        path=API+"/tables/"+table_id
        schema=list(pages(path+"/fields",token))
        records=list(pages(path+"/records",token))
        data=summarize(schema,records)
        data["name_collisions"]={n:collisions(records,n) for n in
            ("Quote Full Name","Quote Name","Quotation Name","Quotation No","Source Key")
            if n in {f.get("field_name") for f in schema}}
        if label=="PROJECT_BOARD":
            data["views"]={}
            for view,view_id in VIEWS.items():
                sub=list(pages(path+"/records",token,{"view_id":view_id}))
                data["views"][view]={"count":len(sub),
                   "quote":collisions(sub,"Quote Full Name"),
                   "progress":profile(sub,[{"field_name":"Progress %","type":2},
                                          {"field_name":"Current Stage","type":1}])}
        results[label]=data
    print("PROJECT_QUOTE_READONLY_AUDIT "+json.dumps(results,ensure_ascii=False,sort_keys=True))
    print("SOURCE_WRITES=0 SOURCE_VALUES_LOGGED=0")

if __name__=="__main__":
    main()
