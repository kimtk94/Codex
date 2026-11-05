"""Non-trading provider capability probe: OpenBB Cboe latest 1m bars.

No historical-intraday availability is inferred from latest-day success.
"""
import json
from pathlib import Path
from datetime import datetime,timezone
result={"schema_version":1,"provider":"openbb_cboe","interval":"1m","historical_intraday_supported":False,"observed_utc":datetime.now(timezone.utc).isoformat(),"symbols":{}}
try:
    from openbb import obb
    for symbol in ("QQQ","QLD"):
        try:
            df=obb.cboe.equity.historical(symbol=symbol,interval="1m",provider="cboe").to_dataframe()
            result["symbols"][symbol]={"status":"PASS" if len(df) else "EMPTY","rows":int(len(df)),
              "first":str(df.index.min()) if len(df) else None,"last":str(df.index.max()) if len(df) else None}
        except Exception as exc:
            result["symbols"][symbol]={"status":"ERROR","error_type":type(exc).__name__,"message":str(exc)[:160]}
except Exception as exc:
    result["setup_error"]={"error_type":type(exc).__name__,"message":str(exc)[:160]}
folder=Path("artifacts/market-tool-lab/capability")
folder.mkdir(parents=True,exist_ok=True)
(folder/"cboe_latest_1m.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result))
