"""Read-only Google Drive CSS source/sink freshness guard. Never emit mail or PII."""
import datetime as dt
import json
import os
import re
import sys
from urllib.parse import quote

UTC = dt.timezone.utc
KST = dt.timezone(dt.timedelta(hours=9))
SHEET = "1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY"
PATTERN = re.compile(r"\bAMEA\d{8,}")

def timestamp(value, kst=False):
    if not isinstance(value, str):
        return None
    try:
        x = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if x.tzinfo is None:
            return x.replace(tzinfo=KST).astimezone(UTC) if kst else None
        return x.astimezone(UTC)
    except ValueError:
        pass
    m = re.fullmatch(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\s*(오전|오후)\s*(\d{1,2}):(\d{2}):(\d{2})", value)
    if not m:
        return None
    y, mo, day, ampm, hr, minute, sec = m.groups()
    try:
        return dt.datetime(int(y), int(mo), int(day), int(hr) % 12 + (12 if ampm == "오후" else 0),
                           int(minute), int(sec), tzinfo=KST).astimezone(UTC)
    except ValueError:
        return None

def iso(value):
    return value.isoformat().replace("+00:00", "Z") if value else None

def classify(metadata, web, health, ingest, now=None):
    now = now or dt.datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("Timezone-aware now required")
    meta = {str(r[0]): str(r[1]) for r in metadata if len(r) >= 2}
    kpi = {}
    for row in web:
        if row and row[0] == "KPI":
            for i in range(1, len(row)-1, 2):
                kpi[str(row[i])] = str(row[i+1])
    sink = timestamp(kpi.get("latest_project_email"), kst=True)
    generated = timestamp(str(web[0][1])) if web and len(web[0]) >= 2 else None
    legacy = timestamp(meta.get("last_run_updated_at"))
    health_times = [timestamp(str(r[4])) for r in health[1:] if len(r) >= 5]
    latest_health = max((t for t in health_times if t), default=None)
    source = []
    examined = 0
    for r in ingest:
        if not r: continue
        examined += 1
        # CSS Git Ingest F:K => received_at, from_email, to, cc, subject, AMEA
        tags = (str(r[5]) if len(r) > 5 else "") + " " + (str(r[4]) if len(r) > 4 else "")
        if not PATTERN.search(tags):
            continue
        t = timestamp(str(r[0]))
        if t: source.append(t)
    latest = max(source, default=None)
    def state(t):
        if t is None: return "SOURCE_UNAVAILABLE"
        age = (now - t).total_seconds()/3600
        return "PASS" if -0.1 <= age <= 36 else "STALE"
    gap = round((latest - sink).total_seconds()/3600, 2) if latest and sink else None
    if not latest or not sink:
        status = "SOURCE_UNAVAILABLE"
    elif gap > 1:
        status = "SINK_LAG"
    elif state(latest) != "PASS" or state(generated) != "PASS":
        status = "STALE"
    else:
        status = "PASS"
    return {
        "status": status, "checked_at": iso(now),
        "source": "CSS Git Ingest recent AMEA mail received_at",
        "source_latest_project_event_at": iso(latest),
        "source_freshness": state(latest),
        "source_rows_examined": examined,
        "source_project_rows_examined": len(source),
        "sink": "WEB_EXPORT latest_project_email",
        "sink_project_event_at": iso(sink),
        "sink_display_generated_at": iso(generated),
        "sink_display_freshness": state(generated),
        "project_event_lag_hours": gap,
        "candidate_newer_project_messages": sum(t > sink + dt.timedelta(hours=1) for t in source) if sink else None,
        "confirmed_unreflected_count": None,
        "legacy_mail_collector_freshness": state(legacy),
        "legacy_mail_collector_last_run_at": iso(legacy),
        "css_system_health_freshness": state(latest_health),
        "css_system_health_latest_at": iso(latest_health),
        "read_only": True,
        "scope": "bounded recent window; not full reconciliation"
    }

def fetch_live():
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import AuthorizedSession
    raw = os.environ.get("GCP_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw: raise RuntimeError("NO_GOOGLE_CREDENTIAL_CONFIG")
    creds = Credentials.from_service_account_info(json.loads(raw),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session = AuthorizedSession(creds)
    base = "https://sheets.googleapis.com/v4/spreadsheets/" + SHEET
    def get(url):
        response = session.get(url, timeout=40)
        response.raise_for_status()
        return response.json()
    sheets = get(base + "?fields=sheets(properties(title,gridProperties(rowCount)))")["sheets"]
    sizes = {s["properties"]["title"]: s["properties"]["gridProperties"]["rowCount"] for s in sheets}
    required = {"_Metadata", "WEB_EXPORT", "CSS System Health", "CSS Git Ingest"}
    if not required.issubset(sizes): raise RuntimeError("REQUIRED_SHEET_MISSING")
    def read(a1):
        return get(base + "/values/" + quote(a1, safe="!'")).get("values", [])
    end = sizes["CSS Git Ingest"]
    start = max(2, end - 2500)
    return classify(read("'_Metadata'!A1:B25"),
                    read("'WEB_EXPORT'!A1:I10"),
                    read("'CSS System Health'!A1:F10"),
                    read(f"'CSS Git Ingest'!F{start}:K{end}"))

def main():
    try:
        data = fetch_live()
    except Exception as exc:
        data = {"status":"SOURCE_UNAVAILABLE","checked_at":iso(dt.datetime.now(UTC)),
                "error_type":type(exc).__name__,"error_details_emitted":False,"read_only":True}
    print(json.dumps(data, ensure_ascii=True, sort_keys=True))
    return 0 if data["status"] == "PASS" else 2

if __name__ == "__main__":
    sys.exit(main())
