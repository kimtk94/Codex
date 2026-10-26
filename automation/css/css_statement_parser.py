"""Parse CSS final statements into evidence-only records; never book revenue.

Input: read-only exported mail dictionaries (Subject, Body Text, Mail UID).
Output: statement observations. No spreadsheet writes or credentials.
"""
import re
from decimal import Decimal, InvalidOperation

AMEA = re.compile(r"\bAMEA\d{10}\b", re.I)
CONTRACT = re.compile(r"\bH\d{3}SC\d+\b", re.I)
SUBPROJECT = re.compile(r"\bX\d{3}SC\d+-Z\d+\b", re.I)
SAM = re.compile(r"\bSAM\d{11,}\b", re.I)
PO = re.compile(r"\b(?:SQ-)?AMEA\d{10}\b", re.I)
TOTAL = re.compile(r"Total\s*Amount[\s\S]{0,150}?([\d,]+(?:\.\d{1,2})?)\s*(KRW|USD)", re.I)
ROW = re.compile(r"(?P<qty>\d+(?:\.\d+)?)\s+(?P<unit>\d+(?:\.\d+)?)\s+(?P<amount>\d+(?:\.\d+)?)\s+(?P<currency>KRW|USD)", re.I)


def parse_statement(mail):
    subject = str(mail.get("Subject") or mail.get("subject") or "")
    body = str(mail.get("Body Text") or mail.get("body") or "")
    if "Final Report & Statement Ready For Confirmation" not in subject:
        return None
    text = subject + "\n" + body
    amea = set(x.upper() for x in AMEA.findall(text))
    contracts = set(x.upper() for x in CONTRACT.findall(text))
    subprojects = set(x.upper() for x in SUBPROJECT.findall(text))
    sams = set(x.upper() for x in SAM.findall(text))
    line_items = []
    for hit in ROW.finditer(body):
        try:
            qty, unit, amount = (Decimal(hit.group(k)) for k in ("qty", "unit", "amount"))
        except InvalidOperation:
            continue
        line_items.append({"quantity": str(qty), "unit_price": str(unit),
                           "amount": str(amount), "currency": hit.group("currency").upper(),
                           "arithmetic_verified": qty * unit == amount})
    # Parsing a final amount from loosely formatted HTML is unsafe unless unique.
    total_candidates = {(v, c.upper()) for v, c in TOTAL.findall(body)}
    verified_total = None
    if len(total_candidates) == 1:
        value, currency = next(iter(total_candidates))
        try:
            amount = Decimal(value.replace(",", ""))
            if line_items and all(i["arithmetic_verified"] and i["currency"] == currency for i in line_items):
                if sum(Decimal(i["amount"]) for i in line_items) == amount:
                    verified_total = str(amount)
        except InvalidOperation:
            pass
    return {"mail_uid": str(mail.get("Mail UID") or mail.get("uid") or ""),
            "amea": sorted(amea), "contracts": sorted(contracts),
            "subprojects": sorted(subprojects), "sams": sorted(sams),
            "statement_total": verified_total,
            "statement_currency": next(iter(total_candidates))[1] if verified_total else None,
            "line_items": line_items, "state": "STATEMENT_READY_UNCONFIRMED",
            "invoice_number": None, "revenue_effect": "NONE",
            "attribution": "REVIEW_ONLY"}


def unique_observations(mails):
    """Idempotent by source UID; conflicting duplicate messages require review."""
    observations = {}
    for mail in mails:
        parsed = parse_statement(mail)
        if parsed is None:
            continue
        key = parsed["mail_uid"]
        if not key:
            raise ValueError("Mail UID required for idempotent processing")
        if key in observations and observations[key] != parsed:
            raise ValueError("Conflicting statement with same UID: " + key)
        observations[key] = parsed
    return list(observations.values())
