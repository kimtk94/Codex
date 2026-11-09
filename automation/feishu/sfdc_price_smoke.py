"""Feishu SFDC real-source quote price smoke, CHECK-only and disposable."""
import json,os,re,sys
from sfdc_command_queue import auth,schema,path,pages,call,plain,google,mirror,HEAD,gs,adr,LAST_COLUMN

KEY="CSS_SFDC_READONLY_PRICING_HEALTHCHECK"
NAME="Korea-CSS-Feishu-Price-E2E-12sample"
class SmokeError(ValueError):pass

def endpoint(table_id):
    return path()+"/tables/"+table_id+"/records"

def locate(token,tid):
    matches=[r for r in pages(token,endpoint(tid)) if
      plain((r.get("fields") or {}).get("Request ID"))==KEY]
    if len(matches)>1:raise SmokeError("DUPLICATE_SMOKE")
    return matches

def seed(token,tid):
    if locate(token,tid):raise SmokeError("SMOKE_ALREADY_EXISTS")
    opp=os.getenv("CSS_SFDC_SMOKE_OPPO_ID","")
    quote=os.getenv("CSS_SFDC_SMOKE_QUOTE_ID","")
    if not re.fullmatch(r"006[A-Za-z0-9]{15}",opp) or not re.fullmatch(r"a0P[A-Za-z0-9]{15}",quote):
        raise SmokeError("SOURCE_SECRETS_UNAVAILABLE")
    fields={
      "Request ID":KEY,"Action":"OPPO_QUOTE_PAIR",
      "Source Oppo ID":opp,"Source Quote ID":quote,
      "New Opportunity Name":NAME,"New Samples":"12","Data Size Gb":"12",
      "Approval":"PREFLIGHT","Run Mode":"CHECK","Status":"NEW"}
    resp=call("POST",endpoint(tid),token,{"fields":fields})
    rid=(resp.get("record") or {}).get("record_id")
    hits=locate(token,tid)
    if not rid or len(hits)!=1 or hits[0].get("record_id")!=rid or any(
        plain((hits[0].get("fields") or {}).get(k))!=v for k,v in fields.items()):
        raise SmokeError("SMOKE_CREATION_READBACK_FAILED")
    return {"status":"PASS","mode":"smoke_seed","created":1,"read_only":True}

def verify(token,tid):
    hits=locate(token,tid)
    if len(hits)!=1:raise SmokeError("SMOKE_ROW_MISSING")
    f=hits[0].get("fields") or {}
    if plain(f.get("Status"))!="PREFLIGHT_PASS":
        raise SmokeError("SMOKE_PREFLIGHT_NOT_PASS")
    numbers={}
    for k in ("Sample Unit KRW","Product Unit KRW","Product Qty","Product Net KRW",
      "Cloud Unit KRW","Cloud Qty","Cloud Net KRW","Quote Net KRW","VAT KRW","Quote Gross KRW"):
        v=plain(f.get(k))
        if not v.isdigit():raise SmokeError("SMOKE_RESULT_MISSING_NUMBER")
        numbers[k]=int(v)
    n=numbers
    net=n["Product Net KRW"]+n["Cloud Net KRW"]
    if n["Product Qty"]!=12 or n["Cloud Qty"]!=2 or n["Sample Unit KRW"]!=n["Product Unit KRW"] or (
       n["Product Net KRW"]!=12*n["Product Unit KRW"]) or (
       n["Cloud Net KRW"]!=2*n["Cloud Unit KRW"]) or (
       n["Quote Net KRW"]!=net) or n["VAT KRW"]!=net//10 or n["Quote Gross KRW"]!=net+net//10:
        raise SmokeError("SMOKE_PRICE_INCONSISTENT")
    if plain(f.get("Price Status"))!="SOURCE_VERIFIED_PROJECTION":
        raise SmokeError("SMOKE_PRICE_SOURCE_UNVERIFIED")
    rows=mirror(google())
    found=[r+[""]*(len(HEAD)-len(r)) for r in rows.values() if
      len(r)>HEAD.index("Request ID") and r[HEAD.index("Request ID")]==KEY]
    if len(found)!=1:raise SmokeError("SMOKE_MIRROR_MISSING")
    row=found[0]
    for k in ("Status","Sample Unit KRW","Product Unit KRW","Product Qty",
      "Product Net KRW","Cloud Unit KRW","Cloud Qty","Cloud Net KRW",
      "Quote Net KRW","VAT KRW","Quote Gross KRW","Price Status"):
        if plain(f.get(k))!=str(row[HEAD.index(k)]):
            raise SmokeError("SMOKE_FEISHU_MIRROR_MISMATCH")
    return {"status":"PASS","mode":"smoke_verify","count":1,
       "product_unit_krw":n["Product Unit KRW"],
       "product_qty":12,"product_net_krw":n["Product Net KRW"],
       "cloud_unit_krw":n["Cloud Unit KRW"],"cloud_qty":2,
       "cloud_net_krw":n["Cloud Net KRW"],"net_krw":net,
       "vat_krw":n["VAT KRW"],"gross_krw":n["Quote Gross KRW"],
       "source_sink":"PASS","crm_writes":0}

def cleanup(token,tid):
    hits=locate(token,tid)
    if len(hits)!=1:raise SmokeError("SMOKE_ROW_MISSING")
    f=hits[0].get("fields") or {}
    if plain(f.get("Run Mode"))!="CHECK" or plain(f.get("Approval"))!="PREFLIGHT" or (
       plain(f.get("Status")) not in ("PREFLIGHT_PASS","PREFLIGHT_BLOCK","BLOCK")):
        raise SmokeError("SMOKE_CLEANUP_NOT_SAFE")
    s=google()
    rows=mirror(s)
    if len(rows)!=1 or next(iter(rows.values()))[HEAD.index("Request ID")]!=KEY:
        raise SmokeError("SMOKE_CLEANUP_OTHER_ROWS_PRESENT")
    call("DELETE",endpoint(tid)+"/"+hits[0]["record_id"],token)
    if locate(token,tid):raise SmokeError("SMOKE_FEISHU_DELETE_UNVERIFIED")
    gs(s,"POST","/values/"+adr("A2:"+LAST_COLUMN+"2")+":clear",{})
    if gs(s,"GET","/values/"+adr("A2:"+LAST_COLUMN+"2")).get("values"):
        raise SmokeError("SMOKE_SHEET_CLEAR_UNVERIFIED")
    return {"status":"PASS","mode":"smoke_cleanup","deleted":1,
       "mirror_cleared":True,"crm_writes":0}

def main(mode):
    if mode not in ("smoke_seed","smoke_verify","smoke_cleanup"):
        raise SmokeError("INVALID_SMOKE_OPERATION")
    token=auth();tid=schema(token)
    return {"smoke_seed":seed,"smoke_verify":verify,"smoke_cleanup":cleanup}[mode](token,tid)

if __name__=="__main__":
    try:print(json.dumps(main(sys.argv[1] if len(sys.argv)>1 else ""),sort_keys=True))
    except Exception as exc:
        reason=str(exc) if isinstance(exc,SmokeError) and re.fullmatch(r"[A-Z0-9_]{5,90}",str(exc)) else "SMOKE_API_OR_ACCESS_ERROR"
        print(json.dumps({"status":"BLOCK","code":reason}),file=sys.stderr)
        sys.exit(2)
