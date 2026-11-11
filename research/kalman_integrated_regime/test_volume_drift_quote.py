"""No-lookahead/asof quote classifier and complete signal-partition contracts."""
import unittest

from research.kalman_integrated_regime.sip_quote_aggressor_probe import classify
from research.kalman_integrated_regime.test_volume_four_arm import synthetic_data
from research.kalman_integrated_regime.volume_regime_drift import collect_drift


class QuoteAggressorContract(unittest.TestCase):
    def test_strict_prior_quote_unknown_and_balance(self):
        quotes=[
            {"t":"2026-10-29T15:00:00.100000000Z","bp":100.,"ap":101.},
            {"t":"2026-10-29T15:00:00.500000000Z","bp":102.,"ap":101.}]
        trades=[
            {"t":"2026-10-29T15:00:00.099999999Z","p":100.,"s":7},
            {"t":"2026-10-29T15:00:00.100000000Z","p":100.,"s":10},
            {"t":"2026-10-29T15:00:00.100000001Z","p":101.,"s":100},
            {"t":"2026-10-29T15:00:00.300000000Z","p":100.,"s":40},
            {"t":"2026-10-29T15:00:00.700000000Z","p":101.,"s":20},
            {"t":"2026-10-29T15:00:01.800000000Z","p":100.,"s":5}]
        r=classify(trades,quotes)
        self.assertEqual(r["shares_by_class"]["BUY_INITIATED_ESTIMATE"],100)
        self.assertEqual(r["shares_by_class"]["SELL_INITIATED_ESTIMATE"],40)
        self.assertEqual(r["shares_by_class"]["UNKNOWN"],42)
        self.assertEqual(r["unknown_reasons"]["NO_PRIOR_QUOTE"],2)
        self.assertEqual(r["unknown_reasons"]["BAD_SPREAD"],1)
        self.assertEqual(r["unknown_reasons"]["STALE_QUOTE"],1)
        self.assertEqual(sum(r["counts_by_class"].values()),6)
        self.assertEqual(sum(r["shares_by_class"].values()),182)

    def test_inside_spread_has_separate_low_confidence(self):
        quotes=[{"t":"2026-10-29T15:00:00.000000100Z",
                 "bp":100.,"ap":102.}]
        trades=[
            {"t":"2026-10-29T15:00:00.000000200Z","p":101.5,"s":2},
            {"t":"2026-10-29T15:00:00.000000300Z","p":100.5,"s":3},
            {"t":"2026-10-29T15:00:00.000000400Z","p":101.,"s":5},
            {"t":"2026-10-29T15:00:00.000000500Z","p":104.,"s":7}]
        r=classify(trades,quotes)
        self.assertEqual(r["counts_by_class"]["BUY_INITIATED_ESTIMATE_LOW_CONFIDENCE"],1)
        self.assertEqual(r["counts_by_class"]["SELL_INITIATED_ESTIMATE_LOW_CONFIDENCE"],1)
        self.assertEqual(r["counts_by_class"]["UNKNOWN"],2)
        self.assertEqual(r["unknown_reasons"]["AT_MIDPOINT"],1)
        self.assertEqual(r["unknown_reasons"]["TRADE_OUTSIDE_SPREAD"],1)

    def test_drift_pair_partition_is_exact(self):
        f,events,_=synthetic_data()
        result=collect_drift(f,events,2025)
        self.assertGreater(result["features"]["num_test"],100)
        for pair in result["pair_signal_contrasts"].values():
            self.assertEqual(
                sum(pair[k]["candidate_signal_days"]
                    for k in ("both_signal","added_by_volume",
                              "removed_by_volume","neither_signal")),
                pair["same_cohort_days"])


if __name__=="__main__":
    unittest.main()
