import unittest
from fresh_incident_lineage import assert_hold

class FreshLineageHoldTests(unittest.TestCase):
    def setUp(self):
        self.base = {
            "research_only": True, "production_writes": False,
            "strategy_promoted": False, "cache_reuse_authorized": False,
            "issuer_payments_certified": 0, "source_finality_verified": 0,
            "official_price_close_certified": 0,
            "independent_adjustment_factor_certified": 0,
        }
    def test_valid_hold(self):
        self.assertIs(assert_hold(self.base), self.base)
    def test_no_payment_certification(self):
        x = dict(self.base, issuer_payments_certified=1)
        with self.assertRaisesRegex(ValueError, "CERTIFICATION"):
            assert_hold(x)
    def test_no_source_finality(self):
        x = dict(self.base, source_finality_verified=1)
        with self.assertRaisesRegex(ValueError, "CERTIFICATION"):
            assert_hold(x)
    def test_no_price_close_promotion(self):
        x = dict(self.base, official_price_close_certified=1)
        with self.assertRaisesRegex(ValueError, "PRICE_PROMOTION"):
            assert_hold(x)
    def test_no_cache_or_strategy_promotion(self):
        x = dict(self.base, cache_reuse_authorized=True)
        with self.assertRaisesRegex(ValueError, "GOVERNANCE"):
            assert_hold(x)
        y = dict(self.base, strategy_promoted=True)
        with self.assertRaisesRegex(ValueError, "GOVERNANCE"):
            assert_hold(y)

if __name__ == "__main__":
    unittest.main()
