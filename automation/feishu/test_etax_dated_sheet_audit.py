"""Offline dated Feishu eTax sheet classification; no credentials."""
import datetime as dt
from etax_dated_sheet_audit import classify,headers_ok,REQUIRED
today=dt.date(2026,10,31)
fresh={"eTax Invoice":{"sheet_id":"x","date":"2026-10-30"}}
stale={"eTax Invoice":{"sheet_id":"x","date":"2026-10-26"}}
old={"eTax Invoice":{"sheet_id":"x","date":"2026-09-30"}}
assert classify(fresh,today)[0]=="CURRENT_MONTH_SNAPSHOT_FRESH"
assert classify(stale,today)[0]=="CURRENT_MONTH_SNAPSHOT_STALE_REVIEW"
assert classify(old,today)[0]=="BLOCK_WRONG_MONTH"
assert classify(None,today)[0]=="BLOCK_MISSING_DATED_SHEET"
assert classify({"eTax Invoice":{"date":"2026-11-01"}},today)[0]=="BLOCK_WRONG_MONTH"
assert headers_ok([list(REQUIRED)])
assert headers_ok([["title"],["extra"],list(REQUIRED)])
assert not headers_ok([["CMS Invoice Num","Amount"]])
assert not headers_ok([])
print("ETAX_DATED_SHEET_SCHEMA_OFFLINE_PASS")
