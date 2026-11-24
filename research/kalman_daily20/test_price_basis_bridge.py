"""26-asset price-basis bridge: reconciliation is not source certification."""
import csv
import gzip
from hashlib import sha256
import io
import tempfile
from pathlib import Path
import unittest

from daily20 import load_spec
from price_basis_bridge import compare, read_yahoo_trace

SESSION = "2026-11-20"
SPEC = load_spec()
EQUITIES = [n for n in SPEC["core"] + SPEC["context"] if n != "^VIX"]
ALL = SPEC["core"] + SPEC["context"]


def fake_reports(base, *, factor_coverage=25):
    source = []
    venue = []
    factors = []
    for name in ALL:
        is_vix = name == "^VIX"
        row = {
            "symbol": name, "session": SESSION,
            "yahoo_close": 35.89 if is_vix else 98.0,
            "yahoo_is_adjusted": not is_vix,
            "source_parquet_sha256": "a" * 64,
            "reference_price": 35.89 if is_vix else 101.0,
            "reference_type": "REGULAR_CLOSE",
            "reference_provider": "Cboe" if is_vix else "Alpaca",
            "reference_feed": "Index" if is_vix else "SIP_MarketCenterOfficialClose_M",
            "reference_adjustment": "RAW",
        }
        source.append(row)
        if is_vix:
            continue
        venue.append({
            "symbol": name,
            "selected_primary_raw_M_price": 101.0,
            "selected_primary_venue_code": "Q",
            "asset_metadata_sha256": "b" * 64,
        })
        factor = {"symbol": name, "status": "YAHOO_FACTOR_OBSERVED_UNATTESTED"}
        if EQUITIES.index(name) < factor_coverage:
            buf = io.StringIO(newline="")
            writer = csv.DictWriter(buf, fieldnames=[
                "session", "yahoo_close_split_adjusted",
                "yahoo_adj_close", "yahoo_adj_over_close"])
            writer.writeheader()
            writer.writerow({
                "session": SESSION,
                "yahoo_close_split_adjusted": "100.0",
                "yahoo_adj_close": "98.0",
                "yahoo_adj_over_close": "0.98",
            })
            original = buf.getvalue().encode()
            fn = name.lower() + ".csv.gz"
            (base / fn).write_bytes(gzip.compress(original, mtime=0))
            factor.update({
                "csv_gzip_file": fn,
                "serialized_csv_sha256": sha256(original).hexdigest(),
            })
        factors.append(factor)
    return (
        {
            "version": "daily20-source-finality-v1",
            "session": SESSION, "verified": 0, "research_hold": True,
            "production_writes": False,
            "symbols": source,
        },
        {
            "version": "daily20-primary-listing-evidence-v1",
            "session": SESSION, "finality_verified": 0,
            "raw_and_yahoo_adjusted_directly_comparable": False,
            "primary_session_asof_independently_certified": False,
            "rows": venue,
        },
        {
            "version": "daily20-yahoo-factor-lineage-v2",
            "session": SESSION, "finality_verified": 0,
            "independent_corporate_actions_certified": 0,
            "required": 25, "rows": factors,
        },
    )


