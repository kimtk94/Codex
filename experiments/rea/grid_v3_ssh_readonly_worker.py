#!/usr/bin/env python3
"""SSH stdin worker: no filesystem writes, no orders, read-only SQLite."""
import json,sys,sqlite3,datetime as dt,math
from pathlib import Path
payload=json.load(sys.stdin)
db=Path(payload["db"]).expanduser().resolve()
if not db.is_file():
    raise SystemExit("READ_ONLY_DB_NOT_FOUND")
con=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
con.execute("PRAGMA query_only=ON")
con.execute("PRAGMA busy_timeout=5000")
count,first,last=con.execute("SELECT COUNT(*), MIN(ts_utc), MAX(ts_utc) FROM candles").fetchone()
if not count:raise SystemExit("EMPTY_DB")
source=payload["source"]
mode=payload["mode"]
if mode=="inclusive_touch":
    if source.count("low<key[1]")!=1 or source.count("high>key[1]")!=1:
        raise SystemExit("SOURCE_FINGERPRINT_MISMATCH")
    source=source.replace("low<key[1]","low<=key[1]").replace("high>key[1]","high>=key[1]")
elif mode!="strict": raise SystemExit("INVALID_MODE")
ns={"__name__":"grid_v3_ssh_readonly","__file__":"<in-memory>"}
exec(compile(source,"<source-from-github-branch>","exec"),ns)
r=ns["sim"](con,int(payload["year"]),float(payload["spacing"]),int(payload["levels"]),float(payload["capital"]),float(payload["fee"]))
con.close()
print(json.dumps({"mode":mode,"result":r,"database":{"bars":count,"first":first,"last":last},"read_only":True,"source_sha":payload["source_sha"]},ensure_ascii=False))
