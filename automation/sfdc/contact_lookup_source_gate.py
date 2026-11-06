#!/usr/bin/env python3
"""Read-only SFDC web lookup source gate.

Do not equate a recent Sheet copy timestamp with a live Salesforce snapshot.
Emit counts and status codes only: no Contact, Account, email, pricing, or ID data
in Actions logs. No CRM actions, no Sheet writes, no public customer export.
"""
import datetime as dt
import json
import os
import sys

KST = dt.timezone(dt.timedelta(hours=9))
REQUIRED_OBJECTS = ("SFDC Opportunity Raw", "SFDC Contacts", "Quotation")
REQUIRED_FIELDS = {
    "SFDC Opportunity Raw": ("Opportunity ID", "Last Modified Date"),
    "SFDC Contacts": ("Contact ID", "Last Modified Date", "Account ID"),
    "Quotation": ("SFDC Quotation ID", "Quotation ID", "Active", "Last Modified Date"),
}

def rows_as_dict(rows):
    if not rows:
        return {}
    header = [str(x).strip() for x in rows[0]]
    return {
        str(row[0]).strip(): {
            key: str(row[i]).strip() if i < len(row) else ""
            for i, key in enumerate(header)
        }
        for row in rows[1:] if row
    }

def parse_timestamp(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace(" KST", "").strip())
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        return parsed.astimezone(KST)
    except ValueError:
        return None

def assess_source_gate(audit_rows, readiness_rows, link_rows, report_rows, *,
                       now=None):
    now = now or dt.datetime.now(KST)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    audits = rows_as_dict(audit_rows)
    reports = rows_as_dict(readiness_rows)
    links = rows_as_dict(link_rows)
    report_metrics = rows_as_dict(report_rows[1:]) if report_rows else {}
    result = {
        "checked_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
        "contact_lookup_gate": "BLOCK",
        "opportunity_quote_gate": "BLOCK",
        "website_live_search": "NOT_CONNECTED",
        "objects": {},
        "report_staging_only": {},
        "reason_codes": [],
        "writes_performed": False,
    }
    for obj in REQUIRED_OBJECTS:
        src = audits.get(obj, {})
        check = reports.get(obj, {})
        missing = {x.strip() for x in check.get("missing_fields","").split(",") if x.strip()}
        requirements_met = not any(x in missing for x in REQUIRED_FIELDS[obj])
        stable = (check.get("stable_id") == "YES")
        modified = (check.get("modified_timestamp") == "YES")
        schema = (check.get("required_field_check") == "PASS" and requirements_met)
        proof = (src.get("freshness_verified") == "YES")
        last = parse_timestamp(src.get("last_checked_kst", ""))
        age = ((now.astimezone(KST)-last).total_seconds()/3600.0) if last else None
        timing = (age is not None and -0.1 <= age <= 8)
        ready = stable and modified and schema and proof and timing
        result["objects"][obj] = {
            "row_count": int(src.get("record_count","0")) if src.get("record_count","0").isdigit() else None,
            "schema_pass": schema, "id_verified": stable,
            "modified_timestamp_verified": modified,
            "freshness_proven": proof, "copy_checked_recently": timing,
            "gate": "SOURCE_PASS" if ready else "SOURCE_HOLD",
        }
        if not ready:
            result["reason_codes"].append("SOURCE_UNVERIFIED_"+obj.upper().replace(" ","_"))
    if all(result["objects"][k]["gate"]=="SOURCE_PASS"
           for k in ("SFDC Opportunity Raw","SFDC Contacts")):
        result["contact_lookup_gate"] = "READY_FOR_AUTHENTICATED_LIVE_RECHECK"
    if (result["contact_lookup_gate"] == "READY_FOR_AUTHENTICATED_LIVE_RECHECK"
        and result["objects"]["Quotation"]["gate"]=="SOURCE_PASS"
        and links.get("active_validation_ready",{}).get("value")=="True"
        and links.get("sfdc_quote_id_column_present",{}).get("value")=="True"
        and links.get("related_opportunity_id_column_present",{}).get("value")=="True"):
        result["opportunity_quote_gate"] = "READY_FOR_AUTHENTICATED_LIVE_RECHECK"
    else:
        result["reason_codes"].append("QUOTATION_LINK_VERIFICATION_REQUIRED")
    # Email-delivered reports are a separately labeled source and never
    # upgrade the live Contact lookup gate, even if they are more up to date.
    for metric, key in (("Lead records","leads"),("Opportunity records","opportunities"),
                        ("Unique quotation IDs","quotation_ids")):
        value = report_metrics.get(metric,{}).get("Latest QQ staged","")
        result["report_staging_only"][key] = int(value) if value.isdigit() else None
    result["reason_codes"] = list(dict.fromkeys(result["reason_codes"]))
    return result

def main():
    from followup_stage1 import auth, OUTPUT_ID
    from opportunity_quote_mirror import range_data
    session=auth()
    a=range_data(session,OUTPUT_ID,"SFDC Source Audit",120)
    b=range_data(session,OUTPUT_ID,"SFDC Report Readiness",20)
    c=range_data(session,OUTPUT_ID,"SFDC Quote Link Audit",30)
    d=range_data(session,OUTPUT_ID,"SFDC 3Report Analytics",45)
    result=assess_source_gate(a,b,c,d)
    # Deliberately log only operational states and aggregate counts.
    message=json.dumps(result,ensure_ascii=False)
    print(message)
    summary=os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary,"a",encoding="utf-8") as f:
            f.write("\n## Salesforce Contact/Quotation lookup readiness\n\n")
            f.write("| Gate | State |\n|---|---|\n")
            for item in ("contact_lookup_gate","opportunity_quote_gate","website_live_search"):
                f.write(f"| {item} | {result[item]} |\n")
            f.write("\nLive Salesforce lookup is not proven by report delivery or Sheet copy time.\n")
    return 0

if __name__=="__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("SFDC_LOOKUP_GATE_ERROR="+type(exc).__name__,file=sys.stderr)
        sys.exit(1)
