"""Keyless OpenBB V5 Cboe historical probe, read-only."""
import csv
import json
import os
from datetime import date
from pathlib import Path

SYMBOLS=("QQQ","QLD","SPY","TQQQ")
OUT=Path(os.environ.get("PROBE_OUTPUT","artifacts/market-tool-lab/openbb"))
OUT.mkdir(parents=True,exist_ok=True)
summary={"provider":"OpenBB V5 / cboe","observed_at_utc":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),"symbols":{}}
try:
    from openbb import obb
    for symbol in SYMBOLS:
        try:
            result=obb.cboe.equity.historical(symbol=symbol,start_date="2026-09-01",provider="cboe")
            frame=result.to_dataframe()
            n=len(frame)
            summary["symbols"][symbol]={"status":"PASS" if n else "NO_ROWS","rows":n,"columns":[str(c) for c in frame.columns]}
            if n:
                frame.to_csv(OUT/(symbol+".csv"),index=True)
        except Exception as exc:
            summary["symbols"][symbol]={"status":"ERROR","type":type(exc).__name__,"reason":str(exc)[:180]}
except Exception as exc:
    summary["setup_error"]={"type":type(exc).__name__,"reason":str(exc)[:180]}
(OUT/"summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n")
print(json.dumps(summary,ensure_ascii=False))
if summary.get("setup_error") or not any(x.get("status")=="PASS" for x in summary["symbols"].values()):
    raise SystemExit(1)
