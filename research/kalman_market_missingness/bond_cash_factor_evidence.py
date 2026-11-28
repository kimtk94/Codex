"""Cash-distribution hypothesis check, not issuer or market-price certification.

The evidence below is transcribed from indexed issuer pages on 2026-11-28.
Original HTML fetch failed; rows are deliberately SEARCH_INDEX_ONLY. No raw
price values, cash corrections, or prospective research admissions are emitted.
"""
from __future__ import annotations

from decimal import Decimal
import math

import exchange_calendars as xc
import pandas as pd
import numpy as np

from backfill_queue import frame_dates

SOURCES = {
    "yf_hyg": "https://www.ishares.com/us/products/239565/ishares-iboxx-high-yield-corporate-bond-etf-hyg",
    "yf_lqd": "https://www.ishares.com/us/products/239566/ishares-iboxx-investment-grade-corporate-bond-etf-lqd",
    "yf_tlt": "https://www.ishares.com/us/products/239454/ishares-1020-year-treasury-bond-etf",
}
CASH_USD = {
    "yf_hyg": ("0.435025", "0.341639", "0.401391"),
    "yf_lqd": ("0.443669", "0.438660", "0.399950"),
    "yf_tlt": ("0.314686", "0.311581", "0.343177"),
}
EX_PAY = (("2026-09-01", "2026-09-04"),
          ("2026-10-01", "2026-10-06"),
          ("2026-11-02", "2026-11-05"))
TOL_BP = 0.1


def compare_cash_event(old_close, adjusted_before, old_ex_close, adjusted_ex, amount):
    """A single cash event predicts F_ex/F_prev=1/(1-D/P_prev).

    Both prices must use comparable share units and consecutive sessions.
    This is a diagnostic hypothesis; other revisions can mimic or mask it.
    """
    try:
        p, a, q, b, cash = map(float, (old_close, adjusted_before, old_ex_close,
                                      adjusted_ex, amount))
    except (ValueError, TypeError, OverflowError):
        return {"status": "INVALID_PRICE_INPUT_HOLD"}
    if not all(math.isfinite(x) and x > 0 for x in (p,a,q,b,cash)) or cash >= p:
        return {"status": "INVALID_PRICE_INPUT_HOLD"}
    predicted = 1 / (1-cash/p)
    observed = (b/q)/(a/p)
    if not math.isfinite(observed) or observed <= 0:
        return {"status": "INVALID_PRICE_INPUT_HOLD"}
    residual = (observed / predicted - 1)*10000
    return {
        "status": "CASH_FACTOR_PATTERN_CONSISTENT_UNCERTIFIED_HOLD" if abs(residual)<=TOL_BP
                  else "CASH_FACTOR_PATTERN_MISMATCH_HOLD",
        "predicted_step_bp": round((predicted-1)*10000,6),
        "observed_step_bp": round((observed-1)*10000,6),
        "residual_bp": round(residual,6),
    }


def audit_cash_events(old, new, key, reference_asof):
    if key not in CASH_USD:
        return []
    views = []
    for frame in (old,new):
        d = frame_dates(frame,key)
        flags = frame["is_adjusted"]
        if flags.isna().any() or not all(isinstance(v,(bool,np.bool_)) for v in flags):
            raise ValueError("CASH_BASIS_FLAG_INVALID")
        v = frame.copy()
        v.index = d.tolist()
        views.append(v)
    raw, adj = views
    calendar = xc.get_calendar("XNYS")
    result = []
    for (ex,pay), amount in zip(EX_PAY,CASH_USD[key]):
        previous = str(calendar.previous_session(pd.Timestamp(ex)).date())
        row = {"asset":key, "ex_date":ex, "pay_date":pay,
               "distribution_usd_per_share":amount, "source_url":SOURCES[key],
               "evidence_grade":"ISSUER_PAGE_SEARCH_INDEX_ONLY",
               "issuer_body_sha256":None, "issuer_amount_certified":False,
               "share_unit_certified":False, "factor_certified":False,
               "pit_approved":False, "approved_backfill_rows":0,
               "previous_session":previous}
        if ex > reference_asof:
            row["status"]="AFTER_REFERENCE_ASOF_HOLD"
        elif bool(raw["is_adjusted"].iloc[0]) or not bool(adj["is_adjusted"].iloc[0]):
            row["status"]="PRICE_BASIS_UNSUITABLE_HOLD"
        elif ex > max(raw.index):
            row["status"]="AFTER_SOURCE_COVERAGE_NO_PAIRED_FACTOR_HOLD"
        elif not {previous,ex}.issubset(raw.index) or not {previous,ex}.issubset(adj.index):
            row["status"]="CONSECUTIVE_PAIR_MISSING_HOLD"
        else:
            row.update(compare_cash_event(raw.at[previous,"close"],adj.at[previous,"close"],
                                          raw.at[ex,"close"],adj.at[ex,"close"],Decimal(amount)))
        result.append(row)
    return result
