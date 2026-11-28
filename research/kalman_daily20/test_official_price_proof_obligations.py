"""Offline proof-matrix contracts; never call market/broker/issuer APIs."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from official_price_proof_obligations import build, run

SESSION = "2026-11-20"
CORE = ["SPY", "QQQ", "QLD", "IWM", "AAPL", "MSFT", "AMZN", "GOOGL",
        "META", "NVDA", "AMD", "AVGO", "MU", "TSLA", "PLTR", "IONQ",
        "COIN", "MSTR", "JPM", "XOM"]
CONTEXT = ["SMH", "^VIX", "HYG", "LQD", "TLT", "GLD"]
NAMES = CORE + CONTEXT
DIGEST = "a" * 64


def fixture():
    spec = {"core": CORE, "context": CONTEXT}
    source = {
        "version": "daily20-source-finality-v1", "session": SESSION,
        "research_only": True, "production_writes": False,
        "strategy_promoted": False, "research_hold": True,
        "external_regular_close_independent_certified": False,
        "verified": 0, "required": 26, "symbols": [],
    }
    bridge = {
        "version": "daily20-price-basis-bridge-v1", "session": SESSION,
        "research_only": True, "production_writes": False,
        "strategy_promoted": False, "research_price_certified": 0,
        "independent_adjustment_factors_certified": 0, "required_assets": 26,
        "rows": [],
    }
    actions = {
        "version": "daily20-corporate-action-crosscheck-v1",
        "session": SESSION, "research_only": True,
        "production_writes": False, "strategy_promoted": False,
        "finality_verified": 0, "independent_factor_certification": 0,
        "required": 25, "symbols": [],
    }
    gaps = {
        "version": "daily20-issuer-ca-gap-audit-v1", "research_only": True,
        "production_writes": False, "strategy_promoted": False,
        "source_finality_verified": 0, "issuer_payments_certified": 0,
        "status": "ISSUER_DISTRIBUTIONS_2_EVENTS_HOLD",
        "events": [{
            "symbol": ticker, "ex_date": exdate,
            "actual_payment_certified": False,
            "independent_adjustment_factor_certified": False,
            "independent_close_certified": False, "research_hold": True,
        } for ticker, exdate in
            [("QQQ", "2018-06-18"), ("QLD", "2023-09-20")]],
    }
    for name in NAMES:
        index = name == "^VIX"
        source["symbols"].append({
            "symbol": name, "session": SESSION,
            "group": "CORE_20" if name in CORE else "CONTEXT_6",
            "source_parquet_sha256": DIGEST,
            "reference_certified": False, "finality_verified": False,
            "reference_price": 20.5 if index else 100.0,
            "reference_provider": "Cboe" if index else "Alpaca",
        })
        bridge["rows"].append({
            "symbol": name, "session": SESSION,
            "group": "CORE_20" if name in CORE else "CONTEXT_6",
            "model_parquet_sha256": DIGEST,
            "research_hold": True, "independent_price_certified": False,
            "independent_adjustment_factor_certified": False,
            "model_input_adjusted": not index,
            "raw_primary_M_auction_price": None if index else 100.0,
            "vendor_unrepaired_adj_over_close": None if index else 0.99,
        })
        if not index:
            actions["symbols"].append({
                "symbol": name, "status": "RESEARCH_UNCERTIFIED",
                "factor_independently_certified": False,
            })
    return spec, source, bridge, actions, gaps


class ProofMatrixTest(unittest.TestCase):
    def setUp(self):
        self.inputs = fixture()

    def evaluate(self, inputs=None):
        return build(*(inputs or self.inputs),
                     input_sha256={"config": DIGEST, "source": DIGEST,
                                   "bridge": DIGEST, "actions": DIGEST,
                                   "gaps": DIGEST})

    def test_exact_26_25_and_two_independent_cash_gaps(self):
        report = self.evaluate()
        self.assertEqual(report["required_assets"], 26)
        self.assertEqual(report["independent_factor_applicable"], 25)
        self.assertEqual(report["official_close_certified"], 0)
        self.assertEqual(report["independent_factor_certified"], 0)
        self.assertEqual(report["issuer_specific_cash_gaps"], 2)
        self.assertEqual(report["primary_M_observed"], 25)
        self.assertTrue(all(row["status"].endswith("HOLD") for row in report["rows"]))
        self.assertEqual(report["rows"][1]["issuer_cash_gap"], "2018-06-18")
        self.assertEqual(report["rows"][2]["issuer_cash_gap"], "2023-09-20")

    def test_equity_close_obligation_is_early_close_aware(self):
        rows = self.evaluate()["rows"]
        equities = [row for row in rows if row["asset_type"] == "EQUITY_OR_ETF"]
        self.assertEqual(len(equities), 25)
        for row in equities:
            self.assertIn("CERTIFIED_XNYS_SCHEDULED_REGULAR_CLOSE_NOT_JUST_M_PRINT",
                          row["required_evidence"])
            self.assertNotIn("CERTIFIED_REGULAR_16_ET_CLOSE_NOT_JUST_M_PRINT",
                             row["required_evidence"])

    def test_vix_no_equity_corporate_factor(self):
        rows = self.evaluate()["rows"]
        vix = next(x for x in rows if x["symbol"] == "^VIX")
        self.assertIsNone(vix["factor_certified"])
        self.assertFalse(vix["primary_M_observed"])
        self.assertEqual(vix["asset_type"], "CBOE_INDEX")
        self.assertEqual(vix["close_reference_grade"], "CBOE_INDEX_PUBLICATION_UNCERTIFIED")
        self.assertNotIn("ISSUER_VERIFIED_SPLIT_AND_CASH_DISTRIBUTION_FACTOR_CHAIN",
                         vix["required_evidence"])

    def test_reject_duplicate_source_symbol(self):
        data = deepcopy(self.inputs)
        data[1]["symbols"][1] = deepcopy(data[1]["symbols"][0])
        with self.assertRaisesRegex(ValueError, "DUPLICATE_OR_UNKNOWN"):
            self.evaluate(data)

    def test_reject_missing_corporate_action_asset(self):
        data = deepcopy(self.inputs)
        data[3]["symbols"].pop()
        with self.assertRaisesRegex(ValueError, "PROOF_ACTION_COVERAGE_COUNT"):
            self.evaluate(data)

    def test_reject_different_session(self):
        data = deepcopy(self.inputs)
        data[3]["session"] = "2026-11-23"
        with self.assertRaisesRegex(ValueError, "SOURCE_SESSION_MISMATCH"):
            self.evaluate(data)

    def test_reject_primary_source_false_certification(self):
        data = deepcopy(self.inputs)
        data[1]["verified"] = 1
        with self.assertRaisesRegex(ValueError, "FALSE_CERTIFICATION"):
            self.evaluate(data)

    def test_reject_factor_self_attestation(self):
        data = deepcopy(self.inputs)
        data[3]["symbols"][0]["factor_independently_certified"] = True
        with self.assertRaisesRegex(ValueError, "CA_ROW_FALSE_ATTESTATION"):
            self.evaluate(data)

    def test_reject_claimed_first_party_cash_payout(self):
        data = deepcopy(self.inputs)
        data[4]["events"][0]["actual_payment_certified"] = True
        with self.assertRaisesRegex(ValueError, "ISSUER_EVENT_UNVERIFIED"):
            self.evaluate(data)

    def test_reject_vix_as_stock_factor(self):
        data = deepcopy(self.inputs)
        vix = next(x for x in data[2]["rows"] if x["symbol"] == "^VIX")
        vix["vendor_unrepaired_adj_over_close"] = 1.01
        with self.assertRaisesRegex(ValueError, "VIX_STOCK_ADJUSTMENT_FORBIDDEN"):
            self.evaluate(data)

    def test_reject_tampered_price_source_identity(self):
        data = deepcopy(self.inputs)
        data[2]["rows"][0]["model_parquet_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "ROW_IDENTITY"):
            self.evaluate(data)

    def test_outputs_are_hashed_deterministic_and_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            files = []
            for key, item in zip(("config", "source", "bridge", "actions", "gaps"),
                                 self.inputs):
                p = root / (key + ".json")
                p.write_text(json.dumps(item), encoding="utf-8")
                files.append(p)
            first = run(*files, root / "out")
            csv_path = root / "out" / "evidence_obligations.csv"
            digest = sha256(csv_path.read_bytes()).hexdigest()
            self.assertEqual(first["evidence_obligations_csv_sha256"], digest)
            self.assertEqual(first["input_sha256"]["source"],
                             sha256(files[1].read_bytes()).hexdigest())
            self.assertEqual(len(csv_path.read_text().splitlines()), 27)
            self.assertEqual(first["status"], "OFFICIAL_CLOSE_AND_FACTOR_RESEARCH_HOLD")
            again = run(*files, root / "out")
            self.assertEqual(first, again)
            self.assertTrue(all(item["factor_certified"] is False
                                for item in again["rows"] if item["symbol"] != "^VIX"))


if __name__ == "__main__":
    unittest.main()
