#!/usr/bin/env python3
"""Read-only audit: weekly approval evidence, report freshness and money provenance.

No SFDC/Feishu/customer/mail writes. No customer/quote identifiers in output.
Fail closed if weekly source counts disagree or the Quote export is stale.
"""
import collections
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from zoneinfo import ZoneInfo

UNIFIED = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
CSS = "1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY"
KST = ZoneInfo("Asia/Seoul")
SF_ID = re.compile(r"a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?")
SOURCE = (
    ("dedup", UNIFIED, "Quote Approval Dedup", "A1:Q1600"),
    ("weekly", UNIFIED, "SFDC Weekly Overview", "A1:S150"),
    ("export", UNIFIED, "SFDC Quote Export", "A1:O2600"),
    ("legacy", CSS, "Quotation Approval List", "A1:W1600"),
    ("cssweekly", CSS, "Quotation Weekly Summary", "A1:P150"),
)

def last_four_completed(today):
    # Friday through Thursday. The current sales week is never completed.
    current_friday = today - dt.timedelta(days=(today.weekday()-4) % 7)
    return [(current_friday - dt.timedelta(days=7*i)).isoformat()
            for i in range(1, 5)]

def sheet_rows(rows, required):
    if not rows:
        raise ValueError("EMPTY_SHEET")
    head = [str(s).strip() for s in rows[0]]
    if len(set(head)) != len(head) or not set(required).issubset(head):
        raise ValueError("QUOTE_AUDIT_SOURCE_SCHEMA_INVALID")
    return [{name: ("" if i >= len(row) or row[i] is None else str(row[i]).strip())
             for i, name in enumerate(head)}
            for row in rows[1:] if any(str(v or "").strip() for v in row)]

