#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
from pathlib import Path

try:
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import AuthorizedSession
except ImportError as exc:
    raise SystemExit("Install dependencies first: pip install google-auth requests") from exc

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
RANGES = {
    "project_dashboard": "'CSS Project Dashboard'!A1:AK1000",
    "action_center": "'CSS Action Center'!A1:V2000",
    "customer_360": "'CSS Customer 360'!A1:P500",
    "web_export": "'WEB_EXPORT'!A1:AN1000",
}


def main(sheet_id: str, credentials_path: Path, output: Path) -> None:
    creds = Credentials.from_service_account_file(str(credentials_path), scopes=SCOPES)
    session = AuthorizedSession(creds)
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values:batchGet"
    params = [("ranges", r) for r in RANGES.values()]
    params += [("majorDimension", "ROWS"), ("valueRenderOption", "FORMATTED_VALUE")]
    resp = session.get(url, params=params, timeout=120)
    resp.raise_for_status()
    payload = resp.json()
    value_ranges = payload.get("valueRanges", [])
    out = {
        "spreadsheet_id": sheet_id,
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    for (key, _), item in zip(RANGES.items(), value_ranges):
        out[key] = item.get("values", [])
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(output)
    print("CSS Sheet snapshot written:", output)
    for key in RANGES:
        print(f"  {key}: {max(0, len(out.get(key, [])) - 1)} rows")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet-id", default=os.environ.get("CSS_SHEET_ID", ""))
    ap.add_argument("--credentials", default=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ""))
    ap.add_argument("--output", default=os.environ.get("CSS_SHEET_SNAPSHOT", "/srv/masteros/cache/css_sheet_snapshot.json"))
    a = ap.parse_args()
    if not a.sheet_id:
        raise SystemExit("CSS_SHEET_ID is required")
    if not a.credentials:
        raise SystemExit("GOOGLE_APPLICATION_CREDENTIALS is required")
    main(a.sheet_id, Path(a.credentials), Path(a.output))
