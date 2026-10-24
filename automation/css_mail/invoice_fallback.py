"""Conservative invoice evidence join when attachment filename omits H ID.

Never reconstruct invoice values or infer paid status from project identifiers.
Only accept matching invoice + AMEA in filename and *unique* corroboration in
the same email subject, plus an explicit integer KRW amount in the filename.
"""
import re
from decimal import Decimal, InvalidOperation

INV = re.compile(r"(?<!\d)\d{12}(?!\d)")
AMEA = re.compile(r"AMEA\d{8,}(?:-\d{1,3})?", re.I)
H_ID = re.compile(r"H209SC\d{6,}", re.I)
AMOUNT = re.compile(r"KRW\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)(?![0-9.])", re.I)

def corroborated_filename(filename, subject):
    filename = str(filename or "")
    subject = str(subject or "")
    if "TAX INVOICE" not in filename.upper() or not filename.lower().strip().endswith(".pdf"):
        return None
    nums_f=set(INV.findall(filename))
    nums_s=set(INV.findall(subject))
    ameas_f={x.upper() for x in AMEA.findall(filename)}
    ameas_s={x.upper() for x in AMEA.findall(subject)}
    hs={x.upper() for x in H_ID.findall(subject)}
    money=AMOUNT.findall(filename)
    if not (len(nums_f)==len(nums_s)==len(ameas_f)==len(ameas_s)==len(hs)==len(money)==1):
        return None
    if nums_f != nums_s or ameas_f != ameas_s:
        return None
    try:
        value=Decimal(money[0].replace(",",""))
    except InvalidOperation:
        return None
    if value<=0 or value!=value.to_integral_value():
        return None
    invoice=next(iter(nums_f))
    if not invoice.startswith(("209125","209126")):
        return None
    return invoice,next(iter(hs)),"",next(iter(ameas_f)),int(value),"SUBJECT_CORROBORATED_FILENAME"
