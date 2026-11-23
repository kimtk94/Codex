#!/usr/bin/env python3
"""Read-only, source-pinned QLD/QQQ historical paired-return evidence.

The original CSV is a historical *same-source* price reference. It is NOT an
exchange closing auction, an issuer distribution ledger, an adjustment factor
or a current Daily20 input. Never infer a paid/not-paid dividend from its
residuals and never write prices or old forecasts.
"""
from __future__ import annotations

import argparse
import base64
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path

VERSION = "daily20-qld-qqq-fixed-historical-residual-v1"
DRIVE_ID = "1v9mM0l0-jLpXu81v6wfwJXHK3kSREsL-"
DRIVE_NAME = "QLD_QQQ_daily_alignment.csv"
PINNED_SHA256 = "87744adcc0dc288141ade3087f10ea270b613a4f9fe2fd6d1682aadfb55c8249"
PINNED_BYTES = 425582
PINNED_ROWS = 2432
PINNED_FIRST_DATE = "2017-01-03"
PINNED_LAST_DATE = "2026-09-04"
SOURCE_IDENTITY = "GOOGLE_DRIVE_HISTORICAL_EXPORT_NOT_INDEPENDENT_EXCHANGE_DATA"
TARGETS = (("QQQ", "2018-06-18"), ("QLD", "2023-09-20"))
FIELDS = (
    "date_ny", "open_qld", "high_qld", "low_qld", "close_qld",
    "volume_qld", "quote_volume_qld", "open_qqq", "high_qqq",
    "low_qqq", "close_qqq", "volume_qqq", "quote_volume_qqq",
    "return_1d_qld", "return_1d_qqq",
    "relative_return_qld_minus_2x_qqq",
)
NUMBERS = ("close_qld", "close_qqq", "return_1d_qld", "return_1d_qqq",
           "relative_return_qld_minus_2x_qqq")
AMOUNT_NOT_CERTIFIED = False


def demand(value, code):
    if not value:
        raise ValueError("HISTORIC_CA_ALIGNMENT_" + code)


