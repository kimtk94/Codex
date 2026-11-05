"""2026+ QQ mail classification. Evidence-first; no financial inference."""
import datetime as dt
import re
from email.utils import getaddresses
from zoneinfo import ZoneInfo

VERSION = "2026-v1"
KST = ZoneInfo("Asia/Seoul")
CUTOFF = dt.datetime(2026, 1, 1, tzinfo=KST)
CSS = "css@novogene-amea.com"
REPLY = re.compile(r"^\s*(?:re|fw|fwd|답장|전달|회신)\s*[:：]", re.I)
INVOICE = re.compile(r"^\s*(?:❗️\s*)?Notice:\s*Invoice Issued\s*&\s*Statement Confirmed\b", re.I)
FILENAME = re.compile(r"TAX\s+INVOICE[-_ ]+(\d{8,15})[-_ ]+(H\d{3}SC\d{5,}|H\d{5,})[-_ ]+([A-Za-z0-9]+)[-_ ]+(AMEA\d{7,}(?:-\d{1,3})?)[-_ ]+KRW\s*([0-9]+(?:\.[0-9]{1,2})?)\.pdf", re.I)
PROJECTS = re.compile(r"\b(?:AMEA\d{7,}(?:-\d+)?|X\d+SC\d+(?:-Z\d+)?|H\d{2,}SC\d+)\b", re.I)
STAGES = [
    ("DATA_DELETION_WARNING", "data deletion in 10 days"),
    ("DATA_READY", "data ready to download"),
    ("FINAL_REPORT", "final report"),
    ("BI_ANALYSIS", "bi analysis"),
    ("SEQUENCING", "sequencing"),
    ("LIBRARY_QC", "library qc"),
    ("SAMPLE_QC", "sample qc"),
    ("SAMPLE_RECEIVED", "sample received"),
]
ORDER = ["TAX_INVOICE", "STATEMENT", "SIF", "QUOTE", "PROJECT", "PAYMENT", "LEAD", "SYSTEM_REPORT", "GENERAL"]

def email_set(value):
    return {a.strip().lower() for _, a in getaddresses([str(value or "")]) if a}

def since_2026(value):
    try:
        date = dt.datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return date.tzinfo is not None and date.astimezone(KST) >= CUTOFF
    except (ValueError, TypeError):
        return False

def invoice_filename(filenames):
    matches = []
    for filename in filenames:
        m = FILENAME.search(re.sub(r"\s+", " ", str(filename)))
        if not m:
            continue
        number, h, po, amea, amount = m.groups()
        integer, _, frac = amount.partition(".")
        if frac and int(frac):
            return None, "DECIMAL_REVIEW"
        if int(integer) <= 0:
            return None, "AMOUNT_REVIEW"
        matches.append((number, int(integer), h, po, amea))
    if len(matches) != 1:
        return None, "FILENAME_MISSING_OR_MULTIPLE"
    return matches[0], "FILENAME_PARSED"

