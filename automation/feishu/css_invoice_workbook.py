"""Read-only loader for CSS Tax Invoices and Quotation Invoice Match XLSX sheets.

Accept local file path only. Uses stdlib zipfile; returns records only to the caller.
Never prints names, identifiers, or monetary values.
"""
import posixpath
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile
from collections import Counter
from pathlib import Path
from invoice_reconciliation import reconcile

NS={"x":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL="{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

def read_sheet(z, path, shared):
    root=ET.fromstring(z.read(path))
    result=[]
    for row in root.findall(".//x:sheetData/x:row",NS):
        cells={}
        for cell in row.findall("x:c",NS):
            col=re.match(r"[A-Z]+",cell.get("r",""))
            if col is None: continue
            raw=cell.find("x:v",NS)
            if raw is None:
                value="".join(t.text or "" for t in cell.findall(".//x:is/x:t",NS))
            else:
                value=raw.text or ""
                if cell.get("t")=="s": value=shared[int(value)]
            cells[col.group()]=value
        result.append(cells)
    if not result:return []
    headers=result[0]
    if len(set(headers.values()))!=len(headers):
        raise ValueError("Duplicate headers")
    if not all(v for v in headers.values()):
        raise ValueError("Empty column header")
    return [{name:row.get(column,"") for column,name in headers.items()} for row in result[1:] if any(row.values())]

def load(path):
    if not Path(path).is_file():raise ValueError("Workbook missing")
    with ZipFile(path) as z:
        book=ET.fromstring(z.read("xl/workbook.xml"))
        rel=ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rels={x.get("Id"):x.get("Target") for x in rel}
        shared=[]
        if "xl/sharedStrings.xml" in z.namelist():
            root=ET.fromstring(z.read("xl/sharedStrings.xml"))
            shared=["".join(t.text or "" for t in si.findall(".//x:t",NS)) for si in root]
        sheets={}
        for sh in book.find("x:sheets",NS):
            if sh.get("name") not in ("CSS Tax Invoices","Quotation Invoice Match"):continue
            target=rels[sh.get(REL)].lstrip("/")
            entry=target if target.startswith("xl/") else posixpath.normpath("xl/"+target)
            if entry not in z.namelist() or not entry.startswith("xl/worksheets/"):raise ValueError("Invalid worksheet path")
            sheets[sh.get("name")]=read_sheet(z,entry,shared)
    if set(sheets)!={"CSS Tax Invoices","Quotation Invoice Match"}:raise ValueError("Required worksheet missing")
    return sheets

def audit(path):
    sheets=load(path)
    invoices=sheets["CSS Tax Invoices"]
    quotes=sheets["Quotation Invoice Match"]
    required={"invoice_number","amount_krw","project_id","institution"}
    if any(not required.issubset(row) for row in invoices):raise ValueError("Missing invoice columns")
    # This run deliberately has NO payment input, so no unpaid or paid inference.
    _,counts=reconcile(invoices,[],quotes)
    status=Counter(q.get("match_type","") or "UNSPECIFIED" for q in quotes)
    return {"INVOICE_COUNT":len(invoices),"QUOTATION_MATCH_ROW_COUNT":len(quotes),
            "UNIQUE_PROJECT_COUNT":len({x["project_id"] for x in invoices if x["project_id"]}),
            "MATCH_TYPE_COUNTS":dict(sorted(status.items())),
            "PAYMENT_INPUT_STATUS":"NOT_CONNECTED",
            "BASE_WRITES":0,"EMAIL_SENDS":0}

if __name__=="__main__":
    import argparse,json
    p=argparse.ArgumentParser()
    p.add_argument("--workbook",required=True)
    args=p.parse_args()
    result=audit(args.workbook)
    # Only aggregate counts are printed; no customer data.
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