class BasisBridgeContracts(unittest.TestCase):
    def test_26_all_explicit_bases_and_no_certification(self):
        with tempfile.TemporaryDirectory() as d:
            src, venue, factor = fake_reports(Path(d))
            result = compare(SPEC, src, venue, factor, d)
            self.assertEqual(result["required_assets"], 26)
            self.assertEqual(result["raw_primary_M_auction_reference_count"], 25)
            self.assertEqual(result["vendor_unrepaired_trace_count"], 25)
            self.assertEqual(result["research_price_certified"], 0)
            self.assertEqual(result["independent_adjustment_factors_certified"], 0)
            self.assertEqual(result["same_session_model_vendor_adj_close_mismatches_gt_half_cent"], 0)
            spy = next(r for r in result["rows"] if r["symbol"] == "SPY")
            self.assertEqual(spy["raw_primary_M_auction_price"], 101)
            self.assertEqual(spy["vendor_unrepaired_split_adjusted_close"], 100)
            self.assertEqual(spy["vendor_unrepaired_dividend_adjusted_close"], 98)
            self.assertEqual(spy["model_input_auto_adjust_close"], 98)
            self.assertEqual(spy["vendor_unrepaired_adj_over_close"], 0.98)
            self.assertEqual(spy["research_raw_M_minus_vendor_close_usd"], 1)
            self.assertFalse(spy["independent_price_certified"])
            vix = next(r for r in result["rows"] if r["symbol"] == "^VIX")
            self.assertFalse(vix["model_input_adjusted"])
            self.assertIsNone(vix["vendor_unrepaired_adj_over_close"])
            self.assertEqual(vix["basis_reconciliation"], "VIX_INDEX_NO_CORPORATE_ACTION_FACTOR")
            self.assertTrue(all(r["research_hold"] for r in result["rows"]))

    def test_primary_auction_vs_source_must_match_before_research_diff(self):
        with tempfile.TemporaryDirectory() as d:
            src, venue, factor = fake_reports(Path(d))
            venue["rows"][0]["selected_primary_raw_M_price"] = 111.0
            with self.assertRaisesRegex(ValueError, "CROSS_REPORT_PRICE_CONFLICT"):
                compare(SPEC, src, venue, factor, d)

    def test_vendor_trace_bytes_integrity_is_hard_gate(self):
        with tempfile.TemporaryDirectory() as d:
            src, venue, factor = fake_reports(Path(d))
            path = Path(d) / "spy.csv.gz"
            path.write_bytes(gzip.compress(b"tampered,csv\n", mtime=0))
            with self.assertRaisesRegex(ValueError, "SHA256_MISMATCH"):
                compare(SPEC, src, venue, factor, d)

    def test_missing_vendor_reference_remains_hold_not_factor_proof(self):
        with tempfile.TemporaryDirectory() as d:
            src, venue, factor = fake_reports(Path(d), factor_coverage=24)
            result = compare(SPEC, src, venue, factor, d)
            self.assertEqual(result["vendor_unrepaired_trace_count"], 24)
            self.assertEqual(result["research_price_certified"], 0)
            omitted = EQUITIES[24]
            row = next(r for r in result["rows"] if r["symbol"] == omitted)
            self.assertEqual(row["vendor_trace_status"], "YAHOO_VENDOR_TRACE_UNAVAILABLE_HOLD")
            self.assertIsNone(row["vendor_unrepaired_adj_over_close"])

    def test_missing_raw_venue_is_not_filled_by_yahoo(self):
        with tempfile.TemporaryDirectory() as d:
            src, venue, factor = fake_reports(Path(d))
            venue["rows"][0]["selected_primary_raw_M_price"] = None
            src["symbols"][0]["reference_price"] = None
            result = compare(SPEC, src, venue, factor, d)
            self.assertEqual(result["raw_primary_M_auction_reference_count"], 24)
            self.assertEqual(result["rows"][0]["basis_reconciliation"],
                             "VENDOR_ONLY_NO_RAW_REFERENCE_HOLD")
            self.assertFalse(result["rows"][0]["independent_price_certified"])

    def test_vendor_repair_disagreement_is_only_diagnostic(self):
        with tempfile.TemporaryDirectory() as d:
            src, venue, factor = fake_reports(Path(d))
            src["symbols"][0]["yahoo_close"] = 99.0
            result = compare(SPEC, src, venue, factor, d)
            self.assertEqual(result["same_session_model_vendor_adj_close_mismatches_gt_half_cent"], 1)
            self.assertIn("MODEL_REPAIR_DIFFERENCE_POSSIBLE",
                          result["rows"][0]["basis_reconciliation"])
            self.assertEqual(result["research_price_certified"], 0)

    def test_wrong_issuer_source_session_cannot_be_joined(self):
        with tempfile.TemporaryDirectory() as d:
            src, venue, factor = fake_reports(Path(d))
            factor["session"] = "2026-11-19"
            with self.assertRaisesRegex(ValueError, "SESSION_MISMATCH"):
                compare(SPEC, src, venue, factor, d)

    def test_duplicate_source_symbol_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            src, venue, factor = fake_reports(Path(d))
            src["symbols"][-1] = dict(src["symbols"][0])
            with self.assertRaisesRegex(ValueError, "SYMBOL_DUPLICATED_OR_UNKNOWN"):
                compare(SPEC, src, venue, factor, d)

    def test_adjusted_reference_is_not_used_as_raw_M(self):
        with tempfile.TemporaryDirectory() as d:
            src, venue, factor = fake_reports(Path(d))
            src["symbols"][0]["reference_adjustment"] = "YAHOO_AUTO_ADJUSTED"
            with self.assertRaisesRegex(ValueError, "WRONG_BASIS"):
                compare(SPEC, src, venue, factor, d)

    def test_trace_filename_traversal_disallowed(self):
        with tempfile.TemporaryDirectory() as d:
            src, venue, factor = fake_reports(Path(d))
            factor["rows"][0]["csv_gzip_file"] = "../secret.csv.gz"
            with self.assertRaisesRegex(ValueError, "UNEXPECTED_VENDOR_TRACE_FILENAME"):
                compare(SPEC, src, venue, factor, d)

    def test_bad_price_and_bad_ratio_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            src, venue, factor = fake_reports(Path(d))
            src["symbols"][0]["yahoo_close"] = -1
            with self.assertRaisesRegex(ValueError, "MODEL_PRICE_INVALID"):
                compare(SPEC, src, venue, factor, d)
            src["symbols"][0]["yahoo_close"] = 98
            original = ("session,yahoo_close_split_adjusted,yahoo_adj_close,yahoo_adj_over_close\n"
                        "2026-11-20,100,98,0.99\n").encode()
            (Path(d) / "spy.csv.gz").write_bytes(gzip.compress(original, mtime=0))
            factor["rows"][0]["serialized_csv_sha256"] = sha256(original).hexdigest()
            with self.assertRaisesRegex(ValueError, "RATIO_NOT_SELF_CONSISTENT"):
                compare(SPEC, src, venue, factor, d)


if __name__ == "__main__":
    unittest.main()
