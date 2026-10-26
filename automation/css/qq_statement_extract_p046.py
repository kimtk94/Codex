#!/usr/bin/env python3
"""P0-46: fail-closed QQ Statement extraction. No spreadsheet or revenue writes."""
from __future__ import annotations
import argparse
import csv
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

AMEA_RE = re.compile(r"\bAMEA\d{10}\b", re.I)
H_RE = re.compile(r"\bH\d{3}SC\d+\b", re.I)
X_RE = re.compile(r"\bX\d{3}SC\d+(?:-Z\d+)\b", re.I)
F_RE = re.compile(r"\b[JF]\d{3}\b", re.I)
SAM_RE = re.compile(r"\bSAM\d+\b", re.I)
INVOICE_RE = re.compile(r"\b(?:invoice\s*(?:no\.?|number)?\s*[:#]\s*)(\d{8,})\b", re.I)
MONEY_RE = re.compile(r"(?im)^\s*(?:Subtotal Amount|Total Amount)\s*[:|\t ]+\s*([\d,]+(?:\.\d+)?)\s*(?:\|\s*)?(KRW|USD)\b")
LINE_RE = re.compile(r"(?im)^\s*\d+\s*\|[^\n]*?\|\s*([\d,]+(?:\.\d+)?)\s*\|\s*([\d,]+(?:\.\d+)?)\s*\|\s*(KRW|USD)\s*\|?\s*$")

def extract(row: dict) -> dict:
    uid = str(row.get("Mail UID") or row.get("UID") or "").strip()
    subject = str(row.get("Subject") or "")
    body = str(row.get("Body") or row.get("Text Body") or "")
    merged = subject + "\n" + body
    found = lambda pattern: sorted(set(x.upper() for x in pattern.findall(merged)))
    amea, h, x, f, sam = (found(p) for p in (AMEA_RE,H_RE,X_RE,F_RE,SAM_RE))
    out = {"mail_uid":uid,"amea":amea,"h_contract":h,"x_subproject":x,
           "statement_stage":f,"sam":sam,"invoice_numbers":found(INVOICE_RE),
           "amount":None,"currency":None,"state":"QUARANTINED","reason":""}
    if not uid:
        out["reason"]="MISSING_UID"
        return out
    if not body.strip():
        out["reason"]="BODY_NOT_AVAILABLE"
        return out
    if len(amea)!=1 or len(h)!=1 or len(x)!=1:
        out["reason"]="AMBIGUOUS_IDENTIFIERS"
        return out
    amounts=[]
    try:
        for number,currency in MONEY_RE.findall(body):
            amounts.append((Decimal(number.replace(",","")),currency.upper()))
    except InvalidOperation:
        out["reason"]="INVALID_AMOUNT"
        return out
    if not amounts:
        out["reason"]="AMOUNT_NOT_FOUND"
        return out
    if len(set(amounts))!=1:
        out["reason"]="CONFLICTING_TOTALS"
        return out
    amount,currency=amounts[0]
    if amount<=0 or (currency=="KRW" and amount!=amount.to_integral_value()):
        out["reason"]="INVALID_AMOUNT"
        return out
    out.update(amount=str(amount),currency=currency,state="PARSED_UNVERIFIED",reason="NEEDS_BATCH_AND_INVOICE_RECONCILIATION")
    return out

def parse_rows(rows):
    ledger={}
    for row in rows:
        result=extract(row)
        key=result["mail_uid"]
        if not key:
            key="MISSING_UID_"+str(len(ledger))
        if key in ledger:
            if result==ledger[key]:
                continue
            ledger[key]["state"]="QUARANTINED"
            ledger[key]["reason"]="DUPLICATE_UID_CONFLICT"
        else:
            ledger[key]=result
    return list(ledger.values())

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True,help="CSV export containing UID, Subject, Body")
    p.add_argument("--output",required=True,help="JSONL output, local review only")
    args=p.parse_args()
    with Path(args.input).open(encoding="utf-8-sig",newline="") as handle:
        rows=list(csv.DictReader(handle))
    results=parse_rows(rows)
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result,ensure_ascii=False)+"\n")
    print(json.dumps({"input":len(rows),"unique":len(results),
        "quarantined":sum(r["state"]=="QUARANTINED" for r in results),
        "unverified":sum(r["state"]=="PARSED_UNVERIFIED" for r in results),
        "revenue_writes":0},ensure_ascii=False))

if __name__=="__main__":
    main()
