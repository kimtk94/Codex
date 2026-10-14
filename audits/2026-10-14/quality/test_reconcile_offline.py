import unittest
from reconcile_offline import reconcile

NOW = "2026-10-14T12:31:00Z"
MIRROR_AS_OF = "2026-10-14T12:30:05Z"


class TestReconcile(unittest.TestCase):
    def setUp(self):
        self.mirror = [{"symbol": "LRCX", "state": "OPEN",
                        "remaining_quantity": "0.049034"}]
        self.broker = {
            "captured_at": "2026-10-14T12:30:00Z",
            "holdings": [{"symbol": "LRCX", "quantity": "0.049034"}],
            "open_orders": [],
        }

    def check(self, mirror=None, broker=None, **kwargs):
        return reconcile(self.mirror if mirror is None else mirror,
                         self.broker if broker is None else broker,
                         mirror_as_of=kwargs.pop("mirror_as_of", MIRROR_AS_OF),
                         now=kwargs.pop("now", NOW), **kwargs)

    def test_no_broker(self):
        self.assertEqual(reconcile(self.mirror, None)["status"], "UNKNOWN")

    def test_missing_orders(self):
        b = dict(self.broker)
        del b["open_orders"]
        self.assertEqual(self.check(broker=b)["status"], "UNKNOWN")

    def test_holdings_match_not_full_pass(self):
        self.assertEqual(self.check()["status"], "HOLDINGS_MATCH")

    def test_submitted_lifecycle_pending(self):
        self.assertEqual(self.check(expected_submitted=21)["status"], "PARTIAL")

    def test_open_orders_pending(self):
        b = {**self.broker, "open_orders": [{"symbol": "LRCX", "side": "BUY"}]}
        result = self.check(broker=b)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["reason"], "BROKER_OPEN_ORDERS_UNRECONCILED")

    def test_mismatch(self):
        b = {**self.broker, "holdings": [{"symbol": "LRCX", "quantity": "0.04"}]}
        self.assertEqual(self.check(broker=b)["status"], "MISMATCH")

    def test_duplicate_broker_holding(self):
        b = {**self.broker, "holdings": self.broker["holdings"] * 2}
        self.assertEqual(self.check(broker=b)["status"], "UNKNOWN")

    def test_duplicate_mirror_position(self):
        self.assertEqual(self.check(mirror=self.mirror * 2)["status"], "UNKNOWN")

    def test_invalid_mirror_quantity(self):
        m = [{**self.mirror[0], "remaining_quantity": "NaN"}]
        self.assertEqual(self.check(mirror=m)["status"], "UNKNOWN")

    def test_missing_capture_time(self):
        b = {**self.broker, "captured_at": None}
        self.assertEqual(self.check(broker=b)["status"], "UNKNOWN")

    def test_missing_mirror_timestamp(self):
        self.assertEqual(self.check(mirror_as_of=None)["reason"],
                         "MIRROR_TIMESTAMP_MISSING")

    def test_stale_mirror_timestamp(self):
        self.assertEqual(self.check(mirror_as_of="2026-10-14T12:20:00Z")["reason"],
                         "STALE_MIRROR_SNAPSHOT")

    def test_future_mirror_timestamp(self):
        self.assertEqual(self.check(mirror_as_of="2026-10-14T12:31:31Z")["reason"],
                         "FUTURE_MIRROR_SNAPSHOT")

    def test_stale_broker_snapshot(self):
        b = {**self.broker, "captured_at": "2026-10-14T12:20:00Z"}
        result = self.check(broker=b)
        self.assertEqual(result["reason"], "INVALID_BROKER_SNAPSHOT")
        self.assertIn("STALE_BROKER_SNAPSHOT", result["errors"])

    def test_snapshot_time_skew(self):
        b = {**self.broker, "captured_at": "2026-10-14T12:25:50Z"}
        self.assertEqual(self.check(broker=b)["reason"], "SNAPSHOT_TIME_SKEW")

    def test_bad_submitted_count(self):
        self.assertEqual(self.check(expected_submitted=-1)["reason"],
                         "INVALID_SUBMITTED_COUNT")

    def test_invalid_tolerance(self):
        self.assertEqual(self.check(tolerance="NaN")["reason"],
                         "INVALID_TOLERANCE")


if __name__ == "__main__":
    unittest.main()
