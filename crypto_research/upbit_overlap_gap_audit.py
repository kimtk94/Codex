#!/usr/bin/env python3
"""Read-only SQLite-vs-CSV Upbit 1m overlap and large gap audit."""
import sqlite3
from pathlib import Path
import pandas as pd
HOME=Path.home()
DB=HOME/"research/upbit_eth/krw_eth_1m.sqlite3"
ROOT=HOME/"kalman-data/upbit_grid_research"
FILES=["v39_monthly/2026-07/KRW-ETH_1m_history.csv","v39_monthly/2026-08/KRW-ETH_1m_history.csv","v32_sep_full/KRW-ETH_1m_history.csv","monthly_1m_20261001_09/KRW-ETH_1m_history.csv"]
def main():
    db=sqlite3.connect(f"file:{DB}?mode=ro",uri=True,timeout=15)
    db.execute("PRAGMA query_only=ON")
    for rel in FILES:
        path=ROOT/rel
        if not path.exists(): continue
        a=pd.read_csv(path)
        a["ts"]=pd.to_datetime(a["t"],utc=True,errors="coerce",unit="ms" if pd.api.types.is_numeric_dtype(a["t"]) and a["t"].median()>1e11 else None)
        a=a.dropna(subset=["ts"]).sort_values("ts")
        lo=a.ts.min().isoformat(); hi=a.ts.max().isoformat()
        b=pd.read_sql_query("SELECT ts_utc,open,high,low,close FROM candles WHERE ts_utc>=? AND ts_utc<=? ORDER BY ts_utc",db,params=[lo,hi])
        b["ts"]=pd.to_datetime(b.ts_utc,utc=True)
        overlap=a.merge(b,on="ts",how="inner")
        summary={"file":rel,"csv_rows":len(a),"sqlite_rows_in_range":len(b),"overlap":len(overlap),"csv_only":len(a)-len(overlap),"sqlite_only":len(b)-len(overlap)}
        for col,short in [("open","o"),("high","h"),("low","l"),("close","c")]:
            if short in overlap:
                lhs=pd.to_numeric(overlap[short],errors="coerce")
                rhs=pd.to_numeric(overlap[col],errors="coerce")
                summary[col+"_mismatch"]=int(((lhs-rhs).abs()>0.00001).sum())
        print("OVERLAP",summary)
        gap=a.ts.diff()
        largest=gap.nlargest(5)
        for index,delta in largest.items():
            if delta>pd.Timedelta(minutes=3):
                end=a.loc[index,"ts"];start=a.loc[a.index[a.index.get_loc(index)-1],"ts"] if a.index.get_loc(index)>0 else None
                print("GAP",rel,"start",start,"end",end,"duration",delta)
    db.close()
if __name__=="__main__":main()
