import unittest
import pandas as pd
import json
from pathlib import Path
from research.regime_countertrend.mirror_snapshot_gate import audit as audit_snapshot
from research.regime_countertrend.mirror_consistency import audit

class MirrorConsistencyTests(unittest.TestCase):
    def fixture(self):
        return pd.DataFrame([
            {"symbol":"A","state":"CLOSED","entry_average_price":100,"exit_average_price":99,
             "net_return":.30,"round_trip_cost_bps":20,
             "entry_order_id":"e1","exit_order_id":"x1","exit_reason":"PROFIT_TO_LOSS_FLIP"},
            {"symbol":"B","state":"CLOSED","entry_average_price":100,"exit_average_price":103,
             "net_return":.028,"round_trip_cost_bps":20,
             "entry_order_id":"e2","exit_order_id":"x2","exit_reason":"MAX_HOLD_4_BUCKETS"},
            {"symbol":"C","state":"CLOSED","entry_average_price":100,"exit_average_price":97,
             "net_return":None,"round_trip_cost_bps":None,
             "entry_order_id":None,"exit_order_id":"x3","exit_reason":"STOP_LOSS_3PCT"}
        ])
    def test_blocks_inflated_stored_profit(self):
        _,r=audit(self.fixture())
        self.assertEqual(r["mirror_count"],3)
        self.assertEqual(r["price_down"],2)
        self.assertEqual(r["net_exceeds_gross"],1)
        self.assertEqual(r["down_with_positive_net"],1)
        self.assertEqual(r["profit_to_loss_flip_price_down"],1)
        self.assertEqual(r["missing_links"],1)
        self.assertFalse(r["promotion_allowed"])
        self.assertTrue(r["status"].startswith("HOLD"))
    def test_net_expected_respects_cost(self):
        t=self.fixture()
        t.loc[0,"net_return"]=-.012
        _,r=audit(t)
        self.assertEqual(r["net_exceeds_gross"],0)
        self.assertEqual(r["net_cost_mismatch"],0)
    def test_nonclosed_excluded(self):
        d=self.fixture()
        d.loc[0,"state"]="OPEN"
        _,r=audit(d)
        self.assertEqual(r["mirror_count"],2)
    def test_frozen_aggregate_snapshot_gate(self):
        source=Path("research/regime_countertrend/reports/neon_mirror_audit_20261102.json")
        report=audit_snapshot(json.loads(source.read_text()))
        self.assertEqual(report["closed_positions"],51)
        self.assertEqual(report["observed_price_down_positions"],33)
        self.assertEqual(report["unreconciled_net_return_gt_gross_count"],6)
        self.assertEqual(report["flip_exit_reason_price_down"],17)
        self.assertFalse(report["promotion_allowed"])
        out=Path("results/regime_countertrend/mirror_snapshot")
        out.mkdir(parents=True,exist_ok=True)
        (out/"decision.json").write_text(json.dumps(report,indent=2))
        print("MIRROR_AGGREGATE_GATE",json.dumps(report))
    def test_snapshot_invalid_reason_count_blocks(self):
        source=Path("research/regime_countertrend/reports/neon_mirror_audit_20261102.json")
        report=json.loads(source.read_text())
        report["exit_reason_price_loss_counts"][0]["count"]+=1
        with self.assertRaises(ValueError):
            audit_snapshot(report)
    def test_snapshot_invalid_net_coverage_blocks(self):
        source=Path("research/regime_countertrend/reports/neon_mirror_audit_20261102.json")
        report=json.loads(source.read_text())
        report["metadata_net_return"]["available"]+=1
        with self.assertRaises(ValueError):
            audit_snapshot(report)
    def test_bad_schema(self):
        with self.assertRaises(ValueError):
            audit(pd.DataFrame({"state":["CLOSED"]}))
if __name__=="__main__":unittest.main()