def finite_decimal(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def checked_csv(blob, *, pinned=True):
    demand(isinstance(blob, bytes) and 0 < len(blob) <= 1_000_000,
           "SOURCE_BYTES_INVALID")
    h = sha256(blob).hexdigest()
    if pinned:
        demand(h == PINNED_SHA256 and len(blob) == PINNED_BYTES,
               "ORIGINAL_DRIVE_EXPORT_SHA256_MISMATCH")
    try:
        text = blob.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("HISTORIC_CA_ALIGNMENT_SOURCE_NOT_UTF8") from exc
    rdr = csv.DictReader(StringIO(text, newline=""))
    demand(tuple(rdr.fieldnames or ()) == FIELDS, "CSV_SCHEMA_CHANGED")
    parsed = []
    last_date = None
    for row in rdr:
        demand(row.get(None) is None, "CSV_MALFORMED_EXTRA_FIELDS")
        d = row["date_ny"]
        try:
            valid = date.fromisoformat(d)
        except (ValueError, TypeError):
            raise ValueError("HISTORIC_CA_ALIGNMENT_INVALID_DATE")
        demand(d == valid.isoformat() and
               (last_date is None or d > last_date),
               "CSV_UNSORTED_OR_DUPLICATE_DATE")
        nums = {key: finite_decimal(row[key]) for key in NUMBERS}
        demand(all(nums[k] is not None for k in ("close_qld", "close_qqq")),
               "CSV_CLOSE_MISSING")
        demand(all(nums[k] > 0 for k in ("close_qld", "close_qqq")),
               "CSV_CLOSE_NONPOSITIVE")
        if parsed:
            demand(all(nums[k] is not None for k in NUMBERS),
                   "CSV_RETURN_MISSING")
            for sym in ("qld", "qqq"):
                inferred = nums["close_" + sym] / parsed[-1]["close_" + sym] - 1
                demand(abs(inferred - nums["return_1d_" + sym]) <= Decimal("1e-9"),
                       "CSV_RETURN_DOES_NOT_RECONCILE_CLOSE")
            resid = nums["return_1d_qld"] - 2 * nums["return_1d_qqq"]
            demand(abs(resid - nums["relative_return_qld_minus_2x_qqq"])
                   <= Decimal("1e-9"),
                   "CSV_RESIDUAL_DOES_NOT_RECONCILE")
        else:
            demand(all(row[k] in ("", None) for k in
                       ("return_1d_qld", "return_1d_qqq",
                        "relative_return_qld_minus_2x_qqq")),
                   "FIRST_ROW_RETURNS_MUST_BE_EMPTY")
        parsed.append({"date": d, **nums})
        last_date = d
    if pinned:
        demand(len(parsed) == PINNED_ROWS and
               parsed[0]["date"] == PINNED_FIRST_DATE and
               parsed[-1]["date"] == PINNED_LAST_DATE,
               "PINNED_COVERAGE_CHANGED")
    demand(len(parsed) > 260, "INSUFFICIENT_HISTORICAL_ROWS")
    return parsed, h


def evaluate(blob, *, pinned=True):
    rows, file_sha = checked_csv(blob, pinned=pinned)
    dates = {row["date"]: i for i, row in enumerate(rows)}
    result = []
    for symbol, target_day in TARGETS:
        demand(target_day in dates, "HISTORIC_EVENT_DATE_MISSING")
        i = dates[target_day]
        demand(i >= 252, "INSUFFICIENT_PRIOR_252_SESSIONS")
        day = rows[i]
        residual = day["relative_return_qld_minus_2x_qqq"]
        historic = [
            abs(rows[j]["relative_return_qld_minus_2x_qqq"])
            for j in range(i-252, i)
        ]
        demand(all(r is not None for r in historic),
               "HISTORIC_RESIDUAL_MISSING")
        rank = sum(r <= abs(residual) for r in historic)
        event = {
            "symbol_with_issuer_exception": symbol,
            "event_ex_date": target_day,
            "research_price_observation_not_dividend": True,
            "source_row_index": i,
            "qld_price_on_day": str(day["close_qld"]),
            "qqq_price_on_day": str(day["close_qqq"]),
            "qld_close_to_close_return": str(day["return_1d_qld"]),
            "qqq_close_to_close_return": str(day["return_1d_qqq"]),
            "qld_minus_2x_qqq_residual": str(residual),
            "qld_minus_2x_qqq_residual_bp": float(residual * 10000),
            "prior_252_abs_residual_rank_leq": rank,
            "prior_252_abs_residual_count": 252,
            "prior_252_abs_residual_empirical_percentile": round(rank / 252 * 100, 6),
            "issuer_cash_payment_certified": AMOUNT_NOT_CERTIFIED,
            "dividend_nonpayment_certified": False,
            "independent_adjustment_factor_certified": False,
            "independent_16et_exchange_close_certified": False,
            "same_source_data_cannot_disambiguate_cash_vs_adjustment": True,
            "status": "PRICE_ONLY_PAIRED_RETURN_DESCRIPTIVE_HOLD",
        }
        result.append(event)
    return {
        "version": VERSION, "research_only": True,
        "production_writes": False, "live_execution": False,
        "strategy_promoted": False, "research_hold": True,
        "source": SOURCE_IDENTITY,
        "source_drive_file_id": DRIVE_ID,
        "source_drive_file_name": DRIVE_NAME,
        "source_sha256": file_sha,
        "source_bytes": len(blob), "source_rows": len(rows),
        "source_first_date": rows[0]["date"],
        "source_last_date": rows[-1]["date"],
        "source_stale_for_2026_11_20_daily20": rows[-1]["date"] < "2026-11-20",
        "issuer_cash_payment_certified": False,
        "issuer_nonpayment_certified": False,
        "independent_factor_certified": False,
        "independent_official_regular_close_certified": False,
        "original_daily20_signals_modified": False,
        "events": result,
        "disclosure": ("Both QLD and QQQ same-export price series and return residuals "
                       "are descriptive; the QLD fund's daily leverage, fees, pricing "
                       "rounding, financing and any dividend/adjustment basis are not "
                       "independently identified. No cash-payment or historical "
                       "nonpayment conclusion can be drawn."),
    }


def fetch_from_drive():
    """Read-only Google Drive API: pin service-account identity and exact target."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from publish_drive import EXPECTED_SERVICE_ACCOUNT
    raw = os.environ.get("CKD_DRIVE_SA_JSON", "").strip()
    if not raw:
        encoded = os.environ.get("GDRIVE_SA_JSON_B64", "").strip()
        demand(bool(encoded), "DRIVE_READONLY_AUTH_MISSING")
        raw = base64.b64decode(encoded, validate=True).decode("utf-8")
    conf = json.loads(raw)
    demand(conf.get("type") == "service_account" and
           conf.get("client_email") == EXPECTED_SERVICE_ACCOUNT,
           "DRIVE_SERVICE_ACCOUNT_IDENTITY_NOT_PINNED")
    credentials = service_account.Credentials.from_service_account_info(
        conf, scopes=["https://www.googleapis.com/auth/drive.readonly"])
    service = build("drive", "v3", credentials=credentials,
                    cache_discovery=False)
    meta = service.files().get(
        fileId=DRIVE_ID, fields="id,name,mimeType,size",
        supportsAllDrives=True).execute()
    demand(meta.get("id") == DRIVE_ID and
           meta.get("name") == DRIVE_NAME and
           meta.get("mimeType") in ("text/csv", "application/octet-stream") and
           int(meta.get("size", -1)) == PINNED_BYTES,
           "DRIVE_SOURCE_METADATA_MISMATCH")
    from googleapiclient.http import MediaIoBaseDownload
    from io import BytesIO
    buf = BytesIO()
    stream = MediaIoBaseDownload(
        buf, service.files().get_media(fileId=DRIVE_ID, supportsAllDrives=True),
        chunksize=256 * 1024)
    completed = False
    count = 0
    while not completed:
        count += 1
        demand(count <= 8, "DRIVE_SOURCE_DOWNLOAD_UNBOUNDED")
        _, completed = stream.next_chunk()
        demand(buf.tell() <= 1_000_000, "DRIVE_SOURCE_OVERSIZE")
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--local-fixture", default=None)
    a = ap.parse_args()
    output = Path(a.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        blob = Path(a.local_fixture).read_bytes() if a.local_fixture else fetch_from_drive()
        result = evaluate(blob, pinned=True)
    except Exception as exc:
        # Never misrepresent an unavailable remote as a successfully checked source.
        # For protected main, write an explicit HOLD JSON even on API denial.
        code = type(exc).__name__
        if isinstance(exc, ValueError) and str(exc).startswith("HISTORIC_CA_ALIGNMENT_"):
            code = str(exc)
        result = {
            "version": VERSION,
            "research_only": True,
            "production_writes": False,
            "strategy_promoted": False,
            "live_execution": False,
            "research_hold": True,
            "status": "ARCHIVED_HISTORICAL_DRIVE_SOURCE_UNAVAILABLE_OR_CHANGED_HOLD",
            "failure_code": code,
            "source_drive_file_id": DRIVE_ID,
            "source_sha256_expected": PINNED_SHA256,
            "independent_factor_certified": False,
            "issuer_cash_payment_certified": False,
            "independent_official_regular_close_certified": False,
        }
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("DAILY20_HISTORICAL_CA_ALIGNMENT",
          result.get("status", "EVENT_STUDY_COMPLETE_RESEARCH_HOLD"),
          "rows", result.get("source_rows"),
          "issuer_certified", result["issuer_cash_payment_certified"])
    return 0 if "events" in result else 2


if __name__ == "__main__":
    raise SystemExit(main())
