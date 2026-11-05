"""Synthetic-only month-block and ex-ante 50/100bps repricing contracts."""
import unittest

from coin_private_tail import month_block_interval, reprice_plan, stress
from coin_signal_replay import replay
from test_coin_signal_replay import synthetic_sessions, row


class PrivateTailContracts(unittest.TestCase):
    def test_cost_repricing_respects_rr2_and_eight_pct_cap(self):
        g={"pass":True,"stop_pct":.02,"target_pct":.0490000001}
        a=reprice_plan(g,"FIXED_2PCT_2R",.005)
        b=reprice_plan(g,"FIXED_2PCT_2R",.01)
        self.assertAlmostEqual(a[1],.055,places=7)
        self.assertAlmostEqual(b[1],.07,places=7)
        self.assertGreaterEqual((a[1]-.005)/(a[0]+.005),2)
        self.assertIsNone(reprice_plan(
            {"pass":True,"stop_pct":.03,"target_pct":.069},
            "ORL_BUFFER_2R",.01))
        self.assertIsNone(reprice_plan(
            {"pass":True,"stop_pct":.02,"target_pct":.049},
            "ORL_PRIOR20_HIGH",.005))

    def test_monthly_cluster_not_individual_bootstrap(self):
        sessions=[{"date":f"2026-{m:02d}-03"} for m in (1,2,3,4)]
        trades=[{"entry_index":i,"realized_R":r}
                for i,r in enumerate((1.9,-1.1,1.1,-1))]
        a=month_block_interval(trades,sessions,seed=42,iterations=100)
        b=month_block_interval(trades,sessions,seed=42,iterations=100)
        self.assertEqual(a,b)
        self.assertEqual(a["months"],4)
        self.assertEqual(len(a["bootstrap95_mean_R"]),2)
        self.assertAlmostEqual(a["leave_best_trade_out_mean_R"],
                               (-1.1+1.1-1)/3,places=6)
        self.assertNotIn("2026-01",str(a))

    def test_30bp_parity_and_36_synthetic_cells(self):
        sessions,q=synthetic_sessions()
        rows=[row(sessions,22,"a"),row(sessions,24,"b")]
        base=replay(sessions,q,rows,"synthetic-hash",expected={2026:2})
        d=stress(sessions,rows,base["results"],expected={2026:2})
        self.assertEqual(len(d["results"]),36)
        self.assertEqual(d["live"],"HOLD")
        self.assertTrue(d["no_private_dates_or_trade_rows"])
        for ref in base["results"]:
            r=next(x for x in d["results"] if
                   (x["year"],x["arm"],x["hold_sessions"],x["roundtrip_cost_bps"])==
                   (ref["year"],ref["arm"],ref["hold_sessions"],30))
            self.assertEqual(r["trades"],ref["trades"])
            self.assertEqual(r["net_mean_R"],ref["mean_R"])
        self.assertIn(50,{x["roundtrip_cost_bps"] for x in d["results"]})
        self.assertIn(100,{x["roundtrip_cost_bps"] for x in d["results"]})

    def test_mean_parity_failure_blocks(self):
        sessions,q=synthetic_sessions()
        rows=[row(sessions,22,"a"),row(sessions,24,"b")]
        base=replay(sessions,q,rows,"synthetic-hash",expected={2026:2})
        base["results"][0]["mean_R"]=-100
        with self.assertRaisesRegex(ValueError,"REPRICE_30BP_BASELINE_PARITY_FAILED"):
            stress(sessions,rows,base["results"],expected={2026:2})


if __name__=="__main__":
    unittest.main()
