"""Fail-closed Salesforce CreatedDate UTC ↔ QQ Created Date KST reconciliation.

Only resolve an apparent one-day date mismatch when the ORIGINAL authenticated
Salesforce CreatedDate UTC timestamp is available and the QQ report's date
exactly matches its Asia/Seoul calendar date. The QID and approval creation
date must both match the ORIGINAL UTC date; never rewrite or assume a timezone
shift from date difference alone. No Salesforce or I/O access in this module.
"""
from datetime import date,datetime,timedelta,timezone
import re

_QID=re.compile(r"^QID-(2026-\d{2}-\d{2})-[0-9]{4,}$")
_NATIVE_UTC=re.compile(r"^2026-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")
_KST=timezone(timedelta(hours=9))


def verify_createddate_utc_kst(quote_id,source_utc_date,qq_kst_date,native_timestamp_utc):
    qid=_QID.fullmatch(str(quote_id or ""))
    if not qid or qid.group(1)!=source_utc_date:
        raise ValueError("QUOTE_QID_SOURCE_DAY_UNVERIFIED")
    try:
        source=date.fromisoformat(source_utc_date)
        qq=date.fromisoformat(qq_kst_date)
    except (ValueError,TypeError):
        raise ValueError("CREATED_DATE_NOT_ISO") from None
    if source.year!=2026 or not _NATIVE_UTC.fullmatch(str(native_timestamp_utc or "")):
        raise ValueError("NATIVE_UTC_TIMESTAMP_MISSING_OR_INVALID")
    try:
        utc=datetime.fromisoformat(native_timestamp_utc.replace("Z","+00:00"))
    except ValueError:
        raise ValueError("NATIVE_UTC_TIMESTAMP_INVALID") from None
    if utc.utcoffset()!=timedelta(0) or utc.date()!=source:
        raise ValueError("NATIVE_CREATED_DATE_DOES_NOT_MATCH_QID")
    if (utc+timedelta(hours=9)).date()!=qq:
        raise ValueError("QQ_CREATED_DATE_NOT_KST_RECONCILED")
    if (qq-source).days!=1:
        raise ValueError("NOT_A_ONE_DAY_UTC_KST_MISMATCH")
    return {
        "status":"PASS_NATIVE_CREATED_DATE_UTC_KST",
        "source_utc_date":source_utc_date,
        "qq_kst_date":qq_kst_date,
        "native_created_timestamp_utc":native_timestamp_utc,
        "crm_writes":0,
        "price_auto_apply":False,
    }
