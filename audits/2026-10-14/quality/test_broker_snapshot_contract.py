import unittest
from broker_snapshot_contract import validate

NOW = "2026-10-14T12:31:00Z"


class SnapshotContract(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "captured_at": "2026-10-14T12:30:00Z",
            "holdings": [{"symbol": "LRCX", "quantity": "0.049034"}],
            "open_orders": [],
        }

    def check(self, data):
        return validate(data, now=NOW)

    def test_valid(self):
        self.assertEqual(self.check(self.payload), [])

    def test_missing_capture(self):
        self.assertIn("INVALID_CAPTURE_TIME", self.check({**self.payload, "captured_at": None}))

    def test_missing_orders(self):
        data = dict(self.payload)
        del data["open_orders"]
        self.assertIn("OPEN_ORDERS_NOT_LIST", self.check(data))

    def test_bad_holding(self):
        data = {**self.payload, "holdings": [{"symbol": "LRCX", "quantity": "bad"}]}
        self.assertIn("INVALID_HOLDING", self.check(data))

    def test_nonfinite_holdings(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                data = {**self.payload, "holdings": [{"symbol": "LRCX", "quantity": value}]}
                self.assertIn("INVALID_HOLDING", self.check(data))

    def test_stale_snapshot(self):
        data = {**self.payload, "captured_at": "2026-10-14T12:25:59Z"}
        self.assertIn("STALE_BROKER_SNAPSHOT", self.check(data))

    def test_exact_age_boundary_is_valid(self):
        data = {**self.payload, "captured_at": "2026-10-14T12:26:00Z"}
        self.assertEqual(self.check(data), [])

    def test_future_snapshot(self):
        data = {**self.payload, "captured_at": "2026-10-14T12:31:31Z"}
        self.assertIn("FUTURE_BROKER_SNAPSHOT", self.check(data))

    def test_naive_timestamp_rejected(self):
        data = {**self.payload, "captured_at": "2026-10-14T12:30:00"}
        self.assertIn("INVALID_CAPTURE_TIME", self.check(data))

    def test_timezone_offset_supported(self):
        data = {**self.payload, "captured_at": "2026-10-14T21:30:00+09:00"}
        self.assertEqual(self.check(data), [])

    def test_bad_evaluation_time(self):
        self.assertIn("INVALID_EVALUATION_TIME", validate(self.payload, now="bad"))

    def test_invalid_bounds(self):
        self.assertIn("INVALID_TIME_BOUNDS", validate(self.payload, now=NOW, max_age_seconds=-1))


if __name__ == "__main__":
    unittest.main()
