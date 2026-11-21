#!/usr/bin/env python3
"""Single-source Lead contact eligibility: 1 calendar year from Lead creation.

A Lead created on the same calendar day one year ago is still eligible.
Older Leads remain in the source and historical sent-mail audit; they are
excluded only from active outreach/recontact queues and filtered views.
No writes, network calls, or external dependencies.
"""
import datetime as dt

KST = dt.timezone(dt.timedelta(hours=9))
ELIGIBILITY_FIELD = "Lead 연락 대상 (자동)"
LABELS = {"eligible": "대상 (최근 1년)", "expired": "제외 (1년 초과)"}

def today_kst():
    return dt.datetime.now(KST).date()

def cutoff_date(today=None):
    today = today or today_kst()
    try:
        return today.replace(year=today.year - 1)
    except ValueError:
        # Leap day: use Feb 28 in the previous non-leap year.
        return today.replace(year=today.year - 1, month=2, day=28)

def parse_created(raw):
    if not isinstance(raw, (str, dt.date)):
        raise RuntimeError("LEAD_CREATED_DATE_MISSING")
    if isinstance(raw, dt.datetime):
        return raw.astimezone(KST).date() if raw.tzinfo else raw.date()
    if isinstance(raw, dt.date):
        return raw
    value = raw.strip()
    if not value:
        raise RuntimeError("LEAD_CREATED_DATE_MISSING")
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        raise RuntimeError("LEAD_CREATED_DATE_INVALID") from None

def eligibility(row, today=None):
    today = today or today_kst()
    created = parse_created(row.get("Lead Created"))
    if created > today:
        raise RuntimeError("LEAD_CREATED_DATE_IN_FUTURE")
    return "expired" if created < cutoff_date(today) else "eligible"

def label(row, today=None):
    return LABELS[eligibility(row, today)]

def stats(rows, today=None):
    today = today or today_kst()
    count = {"eligible": 0, "expired": 0}
    for row in rows:
        count[eligibility(row, today)] += 1
    return {"cutoff": cutoff_date(today).isoformat(),
            "inclusive": True, "counts": count}

