#!/usr/bin/env python3
"""Read-only Upbit KRW-ETH 1m coverage audit. No set -e, no database writes."""
import sqlite3
from pathlib import Path
import pandas as pd

HOME=Path.home()
ROOT=HOME/"kalman-data/upbit_grid_research"
DB=HOME/"research/upbit_eth/krw_eth_1m.sqlite3"

def parse_time(s):
    numeric=pd.to_numeric(s,errors="coerce")
    if numeric.notna().mean()>.99:
        med=numeric.abs().median()
        unit="ns" if med>=1e17 else "us" if med>=1e14 else "ms" if med>=1e11 else "s"
        return pd.to_datetime(numeric,unit=unit,utc=True,errors="coerce")
    return pd.to_datetime(s,utc=True,errors="coerce")

def main():
    if DB.exists():
        c=sqlite3.connect(f"file:{DB}?mode=ro",uri=True,timeout=10)
        c.execute("PRAGMA query_only=ON")
        print("SQLITE",c.execute("SELECT COUNT(*), MIN(ts_utc), MAX(ts_utc) FROM candles").fetchone())
        print("CURSOR",c.execute("SELECT key,val FROM metadata").fetchall())
        c.close()
    for f in sorted(ROOT.rglob("KRW-ETH_1m_history.csv")):
        try:
            hdr=pd.read_csv(f,nrows=0).columns.tolist()
            col=next((x for x in ("t","ts_utc","open_time_ms","timestamp","datetime","date","time") if x in hdr),None)
            if col is None:
                print("UNKNOWN",str(f),hdr);continue
            s=pd.read_csv(f,usecols=[col])[col]
            ts=parse_time(s)
            good=ts.dropna()
            dif=good.sort_values().diff()
            print("CSV",str(f),"rows",len(s),"first",str(good.min()),
                  "last",str(good.max()),"invalid",int(ts.isna().sum()),
                  "duplicates",int(good.duplicated().sum()),
                  "gaps_over_1m",int((dif>pd.Timedelta(minutes=1)).sum()),
                  "max_gap",str(dif.max()))
        except Exception as exc:
            print("ERROR",str(f),str(exc))
if __name__=="__main__":
    main()
