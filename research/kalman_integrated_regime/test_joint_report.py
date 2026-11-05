"""Contract tests for sharded joint-policy aggregation and fail-closed gates."""
import json
from pathlib import Path
import tempfile
import unittest

from research.kalman_integrated_regime.joint_policy import (
    BASELINE, generate_policies, policy_id,
)
from research.kalman_integrated_regime.joint_report import aggregate


class AggregateContracts(unittest.TestCase):
    @staticmethod
    def files(folder, n=8, shards=2):
        policies = generate_policies(n, seed=42)
        files = []
        for shard in range(shards):
            rows = []
            for i, p in enumerate(policies):
                if i % shards != shard:
                    continue
                for year in (2025, 2026):
                    for model in ("price_only", "integrated_regime"):
                        rows.append({
                            "config_index": i, "policy_id": policy_id(p),
                            "year": year, "model": model, "params": p,
                            "return_pct": -5 + i,
                            "mdd_daily_mark_pct": -20.,
                            "trades": 25,
                        })
            path = Path(folder) / f"joint_shard_{shard}.json"
            path.write_text(json.dumps({
                "configs_total": n, "shard": shard, "shards": shards,
                "full_factorial_count": 200000,
                "pairwise_coverage": {"covered": 10,"possible": 100, "fraction": .1},
                "rows": rows}))
            files.append(path)
        return files

    def test_full_joint_aggregation(self):
        with tempfile.TemporaryDirectory() as temp:
            fs = self.files(temp)
            report = aggregate(fs, 8)
            self.assertEqual(report["total_portfolio_simulations"], 32)
            self.assertEqual(report["configs_evaluated"], 8)
            self.assertTrue(report["hold_live"])
            self.assertEqual(report["baseline_return_pct"]["2025_integrated_regime"], -5)
            self.assertEqual(report["rankings"]["integrated_regime"]["qualified_count"], 8)
            self.assertEqual(report["rankings"]["integrated_regime"]["top_exploratory_by_worst_year"][0]["config_index"], 7)

    def test_missing_shard_is_hard_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            fs = self.files(temp)
            with self.assertRaisesRegex(ValueError, "NOT_ALL_SHARDS_PRESENT"):
                aggregate(fs[:1], 8)

    def test_duplicate_rows_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            fs = self.files(temp)
            data = json.loads(fs[0].read_text())
            data["rows"].append(data["rows"][0])
            fs[0].write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "MISSING_CONFIG_MODEL_YEAR_ROWS"):
                aggregate(fs, 8)


if __name__=="__main__":
    unittest.main()
