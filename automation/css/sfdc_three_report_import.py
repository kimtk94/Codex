#!/usr/bin/env python3
"""Validate and normalize three SFDC HTML-table .xls email attachments.

Offline pilot. No Salesforce writes, emails, billing changes or Google Sheet mutations.
Usage: python automation/css/sfdc_three_report_import.py --leads Leads.xls --opportunities Opportunities.xls --quotation Quotation.xls --outdir outputs/sfdc-pilot
"""
import argparse
import csv
import json
from pathlib import Path
from html.parser import HTMLParser

class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows=[]; self.row=None; self.cell=None; self.in_table=False
    def handle_starttag(self,tag,attrs):
        if tag=="table": self.in_table=True
        if not self.in_table: return
        if tag=="tr": self.row=[]
        if tag in ("td","th") and self.row is not None: self.cell=[]
    def handle_data(self,data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ("td","th") and self.cell is not None:
            self.row.append("".join(self.cell).strip()); self.cell=None
        elif tag=="tr" and self.row is not None:
            if self.row: self.rows.append(self.row)
            self.row=None
        elif tag=="table": self.in_table=False

def read_report(path):
    raw=Path(path).read_bytes()
    if raw[:4]==bytes.fromhex("d0cf11e0") or raw[:2]==b"PK":
        raise ValueError("Native binary Excel detected: export as SFDC HTML .xls, not binary workbook")
    parser=Tables()
    parser.feed(raw.decode("utf-8-sig",errors="replace"))
    if len(parser.rows)<2: raise ValueError("No data table found: "+str(path))
    header=parser.rows[0]
    if len(header)!=len(set(header)):
        raise ValueError("Duplicate column header: "+str(path))
    return [dict(zip(header, row+[""]*max(0,len(header)-len(row)))) for row in parser.rows[1:]]

def unique(rows,key):
    d={}
    for row in rows:
        k=row.get(key,"").strip()
        if not k: raise ValueError("Missing "+key)
        if k in d and d[k]!=row: raise ValueError("Conflicting duplicate "+key+": "+k)
        d[k]=row
    return d

def output_csv(path, rows, columns):
    with open(path,"w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=columns,extrasaction="ignore");w.writeheader();w.writerows(rows)

def main():
    p=argparse.ArgumentParser()
    for name in ("leads","opportunities","quotation"): p.add_argument("--"+name,required=True)
    p.add_argument("--outdir",required=True)
    a=p.parse_args()
    leads=read_report(a.leads)
    opps=read_report(a.opportunities)
    quotes=read_report(a.quotation)
    required={
        "Leads":("SFDC Lead ID","Lead ID","Opportunity ID.1"),
        "Opportunities":("Opportunity ID","Lead Converted ID","Stage"),
        "Quotation":("SFDC Quotation ID","Quotation Product ID","Opportunity ID","Quote Process Name","Sample Quantity","Data Size"),
    }
    for label, rows in (("Leads",leads),("Opportunities",opps),("Quotation",quotes)):
        if not rows: raise ValueError(label+" empty")
        missing=set(required[label])-set(rows[0])
        if missing: raise ValueError(label+" missing columns: "+", ".join(sorted(missing)))
    leads_by_id=unique(leads,"SFDC Lead ID")
    opps_by_id=unique(opps,"Opportunity ID")
    # One quote has many products; one product has many process rows.
    dedup={}
    conflicts=0
    for r in quotes:
        key=(r["SFDC Quotation ID"],r["Quotation Product ID"],r["Quote Process Name"],r.get("Process Name: SFDC Process ID",""))
        if key in dedup and dedup[key]!=r: conflicts+=1
        else: dedup[key]=r
    # Keep one row per quote/product for sample count and monetary validation.
    products={}
    money_conflicts=[]
    for r in dedup.values():
        key=(r["SFDC Quotation ID"],r["Quotation Product ID"])
        if key in products:
            prev=products[key]
            for col in ("Total Price USD (converted)","Sales Price USD (converted)","Sample Quantity","Data Size"):
                if prev.get(col,"")!=r.get(col,"") and prev.get(col,"") and r.get(col,""):
                    money_conflicts.append({"quote":key[0],"product":key[1],"field":col})
        else: products[key]=r
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    output_csv(out/"leads.csv",list(leads_by_id.values()),list(leads[0]))
    output_csv(out/"opportunities.csv",list(opps_by_id.values()),list(opps[0]))
    output_csv(out/"quotation_process.csv",list(dedup.values()),list(quotes[0]))
    output_csv(out/"quotation_products.csv",list(products.values()),list(quotes[0]))
    audit={
        "source":"SFDC report email pilot",
        "timezone":"Asia/Seoul",
        "expected_receipt_times":["08:00","12:00","17:00"],
        "lead_rows":len(leads),
        "opportunity_rows":len(opps),
        "quotation_raw_rows":len(quotes),
        "quotation_process_rows":len(dedup),
        "quotation_product_rows":len(products),
        "quotation_ids":len({r["SFDC Quotation ID"] for r in quotes}),
        "quote_process_duplicate_rows":len(quotes)-len(dedup),
        "quote_process_conflicting_duplicate_rows":conflicts,
        "quote_product_conflicts":money_conflicts[:100],
        "quote_product_conflict_count":len(money_conflicts),
        "quote_rows_with_known_opportunity":sum(r["Opportunity ID"] in opps_by_id for r in quotes),
        "leads_with_converted_id_match":sum(r["Lead ID"] in {o["Lead Converted ID"] for o in opps} for r in leads),
        "invoice_authority":"Tax Invoice only; do not recognize quote as revenue",
        "status":"REVIEW" if conflicts or money_conflicts else "READY"
    }
    (out/"audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(audit,ensure_ascii=False,indent=2))
    if audit["status"]!="READY": raise SystemExit(2)

if __name__=="__main__": main()
