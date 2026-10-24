"""Read-only Sales Command dashboard aggregate adapter.

Runs in trusted GitHub Actions/CI, never in an anonymous browser.
Only writes an aggregate output if all source pages validate.
"""
import argparse
import datetime as dt
import json
import math
import os
import pathlib
import urllib.parse
import urllib.request

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
FIELDS = {
    "service": ["Invoice Month", "Service Group", "Revenue KRW", "Revenue K USD", "Coverage", "Invoice Source", "Validation"],
    "kpi": ["Metric", "Value", "Unit"],
}
DEFAULT_ID = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"

def header_rows(values, fields):
    if not values:
        raise ValueError("Source tab returned no rows")
    header = values[0]
    absent = set(fields).difference(header)
    if absent:
        raise ValueError(f"Missing required header(s): {sorted(absent)}")
    return [dict(zip(header, row)) for row in values[1:] if any(str(v).strip() for v in row)]

def valid_money(v):
    try:
        n = float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        raise ValueError("Invalid monetary value")
    if not math.isfinite(n):
        raise ValueError("Non-finite monetary value")
    return n

def build_aggregate(kpi_values, service_values, as_of):
    kpi_rows = header_rows(kpi_values, FIELDS["kpi"])
    services = header_rows(service_values, FIELDS["service"])
    metrics = {str(x["Metric"]).strip(): x for x in kpi_rows}
    rev = metrics.get("Invoice Revenue")
    # KPI source may be cumulative; explicitly label scope unknown.
    total = valid_money(rev["Value"]) if rev else None
    groups = {}
    coverage = set()
    for row in services:
        month = str(row["Invoice Month"]).strip()
        if len(month) != 7 or month[4] != "-" or not (1 <= int(month[5:]) <= 12):
            raise ValueError("Invalid invoice month")
        if row["Invoice Source"] != "TAX_INVOICE":
            raise ValueError("Non-invoice revenue source found")
        service = str(row["Service Group"]).strip()
        key = (month, service)
        if key in groups:
            raise ValueError(f"Duplicate month/service group: {key}")
        groups[key] = {
            "month": month, "service": service,
            "krw": valid_money(row["Revenue KRW"]),
            "kUsd": valid_money(row["Revenue K USD"]),
            "coverage": row.get("Coverage", "UNKNOWN"),
            "validation": row.get("Validation", "UNKNOWN"),
        }
        coverage.add(str(row.get("Coverage", "UNKNOWN")))
    if not services:
        raise ValueError("No monthly service rows; aggregate not published")
    return {
        "asOf": as_of, "basis": "TAX_INVOICE",
        "reportingFxKrwPerUsd": 1500,
        "coverage": sorted(coverage),
        "revenue": {"krw": total, "scope": "source_KPI_scope_unverified", "kUsd": None},
        "serviceMonthly": sorted(groups.values(), key=lambda x: (x["month"], x["service"])),
        "sourceTabs": ["BI Monthly KPI", "BI Service Monthly 10"],
        "dataSecurity": "approved_aggregate_only",
    }

def fetch_values(sheet_id, tab, auth_token):
    path = urllib.parse.quote(f"'{tab}'!A1:K20000", safe="!:'")
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{path}?valueRenderOption=UNFORMATTED_VALUE"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {auth_token}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response).get("values", [])

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--fixture", help="local fixture path for tests; no network calls")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    if args.fixture:
        fixture = json.loads(pathlib.Path(args.fixture).read_text(encoding="utf-8"))
        kpi, service = fixture["kpi"], fixture["service"]
    else:
        # GITHUB_ACTIONS input must be a short-lived scoped OAuth token, never embedded in frontend code.
        token = os.environ["GOOGLE_SHEETS_ACCESS_TOKEN"]
        sid = os.environ.get("SALES_SHEET_ID", DEFAULT_ID)
        kpi = fetch_values(sid, "BI Monthly KPI", token)
        service = fetch_values(sid, "BI Service Monthly 10", token)
    output = build_aggregate(kpi, service, dt.datetime.now(dt.timezone.utc).isoformat())
    dest = pathlib.Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(dest)
    print("AGGREGATE_VALIDATED", "monthly_records=", len(output["serviceMonthly"]))

if __name__ == "__main__":
    main()