def classify(row, filenames=(), inspected=False, user_email=""):
    subject = str(row.get("Subject", "")).strip()
    low = subject.lower()
    body = str(row.get("Body Excerpt", ""))[:1800]
    sender = email_set(row.get("From", ""))
    recipient = email_set(row.get("To", "")) | email_set(row.get("CC", ""))
    direction = row.get("Direction", "")
    reply = bool(REPLY.match(subject) or row.get("In Reply To"))
    types = []
    stage, action, evidence = "UNCLASSIFIED", "REVIEW", "NO_CONFIRMED_RULE"
    finance, sif, invoice, gross = "NONE", "NOT_VERIFIED", "", None
    quality = "NOT_APPLICABLE"
    if low.startswith("report results ("):
        types.append("SYSTEM_REPORT")
        stage, action, evidence = "SFDC_REPORT", "VALIDATE_REPORT", "REPORT_SUBJECT"
    if direction == "INBOUND" and CSS in sender and INVOICE.match(subject):
        types.extend(["TAX_INVOICE", "PROJECT"])
        stage = "INVOICE_REPLY_REVIEW" if reply else "INVOICE_NOTICE_UNVERIFIED"
        action, evidence = "VERIFY_ORIGINAL_PDF", "OFFICIAL_NOTICE"
        if not reply:
            parsed, quality = invoice_filename(filenames)
            if inspected and parsed:
                stage, finance = "INVOICE_VERIFIED", "ACTUAL_INVOICE"
                invoice, gross = parsed[0], parsed[1]
                evidence, action = "ORIGINAL_CSS_PDF_FILENAME", "RECONCILE_INVOICE"
    elif direction == "INBOUND" and CSS in sender and (
        "statement ready for confirmation" in low or "revised statement" in low
    ):
        types.extend(["STATEMENT", "PROJECT"])
        stage = "STATEMENT_REPLY_REVIEW" if reply else "STATEMENT_CONFIRMATION"
        finance = "NONE" if reply else "PENDING_UNPRICED"
        action, evidence = "VERIFY_STATEMENT", "OFFICIAL_STATEMENT_NOTICE"
    if direction == "INBOUND" and CSS in sender and "sif approved" in low:
        types.extend(["SIF", "PROJECT"])
        stage, sif, action, evidence = "SIF_APPROVED", "APPROVED", "UPDATE_PROJECT", "OFFICIAL_SIF_NOTICE"
    elif direction == "INBOUND" and CSS in sender and "sif received" in low:
        types.extend(["SIF", "PROJECT"])
        stage, sif, action, evidence = "SIF_RECEIVED", "RECEIVED", "UPDATE_PROJECT", "OFFICIAL_SIF_NOTICE"
    elif "sif" in low and not types:
        types.extend(["SIF", "PROJECT"])
        stage, sif, action, evidence = "SIF_REQUEST", "REQUEST_ONLY", "CHECK_SIF", "SUBJECT_ONLY"
    if any(p in low for p in ("quotation", "quote")) and not types:
        types.append("QUOTE")
        stage, action, evidence = "QUOTE_NOTICE", "VERIFY_QUOTE", "QUOTE_SUBJECT"
    for milestone, phrase in STAGES:
        if phrase in low:
            types.append("PROJECT")
            if stage == "UNCLASSIFIED":
                stage, action, evidence = milestone, "UPDATE_PROJECT", "PROJECT_SUBJECT"
            break
    if not types and direction == "INBOUND" and any(x in (low + " " + body.lower()) for x in ("견적 문의", "request for quote", "request for sequencing", "pricing inquiry")):
        types.append("LEAD")
        stage, action, evidence = "ENQUIRY", "FOLLOWUP_CANDIDATE", "INBOUND_ENQUIRY"
    if not types:
        types.append("GENERAL")
        stage, action = "GENERAL", "REVIEW"
    tags = sorted(set(types), key=ORDER.index)
    priority = "URGENT" if "DATA_DELETION_WARNING" == stage else "HIGH" if stage in ("SIF_REQUEST", "STATEMENT_CONFIRMATION") else "NORMAL"
    return {
        "Primary Category": tags[0], "Tags": ", ".join(tags), "Milestone": stage,
        "SIF Evidence": sif, "Finance Classification": finance,
        "Invoice Number": invoice, "Tax Invoice Gross KRW": gross,
        "Invoice Validation": quality, "Quote Amount Status": "NOT_VERIFIED",
        "Reply Status": "NOT_APPLICABLE" if direction == "OUTBOUND" else "THREAD_REVIEW_REQUIRED",
        "Priority": priority, "Next Action": action, "Evidence": evidence,
        "Original Mail": "NO" if reply else "YES",
        "Direct Recipient": "YES" if user_email and user_email.lower() in recipient else "NO" if user_email else "UNKNOWN",
        "Ownership": "NOT_VERIFIED",
        "Project Identifiers": ", ".join(sorted(set(x.upper() for x in PROJECTS.findall(subject + " " + body)))),
        "Rule Version": VERSION,
    }