def get_all():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    raw = os.environ.get("GCP_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        raise RuntimeError("GCP_READONLY_CREDENTIAL_MISSING")
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    sess = AuthorizedSession(credentials)
    result = {}
    for key,book,tab,rectangle in SOURCE:
        rng = urllib.parse.quote("'" + tab.replace("'", "''") + "'!" + rectangle, safe="")
        url = "https://sheets.googleapis.com/v4/spreadsheets/" + book + "/values/" + rng
        res = sess.get(url, timeout=55)
        if not res.ok:
            raise RuntimeError("QUOTE_AUDIT_SOURCE_READ_FAILED_" + key + "_" + str(res.status_code))
        result[key] = res.json().get("values") or []
    return result

def number(value):
    s = str(value or "").strip().replace(",", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?", s):
        return None
    return float(s)

def normalized_id(raw):
    key = str(raw or "").strip()
    return key[:15] if SF_ID.fullmatch(key) else ""

def evidence_week(value):
    iso = str(value or "")[:10]
    try:
        day = dt.date.fromisoformat(iso)
    except ValueError:
        return None
    return (day - dt.timedelta(days=(day.weekday()-4) % 7)).isoformat()

def summarize(data, now=None):
    today = (now or dt.datetime.now(KST)).date()
    target = last_four_completed(today)
    needed = {
        "dedup":["Approval KST","SFDC Record ID","Week Status","Approval Evidence",
                 "Approved AND Active","Quote Status","Currency","Verified Amount kUSD"],
        "weekly":["week_start","quotation_approvals"],
        "export":["Salesforce Record ID","Exported At KST"],
        "legacy":["week_start","salesforce_record_id"],
        "cssweekly":["week_start","quotation_count"],
    }
    src = {k:sheet_rows(data[k],required) for k,required in needed.items()}
    latest = None
    for row in src["export"]:
        timestamp = row["Exported At KST"].replace(" KST","").strip()
        try:
            stamp = dt.datetime.fromisoformat(timestamp)
        except ValueError:
            continue
        if latest is None or stamp > latest:
            latest = stamp
    stamp_age_days = ((now or dt.datetime.now(KST)).replace(tzinfo=None)-latest).total_seconds()/86400 if latest else None
    report_fresh = stamp_age_days is not None and 0 <= stamp_age_days <= 2
    byweek = collections.defaultdict(list)
    for item in src["dedup"]:
        week = evidence_week(item["Approval KST"])
        if week in target:
            byweek[week].append(item)
    count_map = {}
    for item in src["weekly"]:
        week = item["week_start"]
        if week in target:
            if week in count_map:
                raise ValueError("DUPLICATE_WEEKLY_OVERVIEW")
            count_map[week] = number(item["quotation_approvals"])
    css_weekly = {}
    for item in src["cssweekly"]:
        if item["week_start"] in target:
            css_weekly[item["week_start"]] = number(item["quotation_count"])
    legacy = collections.Counter(x["week_start"] for x in src["legacy"])
    weeks = []
    for week in sorted(target):
        items = byweek[week]
        seen = set()
        duplicates = invalid_id = nonblank_values = active_proven = qualified_values = 0
        for item in items:
            record_id = normalized_id(item["SFDC Record ID"])
            first_seen_id = bool(record_id) and record_id not in seen
            if not record_id:
                invalid_id += 1
            elif not first_seen_id:
                duplicates += 1
            else:
                seen.add(record_id)
            amount = number(item["Verified Amount kUSD"])
            if amount is not None:
                nonblank_values += 1
            verified = (first_seen_id and
                        item["Approved AND Active"] == "YES" and
                        item["Quote Status"] == "ACTIVE" and
                        item["Currency"].upper() == "USD")
            if verified:
                active_proven += 1
                if amount is not None and report_fresh:
                    qualified_values += 1
        weekly_count = count_map.get(week)
        evidence_unique = len(seen)
        mismatch = (weekly_count is None or int(weekly_count) != evidence_unique or
                    invalid_id > 0 or duplicates > 0)
        weeks.append({
            "week_start":week,
            "approval_rows":len(items),
            "distinct_salesforce_ids":evidence_unique,
            "id_missing_or_invalid":invalid_id,
            "duplicate_id_rows":duplicates,
            "sfdc_weekly_count":weekly_count,
            "css_legacy_rows":legacy.get(week,0),
            "css_weekly_count":css_weekly.get(week),
            "nonblank_money_cells":nonblank_values,
            "active_proven_rows":active_proven,
            "eligible_value_rows":qualified_values,
            "count_mismatch":mismatch,
        })
    blockers = []
    if not report_fresh: blockers.append("SFDC_QUOTE_EXPORT_STALE_OR_MISSING")
    if any(w["count_mismatch"] for w in weeks):blockers.append("WEEKLY_SOURCE_COUNT_DIVERGENCE")
    if any(w["nonblank_money_cells"]>w["eligible_value_rows"] for w in weeks):
        blockers.append("MONETARY_CELLS_LACK_CURRENT_ACTIVE_PROOF")
    # Approval-mail evidence does not expose a verified sales owner field.
    blockers.append("OWNER_SCOPE_UNVERIFIED_IN_APPROVAL_EVIDENCE")
    return {
        "status":"HOLD" if blockers else "PASS",
        "source_export_latest_kst":latest.isoformat(sep=" ") if latest else None,
        "source_export_age_days":round(stamp_age_days,2) if stamp_age_days is not None else None,
        "source_export_fresh":report_fresh,
        "weeks":weeks, "blockers":blockers,
        "source_rows":{key:len(rows) for key,rows in src.items()},
        "note":"Counts are approval-evidence rows, not verified owner-scoped active Quotes; blank money never becomes zero.",
    }

def summary_markdown(result):
    lines = ["## Feishu Quote four-week source audit", "",
             "**Status: " + result["status"] + "**",
             "Export snapshot: " + str(result["source_export_latest_kst"]) +
             " KST; age " + str(result["source_export_age_days"]) + " days.",
             "",
             "| Fri-Thu start | Approval rows | Distinct Quote IDs | Weekly KPI | CSS legacy rows | Nonblank USD cells | Current active/value proof |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for w in result["weeks"]:
        lines.append("| " + w["week_start"] + " | " + str(w["approval_rows"]) +
                     " | " + str(w["distinct_salesforce_ids"]) +
                     " | " + str(w["sfdc_weekly_count"]) +
                     " | " + str(w["css_legacy_rows"]) +
                     " | " + str(w["nonblank_money_cells"]) +
                     " | " + str(w["eligible_value_rows"]) + " |")
    lines += ["", "Blockers: " + (", ".join(result["blockers"]) if result["blockers"] else "none"),
              "", "No customers, quote IDs, amounts or source records are printed or modified.",
              ""]
    return "\n".join(lines)

def main():
    result = summarize(get_all())
    report = summary_markdown(result)
    print(report)
    output = os.environ.get("GITHUB_STEP_SUMMARY")
    if output:
        with open(output,"a",encoding="utf-8") as handle:
            handle.write(report)
    print("QUOTE_SOURCE_AUDIT_STATUS="+result["status"]+
          " blockers="+",".join(result["blockers"]))
    return 2 if result["status"]=="HOLD" else 0

if __name__=="__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("QUOTE_SOURCE_AUDIT_FAILED="+type(exc).__name__,file=sys.stderr)
        sys.exit(1)
