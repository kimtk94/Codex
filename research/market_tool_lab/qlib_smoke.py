"""Qlib installation and callable-surface smoke, never download datasets or use credentials."""
import json
import qlib
from pathlib import Path
result={"engine":"qlib","status":"IMPORT_PASS","version":getattr(qlib,"__version__","unknown"),
        "training":"NOT_RUN","market_data":"NOT_ATTACHED",
        "warning":"A successful import does not imply ML model accuracy or Kalman compatibility."}
out=Path("artifacts/market-tool-lab/qlib_smoke.json")
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result))
