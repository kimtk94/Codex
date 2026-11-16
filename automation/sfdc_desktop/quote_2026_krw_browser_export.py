"""Read-only local Salesforce 2026 native KRW process price evidence exporter.

Requires an already-authenticated Chrome CDP session at 127.0.0.1:9222,
a private independently checked approval manifest, and known Process IDs.
Never sends data to GitHub, never clicks Edit/Save and never changes CRM.
"""
import argparse, hashlib, json, re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from playwright.sync_api import sync_playwright
from quote_2026_krw_totals_guard import require_original_krw_totals
from quote_2026_createddate_kst_guard import verify_createddate_utc_kst

SFDC="https://novogene.lightning.force.com"
ID_RX=re.compile(r"^a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
PROCESS_RX=re.compile(r"^Process-[A-Za-z0-9-]{8,64}$")
QID_RX=re.compile(r"^QID-2026-[0-9-]{8,50}$")
NUM_RX=re.compile(r"^[0-9,]+(?:\.[0-9]{1,4})?$")
def amount(s):
    t=str(s or "").replace(",","").strip()
    if not NUM_RX.fullmatch(t):raise ValueError("NON_NUMERIC_KRW")
    return Decimal(t)
def next_field(lines,key):
    for i,v in enumerate(lines[:-1]):
        if v==key:return lines[i+1]
    return ""
def money_after(text,label):
    m=re.search(re.escape(label)+r"\s*\n\s*KRW\s*([\d,]+(?:\.\d+)?)",text)
    if not m:raise ValueError("TOTAL_KRW_NOT_VISIBLE")
    return amount(m.group(1))
def native_lookup(hrefs,object_name):
    rx=re.compile(r"/lightning/r/"+object_name+r"/([A-Za-z0-9]{15,18})/view")
    ids={m.group(1) for h in hrefs for m in [rx.search(h)] if m}
    if len(ids)!=1 or not next(iter(ids)).startswith("001" if object_name=="Account" else "003"):
        raise ValueError("NATIVE_ID_UNVERIFIED")
    return next(iter(ids))
def extract(page,reference):
    qid=reference["quote_id"];rid=reference["record_id"]
    if not QID_RX.fullmatch(qid) or not ID_RX.fullmatch(rid) or reference.get("approval_evidence")!="APPROVED_TEXT":
        raise ValueError("APPROVAL_MANIFEST_INVALID")
    if not re.fullmatch(r"2026-\d{2}-\d{2}",reference["created_date"]):
        raise ValueError("CREATED_DATE_UNVERIFIED")
    process_ids=reference.get("process_ids") or {}
    if not process_ids or any(not PROCESS_RX.fullmatch(v) for v in process_ids.values()):
        raise ValueError("PROCESS_ID_MAP_MISSING")
    resolution=reference.get("source_date_resolution")
    if resolution:
        if resolution!="NATIVE_UTC_TO_ASIA_SEOUL_EXACT":
            raise ValueError("DATE_RESOLUTION_UNVERIFIED")
        # The saved reference is not sufficient: we also re-read the LIVE native
        # CreatedDate using authenticated Salesforce UI API after navigation.
        verify_createddate_utc_kst(
            qid,reference["created_date"],reference.get("qq_created_date_kst"),
            reference.get("native_created_at_utc"))
    page.goto(SFDC+"/lightning/r/Quotation__c/"+rid+"/view",wait_until="domcontentloaded",timeout=30000)
    page.wait_for_function("qid=>document.title.includes(qid)",arg=qid,timeout=18000)
    if resolution:
        result=page.evaluate("""async (rid)=>{
          const res=await fetch('/services/data/v62.0/ui-api/records/'+rid
             +'?fields=Quotation__c.CreatedDate',
             {method:'GET',credentials:'same-origin'});
          if(!res.ok)return null;
          const obj=await res.json();
          return obj?.fields?.CreatedDate?.value??null;
        }""",rid)
        if not result or result!=reference.get("native_created_at_utc"):
            raise ValueError("LIVE_SFDC_CREATED_DATE_EVIDENCE_CHANGED")
        verify_createddate_utc_kst(
            qid,reference["created_date"],reference["qq_created_date_kst"],result)
    page.get_by_role("tab",name="Details",exact=True).click(timeout=10000)
    info=page.locator("body").inner_text(timeout=15000)
    lines=[s.strip() for s in info.splitlines() if s.strip()]
    if next_field(lines,"Currency")!="KRW":raise ValueError("NOT_NATIVE_KRW")
    if next_field(lines,"Active")!="True":raise ValueError("NOT_ACTIVE")
    if next_field(lines,"Quotation ID")!=reference["amea_id"]:raise ValueError("AMEA_ID_MISMATCH")
    hrefs=page.locator("a[href]").evaluate_all("nodes=>nodes.map(n=>n.getAttribute('href')||'')")
    account=native_lookup(hrefs,"Account")
    contact=native_lookup(hrefs,"Contact")
    quoted=money_after(info,"Total Price")
    total_with_tax=money_after(info,"Grand Total")
    require_original_krw_totals(next_field(lines,"Currency"),
                                next_field(lines,"Active"),
                                quoted,total_with_tax,
                                next_field(lines,"GST/VAT (%)"))
    page.get_by_role("tab",name="Quotation Detail",exact=True).click(timeout=10000)
    table=page.locator("table").filter(has_text="Process Name").first
    table.wait_for(timeout=12000)
    page.wait_for_function("""() => Array.from(document.querySelectorAll("table tr")).some(
        r => /^[0-9]+$/.test((r.querySelector("th,td")?.textContent||"").trim()))""",timeout=15000)
    body=page.locator("body").inner_text()
    matches=re.findall(r"([^\n]{2,100})\(([A-Z]{2,8}\d{4,})\)",body)
    if not matches:raise ValueError("PRODUCT_CODE_NOT_VISIBLE")
    product_name,product_code=matches[0]
    rows=[]
    for tr in table.locator("tr").all():
        v=[x.strip() for x in tr.locator("th,td").all_inner_texts()]
        if len(v)<9 or not v[0].isdigit():continue
        seq,pack,name,process_type,sample_qty,size,unit,rate,total=v[:9]
        if name not in process_ids:raise ValueError("PROCESS_NOT_IN_VERIFIED_REPORT")
        qty=amount(sample_qty)
        if qty<=0 or qty!=int(qty):raise ValueError("SAMPLE_QTY_INVALID")
        rate_decimal=amount(rate);subtotal=amount(total)
        if abs(rate_decimal*qty-subtotal)>Decimal("0.05"):
            raise ValueError("PROCESS_QUANTITY_TOTAL_MISMATCH")
        rows.append(dict(process_name=name,process_type=process_type,pack=pack,
                         process_id=process_ids[name],sample_quantity=int(qty),
                         unit_price_krw=str(rate_decimal),line_total_krw=str(subtotal),
                         data_unit=unit if unit else "NA",data_size=size))
    if not rows or sum(Decimal(r["line_total_krw"]) for r in rows)!=quoted:
        raise ValueError("QUOTE_PROCESS_SUM_MISMATCH")
    template={"product_code":product_code,"process_ids":[r["process_id"] for r in rows],
              "process_types":[r["process_type"] for r in rows]}
    signature=hashlib.sha256(json.dumps(template,ensure_ascii=False,
                         sort_keys=True,separators=(",",":")).encode()).hexdigest()
    records=[]
    for r in rows:
        records.append(dict(source_kind="VERIFIED_SFDC_KRW_PROCESS_PRICE",
            source_verified=True,created_date=reference["created_date"],quote_id=qid,
            active=True,approval_status="APPROVED",currency="KRW",
            was_usd_converted=False,vat_basis="VAT_EXCLUDED",
            account_id=account,contact_id=contact,process_id=r["process_id"],
            product_signature=signature,unit_price_krw=r["unit_price_krw"],
            data_unit=r["data_unit"],data_size=r["data_size"],
            sample_quantity=r["sample_quantity"],process_name=r["process_name"],
            product_name=product_name.strip()[:100],
            **({"source_date_resolution":"NATIVE_UTC_TO_ASIA_SEOUL_EXACT",
                "native_created_at_utc":reference["native_created_at_utc"],
                "qq_created_date_kst":reference["qq_created_date_kst"]}
               if resolution else {})))
    return records
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    a=parser.parse_args()
    manifest=json.loads(a.manifest.read_text(encoding="utf-8"))
    if not isinstance(manifest.get("quotes"),list) or len(manifest["quotes"]) not in range(1,21):
        raise ValueError("MANIFEST_INVALID")
    records=[];holds=[]
    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page=browser.contexts[0].new_page()
        try:
            for q in manifest["quotes"]:
                try:records+=extract(page,q)
                except Exception as ex:holds.append({"reason":str(ex)[:75]})
        finally:page.close();browser.close()
    if records:
        result={"version":"sfdc-2026-krw-process-prices-v1",
                "source":"SFDC_AUTHENTICATED_READ_ONLY_KRW_PROCESS_LINES",
                "generated_at":datetime.now(timezone.utc).isoformat(),
                "salesforce_write_performed":False,"records":records}
        a.output.parent.mkdir(parents=True,exist_ok=True)
        tmp=a.output.with_suffix(".partial")
        tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        tmp.replace(a.output)
    print(json.dumps({"status":"PASS" if records else "HOLD",
                      "quotes_in_manifest":len(manifest["quotes"]),
                      "process_rows":len(records),"held_quotes":len(holds),
                      "hold_reasons":[x["reason"] for x in holds],
                      "crm_writes":0},ensure_ascii=False))
if __name__=="__main__":main()