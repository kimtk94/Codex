"""Run authorized private execution attribution only after evidence admission."""
import json
from pathlib import Path

import pandas as pd

from .evidence_gate import classify_evidence
from .execution_validation import attribute

def main():
    root=Path("research/regime_countertrend/data/execution")
    out=Path("results/regime_countertrend/execution")
    out.mkdir(parents=True,exist_ok=True)
    trades=root/"real_trades.csv"
    bars=root/"real_15m_bars.csv"
    evidence=root/"source_attestation.json"
    verdict=classify_evidence(trades,bars,evidence)
    (out/"evidence_gate.json").write_text(json.dumps(verdict,indent=2))
    if verdict["status"]!="PASS_EVIDENCE_CONTRACT_ONLY":
        (out/"coverage.json").write_text(json.dumps({
            "status":verdict["status"],"actual_fill_analysis_completed":False,
            "source":"HOLD_UNVERIFIED_OR_UNAVAILABLE_BROKER_DATA",
            "real_trades_verified":0},indent=2))
        print(json.dumps(verdict))
        return
    trade_rows,coverage=attribute(pd.read_csv(trades),pd.read_csv(bars))
    trade_rows.to_csv(out/"trade_attribution.csv",index=False)
    coverage["status"]="INTRADAY_ATTRIBUTION_UNVERIFIED_BROKER_RECONCILIATION"
    coverage["actual_fill_analysis_completed"]=False
    coverage["promotion_allowed"]=False
    (out/"coverage.json").write_text(json.dumps(coverage,indent=2))
    print(json.dumps({"status":coverage["status"],"trade_count":coverage["trades"]}))
if __name__=="__main__":main()
