from __future__ import annotations

import unittest
from pathlib import Path


class V2ShadowScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.cron = (cls.root / "config/kalman.cron.d").read_text(encoding="utf-8")
        cls.runner = (cls.root / "scripts/run_v2_shadow_refresh.sh").read_text(encoding="utf-8")

    def test_fixed_model_runner_never_retrains(self) -> None:
        self.assertIn("run_shadow_v2.sh", self.runner)
        self.assertNotIn("run_model_v2_research.sh", self.runner)

    def test_refresh_remains_isolated_while_live_trading_is_active(self) -> None:
        self.assertIn("SHADOW_ISOLATED_FROM_LIVE_TRADING", self.runner)
        self.assertIn("continuing isolated fixed-model V2 SHADOW refresh", self.runner)
        self.assertNotIn(
            "TRADING_ENABLED=true; refuse scheduled V2 SHADOW refresh",
            self.runner,
        )
        self.assertNotIn(
            "LIVE_TRADING_CONFIRM is set; refuse scheduled V2 SHADOW refresh",
            self.runner,
        )
        self.assertNotIn("run_auto_trade.sh", self.runner)
        self.assertNotIn("run_us_cycle.sh", self.runner)
        self.assertNotIn("toss", self.runner.lower())

    def test_cron_has_exactly_two_active_v2_shadow_refresh_jobs(self) -> None:
        active = [
            line.strip()
            for line in self.cron.splitlines()
            if line.strip()
            and not line.lstrip().startswith("#")
            and "run_v2_shadow_refresh.sh" in line
        ]
        self.assertEqual(len(active), 2)

    def test_kr_close_schedule(self) -> None:
        self.assertIn(
            "50 16 * * 1-5 root /opt/kalman/app/scripts/run_v2_shadow_refresh.sh "
            "--mirror-neon --skip-finviz",
            self.cron,
        )

    def test_us_close_schedule(self) -> None:
        self.assertIn(
            "30 7 * * 2-6 root /opt/kalman/app/scripts/run_v2_shadow_refresh.sh "
            "--mirror-neon",
            self.cron,
        )

    def test_cron_never_retrains_model_v2(self) -> None:
        active = [
            line.strip()
            for line in self.cron.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertTrue(all("run_model_v2_research.sh" not in line for line in active))


if __name__ == "__main__":
    unittest.main()
