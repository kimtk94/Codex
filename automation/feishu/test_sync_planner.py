"""Offline regression suite for idempotent, no-delete reconciliation."""
import datetime as dt
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sync_planner import plan
d=dt.date(2026,10,20)
owned=("payment_status","amount")
src=[{"source_key":"a","payment_status":"paid","amount":10},
     {"source_key":"b","payment_status":"pending","amount":20}]
dest=[{"source_key":"a","payment_status":"pending","amount":10,"manual_comment":"keep","_source_date":d},
      {"source_key":"c","payment_status":"paid","amount":5,"_source_date":d}]
count,actions=plan("Payment Outstanding",d,src,dest,owned)
assert count["update"]==1 and count["create"]==1 and count["target_only_preserved"]==1
assert actions[0]["fields"]=={"payment_status":"paid"}
count2,_=plan("Payment Outstanding",d,src,[dict(dest[0],payment_status="paid"),dict(dest[1]),dict(src[1])],owned)
assert count2["update"]==0 and count2["create"]==0
count3,_=plan("Payment Outstanding",d,src,[dict(dest[0],_source_date=dt.date(2026,10,21))],owned)
assert count3["stale"]==1
try: plan("Prepayments",d,[src[0],src[0]],[],owned)
except ValueError: pass
else: raise AssertionError("Duplicate key should be rejected")
try: plan("Prepayments",d,[{"source_key":"a"}],[],owned)
except ValueError: pass
else: raise AssertionError("Unknown mapping should be rejected")
print("SYNC_PLANNER_OFFLINE_TEST: PASS")
print("ACTUAL_WRITES: 0")
