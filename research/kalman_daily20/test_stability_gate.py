"""Offline tests for the research-only Daily20 provenance HOLD gate."""
import unittest

from stability_gate import VERSION, classify


def snapshot(*, bull=.72, bear=.34, rule=False, feature="a" * 64):
    def model(p, candidate):
        return {"probability": p, "candidate": candidate}
    return {
        "schema": VERSION,
        "session": "2026-11-20",
        "models": {"SPY": {
            "ohlcv": {"close": 100.0},
            "feature_sha256": feature,
            "scored": {
                "BULL_LOGISTIC": model(bull, bull >= .7),
                "BEAR_LOGISTIC": model(bear, bear >= .7),
                "BEAR_RULE": model(None, rule),
            },
            "models": {
                "BULL_LOGISTIC": {
                    "training_hash": "train1", "fitted_model_hash": "coeff1"
                },
                "BEAR_LOGISTIC": {
                    "training_hash": "train2", "fitted_model_hash": "coeff2"
                },
            },
        }},
    }


class StabilityGateTests(unittest.TestCase):
    def test_identical_inputs_do_not_raise_hold(self):
        left = snapshot()
        rows, hold = classify(left, snapshot())
        self.assertEqual(rows, [])
        self.assertFalse(hold)

    def test_probability_change_over_one_percentage_point_holds(self):
        rows, hold = classify(snapshot(), snapshot(bull=.731))
        self.assertTrue(hold)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["family"], "BULL_LOGISTIC")
        self.assertAlmostEqual(rows[0]["probability_delta_pp"], 1.1)

    def test_one_pp_exact_not_hold(self):
        rows, hold = classify(snapshot(), snapshot(bull=.73))
        self.assertFalse(hold)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["research_hold"])

    def test_candidate_flip_holds_regardless_probability_magnitude(self):
        left, right = snapshot(rule=False), snapshot(rule=True)
        rows, hold = classify(left, right)
        self.assertTrue(hold)
        self.assertEqual(rows[0]["family"], "BEAR_RULE")
        self.assertTrue(rows[0]["candidate_flip"])

    def test_asof_feature_revision_below_threshold_is_advisory(self):
        rows, hold = classify(snapshot(), snapshot(feature="b" * 64))
        self.assertFalse(hold)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(x["asof_input_changed"] for x in rows))
        self.assertFalse(any(x["research_hold"] for x in rows))

    def test_missing_probability_is_hold(self):
        rows, hold = classify(snapshot(bear=.34), snapshot(bear=None))
        self.assertTrue(hold)
        self.assertTrue(rows[0]["probability_missing_changed"])


if __name__ == "__main__":
    unittest.main()
