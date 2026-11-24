"""No-network reproducibility, baseline isolation and truly joint 40-axis random proposals."""
import unittest
from research.kalman_integrated_regime.joint_policy import AXES, BASELINE, policy_id, policy_valid
from research.kalman_integrated_regime.random_10k import uniform_random_policies


class Random10KContracts(unittest.TestCase):
    def test_exactly_ten_thousand_random_plus_one_control(self):
        policies, audit = uniform_random_policies(10000, seed=20261101)
        self.assertEqual(len(AXES), 40)
        self.assertEqual(len(policies), 10001)
        self.assertEqual(audit["random_candidates_accepted"], 10000)
        self.assertEqual(audit["additional_unrandomized_baseline"], 1)
        self.assertTrue(audit["outcome_blind"])
        self.assertEqual(policies[0], BASELINE)
        self.assertEqual(len({policy_id(p) for p in policies}), 10001)
        self.assertTrue(all(policy_valid(p) for p in policies))
        # Every axis appears with at least two different effective values.
        for axis in AXES:
            with self.subTest(axis=axis):
                self.assertGreater(len({p[axis] for p in policies[1:]}), 1)
        # This is an unfiltered random search, not a return-optimized list.
        self.assertGreater(sum(p["confidence"] >= .6 for p in policies[1:]), 100)
        self.assertGreater(sum(p["split"] != "single" for p in policies[1:]), 500)

    def test_reproducible_not_baseline_greedy(self):
        a, report_a = uniform_random_policies(150, seed=11)
        b, report_b = uniform_random_policies(150, seed=11)
        c, _ = uniform_random_policies(150, seed=12)
        self.assertEqual(a, b)
        self.assertEqual(report_a, report_b)
        self.assertNotEqual(a[1], c[1])
        self.assertTrue(any(sum(p[k] != BASELINE[k] for k in AXES) > 15
                            for p in a[1:]))


if __name__ == "__main__":
    unittest.main()
