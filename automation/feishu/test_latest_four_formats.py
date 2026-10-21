"""Offline tests for recurring Feishu Sheets names (no network, no secrets)."""
import datetime as dt
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from latest_four_formats import classify,select

today=dt.date(2026,10,21)
cases={
    "Payment Outstanding 10.20":("Payment Outstanding",dt.date(2026,10,20)),
    "eTax - Oct Invoice 10.20":("eTax Invoice",dt.date(2026,10,20)),
    "Payment Receipt 10.20":("Payment Receipt",dt.date(2026,10,20)),
    "Prepayments 10.20":("Prepayments",dt.date(2026,10,20)),
    "Payment Outstanding 10.11":("Payment Outstanding",dt.date(2026,10,11)),
    "Payment Outstanding 09.30":("Payment Outstanding",dt.date(2026,9,30)),
    "Payment Receipt 12.31":("Payment Receipt",dt.date(2025,12,31)),
}
for name,expected in cases.items():
    assert classify(name,today)==expected,(name,classify(name,today))
sheets=[{"title":name,"sheet_id":"sheet"+str(i)} for i,name in enumerate(cases)]
selected,unclassified=select(sheets,today)
assert unclassified==0
assert len(selected)==4
assert selected["Payment Outstanding"]["date"]=="2026-10-20"
assert selected["Payment Outstanding"]["versions"]==3
print("LATEST_FOUR_OFFLINE_TEST: PASS")
