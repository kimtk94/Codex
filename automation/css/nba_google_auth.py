"""Dedicated NBA Google Sheets credentials; never fall back to CKD GCP secrets."""
import json
import os
import base64
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def auth():
    raw = os.getenv("NBA_GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError("NBA sales Sheets credential missing: configure NBA_GOOGLE_SERVICE_ACCOUNT_JSON")
    try:
        data = json.loads(raw)
    except ValueError:
        data = json.loads(base64.b64decode(raw))
    return build("sheets", "v4", credentials=service_account.Credentials.from_service_account_info(data, scopes=SCOPES), cache_discovery=False).spreadsheets()
