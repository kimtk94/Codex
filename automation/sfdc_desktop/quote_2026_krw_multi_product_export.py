"""Native-KRW multi-Product quote browser readback. PRIVATE manifest, No-Save.

Each Salesforce Product article owns its Process table and Product code.
Verify QQ report process multiset, native 001/003 identity, active+approved,
line totals and quote VAT totals before indexing each Product independently.
Never publish customer data/prices to GitHub, logs or Action artifacts.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import hashlib, json, re
from playwright.sync_api import sync_playwright
from quote_2026_krw_browser_export import (
    SFDC, ID_RX, QID_RX, PROCESS_RX, amount, next_field,
    money_after, native_lookup,
)

CODE_RX = re.compile(r"^(.{3,120})\(([A-Z]{2,8}[0-9]{4,})\)$")
DAY_RX = re.compile(r"^2026-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$")


def normalize_size(v):
    s = str(v or "").strip()
    if not s:
        return ""
    try:
        n = Decimal(s.replace(",", ""))
        if not n.is_finite() or n < 0:
            raise ValueError
        return str(n.normalize())
    except Exception as e:
        raise ValueError("INVALID_DATA_SIZE") from e


def normalize_qty(v):
    n = amount(v)
    if n <= 0 or n != int(n):
        raise ValueError("INVALID_SAMPLE_QUANTITY")
    return int(n)


def row_key(process, qty, data_size, data_unit):
    return (
        str(process or "").strip(), normalize_qty(qty), normalize_size(data_size),
        str(data_unit or "NA").strip() or "NA",
    )


def verify_multiset(expected, actual):
    """Require exact source row counts, product count and process row multiset."""
    if not isinstance(expected, list) or not expected or not isinstance(actual, list):
        raise ValueError("SOURCE_PROCESS_LINES_MISSING")
    source_keys = Counter()
    for item in expected:
        if not isinstance(item, dict):
            raise ValueError("SOURCE_PROCESS_LINE_INVALID")
        if not re.fullmatch(r"QD-[0-9]{3,}",str(item.get("quotation_product_id",""))):
            raise ValueError("SOURCE_QUOTE_PRODUCT_ID_UNVERIFIED")
        if not PROCESS_RX.fullmatch(str(item.get("process_id") or "")):
            raise ValueError("SOURCE_PROCESS_ID_UNVERIFIED")
        k = row_key(item.get("process_name"), item.get("sample_quantity"),
                    item.get("data_size"), item.get("data_unit"))
        source_keys[(k,item["process_id"])] += 1
    actual_keys = Counter((row_key(x["process_name"],x["sample_quantity"],
                         x["data_size"],x["data_unit"]),x["process_id"])
                          for x in actual)
    if actual_keys != source_keys:
        raise ValueError("SOURCE_PROCESS_MULTISET_MISMATCH")
    return True



def verify_product_partitions(expected, actual_product_rows):
    """Verify QD product boundaries, not just the all-Quote process multiset.

    Salesforce renders Product articles with product codes, whereas the QQ
    report records opaque QD product IDs. A bijection of Product-level
    process multisets is required; a match in aggregate alone is insufficient.
    """
    if not isinstance(expected, list) or not expected:
        raise ValueError("SOURCE_PRODUCT_PARTITIONS_MISSING")
    if not isinstance(actual_product_rows, list) or not actual_product_rows:
        raise ValueError("PRODUCT_ARTICLES_MISSING")
    source = defaultdict(Counter)
    for r in expected:
        qd = str(r.get("quotation_product_id") or "")
        pid = str(r.get("process_id") or "")
        if not re.fullmatch(r"QD-[0-9]{3,}", qd) or not PROCESS_RX.fullmatch(pid):
            raise ValueError("SOURCE_PRODUCT_PARTITION_ID_UNVERIFIED")
        key = (row_key(r.get("process_name"), r.get("sample_quantity"),
                       r.get("data_size"), r.get("data_unit")), pid)
        source[qd][key] += 1
    def partition_signature(rows):
        """Canonical identity of a process multiset, preserving duplicates."""
        return tuple(sorted((key, count) for key, count in rows.items()))
    actual = []
    for rows in actual_product_rows:
        if not isinstance(rows, list) or not rows:
            raise ValueError("EMPTY_PRODUCT_ARTICLE")
        counter = Counter()
        for r in rows:
            pid = str(r.get("process_id") or "")
            if not PROCESS_RX.fullmatch(pid):
                raise ValueError("ARTICLE_PROCESS_ID_UNVERIFIED")
            key = (row_key(r.get("process_name"), r.get("sample_quantity"),
                           r.get("data_size"), r.get("data_unit")), pid)
            counter[key] += 1
        actual.append(partition_signature(counter))
    expected_signatures = Counter(partition_signature(x) for x in source.values())
    actual_signatures = Counter(actual)
    if actual_signatures != expected_signatures:
        raise ValueError("SOURCE_PRODUCT_PARTITION_MISMATCH")
    return True

def product_fingerprint(product_code, rows):
    if not re.fullmatch(r"[A-Z]{2,8}[0-9]{4,}", product_code) or not rows:
        raise ValueError("PRODUCT_CODE_INVALID")
    payload={"product_code":product_code,
             "process_ids":[r["process_id"] for r in rows],
             "process_types":[r["process_type"] for r in rows]}
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,
                                     separators=(",",":")).encode()).hexdigest()


def extract_multi(page, reference):
    if not isinstance(reference,dict):
        raise ValueError("MANIFEST_ENTRY_INVALID")
    qid=reference.get("quote_id")
    record=reference.get("record_id")
    date=reference.get("created_date")
    if not isinstance(qid,str) or not QID_RX.fullmatch(qid) or not isinstance(record,str) or not ID_RX.fullmatch(record):
        raise ValueError("REFERENCE_ID_UNVERIFIED")
    if reference.get("approval_evidence")!="APPROVED_TEXT" or not DAY_RX.fullmatch(str(date or "")):
        raise ValueError("APPROVAL_DATE_UNVERIFIED")
    if not qid.startswith("QID-"+date+"-"):
        raise ValueError("QUOTE_DATE_MISMATCH")
    expected=reference.get("expected_process_lines")
    if not isinstance(expected,list) or len(expected)<2 or len(expected)>80:
        raise ValueError("EXPECTED_PROCESS_ROWS_INVALID")
    expected_products={x["quotation_product_id"] for x in expected if isinstance(x,dict) and x.get("quotation_product_id")}
    if len(expected_products)<2 or len(expected_products)>8:
        raise ValueError("NOT_MULTIPLE_PRODUCTS")
    process_id_by_name={}
    for x in expected:
        key=x["process_name"]
        pid=x["process_id"]
        if not PROCESS_RX.fullmatch(pid) or (key in process_id_by_name and process_id_by_name[key]!=pid):
            raise ValueError("AMBIGUOUS_PROCESS_NAME_ID")
        process_id_by_name[key]=pid

    page.goto(SFDC+"/lightning/r/Quotation__c/"+record+"/view",
              wait_until="domcontentloaded",timeout=30000)
    page.wait_for_function("qid=>document.title.includes(qid)",arg=qid,timeout=18000)
    page.get_by_role("tab",name="Details",exact=True).click(timeout=10000)
    details=page.locator("body").inner_text(timeout=12000)
    lines=[v.strip() for v in details.splitlines() if v.strip()]
    if next_field(lines,"Currency")!="KRW":
        raise ValueError("NON_KRW_QUOTE")
    if next_field(lines,"Active")!="True":
        raise ValueError("INACTIVE_QUOTE")
    if next_field(lines,"Quotation ID")!=reference.get("amea_id"):
        raise ValueError("AMEA_ID_MISMATCH")
    hrefs=page.locator("a[href]").evaluate_all("nodes=>nodes.map(n=>n.getAttribute('href')||'')")
    account=native_lookup(hrefs,"Account")
    contact=native_lookup(hrefs,"Contact")
    subtotal=money_after(details,"Total Price")
    grand=money_after(details,"Grand Total")
    if subtotal<=0 or abs(grand-subtotal*Decimal("1.10"))>Decimal("0.05"):
        raise ValueError("QUOTE_VAT_TOTAL_MISMATCH")
    page.get_by_role("tab",name="Quotation Detail",exact=True).click(timeout=10000)
    page.wait_for_function("""n=>document.querySelectorAll('article.slds-card').length>=n""",
                           arg=len(expected_products),timeout=15000)
    tables=page.locator("article.slds-card").filter(has=page.locator("table").filter(has_text="Process Name"))
    if tables.count()!=len(expected_products):
        raise ValueError("PRODUCT_TABLE_COUNT_MISMATCH")
    all_rows=[]
    product_codes=set()
    product_groups=[]
    for i in range(tables.count()):
        article=tables.nth(i)
        label=article.inner_text(timeout=15000).splitlines()[0].strip()
        matched=CODE_RX.fullmatch(label)
        if not matched:
            raise ValueError("PRODUCT_CODE_NOT_VISIBLE")
        pname,pcode=matched.groups()
        if pcode in product_codes:
            raise ValueError("DUPLICATE_PRODUCT_CODE")
        product_codes.add(pcode)
        table=article.locator("table").filter(has_text="Process Name").first
        rows=[]
        for tr in table.locator("tr").all():
            cols=[c.strip() for c in tr.locator("th,td").all_inner_texts()]
            if len(cols)<9 or not cols[0].isdigit():continue
            _,pack,name,process_type,qty,size,unit,rate,total=cols[:9]
            if name not in process_id_by_name:
                raise ValueError("PROCESS_NAME_NOT_IN_REPORT")
            n=normalize_qty(qty)
            if abs(amount(rate)*Decimal(n)-amount(total))>Decimal("0.05"):
                raise ValueError("LINE_QTY_PRICE_MISMATCH")
            rows.append({"pack":pack,"process_name":name,
                         "process_type":process_type,
                         "process_id":process_id_by_name[name],
                         "sample_quantity":n,
                         "data_size":size,
                         "data_unit":unit.strip() or "NA",
                         "unit_price_krw":str(amount(rate)),
                         "line_total_krw":str(amount(total))})
        if not rows:
            raise ValueError("EMPTY_PRODUCT_PROCESS_TABLE")
        product_groups.append((pname,pcode,rows))
        all_rows.extend(rows)
    verify_multiset(expected,all_rows)
    verify_product_partitions(expected,[rows for _,_,rows in product_groups])
    if sum(Decimal(x["line_total_krw"]) for x in all_rows)!=subtotal:
        raise ValueError("QUOTE_PROCESS_SUM_MISMATCH")
    output=[]
    for pname,pcode,rows in product_groups:
        signature=product_fingerprint(pcode,rows)
        for line in rows:
            output.append({
                "source_kind":"VERIFIED_SFDC_KRW_PROCESS_PRICE",
                "source_verified":True,"created_date":date,"quote_id":qid,
                "active":True,"approval_status":"APPROVED",
                "currency":"KRW","was_usd_converted":False,"vat_basis":"VAT_EXCLUDED",
                "account_id":account,"contact_id":contact,
                "process_id":line["process_id"],
                "product_signature":signature,
                "unit_price_krw":line["unit_price_krw"],
                "data_unit":line["data_unit"],
                "data_size":line["data_size"],
                "sample_quantity":line["sample_quantity"],
                "process_name":line["process_name"],
                "product_name":pname.strip()[:100]
            })
    return output


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    manifest=json.loads(args.manifest.read_text(encoding="utf-8"))
    refs=manifest.get("quotes")
    if not isinstance(refs,list) or not 1<=len(refs)<=10:
        raise ValueError("INVALID_PRIVATE_MANIFEST")
    records=[];holds=[]
    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page=browser.contexts[0].new_page()
        try:
            for ref in refs:
                try:
                    records+=extract_multi(page,ref)
                except Exception as err:
                    holds.append(type(err).__name__+":"+str(err)[:80])
        finally:
            page.close()
            browser.close()
    if records:
        result={
            "version":"sfdc-2026-krw-process-prices-v1",
            "source":"SFDC_AUTHENTICATED_READ_ONLY_KRW_PROCESS_LINES",
            "generated_at":datetime.now(timezone.utc).isoformat(),
            "salesforce_write_performed":False,
            "records":records,
        }
        args.output.parent.mkdir(parents=True,exist_ok=True)
        temp=args.output.with_suffix(".partial")
        temp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        temp.replace(args.output)
    print(json.dumps({"status":"PASS" if records else "HOLD",
                      "quotes_requested":len(refs),
                      "quotes_passed":len({r["quote_id"] for r in records}),
                      "process_rows":len(records),
                      "held_count":len(holds),
                      "hold_reasons":holds,
                      "crm_writes":0},ensure_ascii=False))


if __name__=="__main__":
    main()
