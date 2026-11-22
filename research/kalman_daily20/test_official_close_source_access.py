"""Offline regression contracts for primary publisher route and VIX recheck."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import gzip
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from official_close_source_access import build, recheck_cboe, run
from official_price_proof_obligations import build as make_obligations
from test_official_price_proof_obligations import fixture as proof_fixture, DIGEST

SESSION = "2026-11-20"


def sample_csv(close="20.50"):
    last = date(2026, 11, 20)
    lines = ["DATE,OPEN,HIGH,LOW,CLOSE"]
    for i in range(999, -1, -1):
        day = last - timedelta(days=i)
        lines.append(f"{day:%m/%d/%Y},19,21,18,{close if i == 0 else '19.75'}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def fixture():
    spec, source, bridge, actions, gaps = proof_fixture()
    obligations = make_obligations(
        spec, source, bridge, actions, gaps,
        input_sha256={"source": DIGEST, "bridge": DIGEST,
                      "actions": DIGEST, "gaps": DIGEST, "config": DIGEST})
    independent = {
        "version": "daily20-independent-feed-diagnostics-v1",
        "research_only": True, "production_writes": False,
        "verified_regular_finality": 0, "session": SESSION,
        "cboe": {"status": "CBOE_OFFICIAL_VIX_HISTORY_PRESENT",
                 "provider": "Cboe", "index_admin_publication": True,
                 "body_sha256": DIGEST, "official_index_close": 20.5},
    }
    reference = {
        "schema": "daily20-quote-reference-v1",
        "session": SESSION, "quotes": [
            {"symbol": "^VIX", "provider": "Cboe",
             "feed": "VIX_Index_Historical_Daily_Close",
             "price": 20.5, "quote_type": "REGULAR_CLOSE",
             "adjustment": "RAW",
             "source_url": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
             "source_body_sha256": DIGEST,
             "independently_exchange_certified_at_16_00": False},
        ],
    }
    venues = ["NASDAQ", "NYSE", "NYSE_ARCA", "NYSE_AMERICAN", "CBOE_BZX"]
    equities = [x for x in spec["core"] + spec["context"] if x != "^VIX"]
    venue = {
        "version": "daily20-primary-listing-evidence-v1",
        "research_only": True, "production_writes": False,
        "session": SESSION, "finality_verified": 0, "rows": [],
    }
    for i, symbol in enumerate(equities):
        venue["rows"].append({
            "symbol": symbol, "session": SESSION,
            "primary_canonical": venues[i % len(venues)],
            "selected_primary_raw_M_price": 100.0,
            "session_primary_listing_certified": False,
            "primary_market_center_M_certified_as_consolidated_close": False,
            "direct_comparison_with_Yahoo_auto_adjust": False,
        })
    return spec, independent, reference, venue, obligations


class SourceAccessTest(unittest.TestCase):
    def setUp(self):
        self.docs = fixture()

    def report(self, docs=None, **kwargs):
        return build(*(docs or self.docs),
                     input_sha256={"config": DIGEST, "independent": DIGEST,
                                   "reference": DIGEST, "venue": DIGEST,
                                   "obligations": DIGEST}, **kwargs)

    def test_offline_has_26_routes_no_false_certification(self):
        r = self.report()
        self.assertEqual(len(r["rows"]), 26)
        self.assertEqual(r["official_close_certified"], 0)
        self.assertEqual(r["independent_corporate_factors_certified"], 0)
        self.assertEqual(r["equities_missing_primary_numeric_evidence"], 25)
        self.assertEqual(sum(r["access_route_counts"].values()), 25)
        self.assertTrue(all(not x["point_in_time_close_certified"] for x in r["rows"]))

    def test_vix_index_provenance_not_equity_adjustment(self):
        v = next(x for x in self.report()["rows"] if x["symbol"] == "^VIX")
        self.assertFalse(v["corporate_factor_applicable"])
        self.assertTrue(v["official_close_record_attached"])
        self.assertFalse(v["point_in_time_close_certified"])
        self.assertEqual(v["access_status"], "CBOE_RECHECK_NOT_RUN_OFFLINE_HOLD")

    def test_new_csv_same_value_new_hash_is_not_revision(self):
        r = self.report(recheck_attempted=True, cboe_raw=sample_csv())
        c = r["cboe_publisher_recheck"]
        self.assertTrue(c["same_session_value_unchanged"])
        self.assertNotEqual(c["original_response_sha256"], c["recheck_raw_sha256"])
        self.assertEqual(c["recheck_status"], "CBOE_TWO_CAPTURES_MATCH_PUBLISHER_ONLY_HOLD")

    def test_same_day_cboe_value_revision_marks_hold(self):
        r = self.report(recheck_attempted=True, cboe_raw=sample_csv("21.20"))
        c = r["cboe_publisher_recheck"]
        self.assertFalse(c["same_session_value_unchanged"])
        self.assertEqual(c["recheck_status"], "CBOE_HISTORICAL_PUBLISHER_REVISION_HOLD")
        self.assertEqual(r["official_close_certified"], 0)

    def test_cboe_network_missing_does_not_invent_published_quote(self):
        r = self.report(recheck_attempted=True, cboe_raw=None)
        self.assertEqual(r["cboe_publisher_recheck"]["recheck_status"],
                         "CBOE_RECHECK_NETWORK_UNAVAILABLE_HOLD")

    def test_reject_source_quote_digest_mismatch(self):
        d = deepcopy(self.docs)
        d[2]["quotes"][0]["source_body_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "ACCESS_CBOE_ANCHOR_CONFLICT"):
            self.report(d)

    def test_reject_wrong_session(self):
        d = deepcopy(self.docs)
        d[3]["session"] = "2026-11-19"
        with self.assertRaisesRegex(ValueError, "ACCESS_SESSION_CONFLICT"):
            self.report(d)

    def test_reject_fake_certification_from_upstream(self):
        d = deepcopy(self.docs)
        d[4]["official_close_certified"] = 26
        with self.assertRaisesRegex(ValueError, "ACCESS_FALSE_FINALITY_UPSTREAM"):
            self.report(d)

    def test_reject_current_master_fake_historical_cert(self):
        d = deepcopy(self.docs)
        d[3]["rows"][0]["session_primary_listing_certified"] = True
        with self.assertRaisesRegex(ValueError, "ACCESS_VENUE_REFERENCE_CONFLICT"):
            self.report(d)

    def test_unknown_exchange_does_not_guess_publisher(self):
        d = deepcopy(self.docs)
        d[3]["rows"][0]["primary_canonical"] = "NON_STANDARD"
        x = self.report(d)["rows"][0]
        self.assertEqual(x["access_status"], "UNKNOWN_CURRENT_PRIMARY_VENUE_HOLD")
        self.assertIsNone(x["source_url"])

    def test_reject_duplicate_venue_rows(self):
        d = deepcopy(self.docs)
        d[3]["rows"][0] = deepcopy(d[3]["rows"][1])
        with self.assertRaisesRegex(ValueError, "ACCESS_UNKNOWN_OR_DUPLICATE_SYMBOL"):
            self.report(d)

    def test_archive_cboe_raw_source_reproducible_with_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = []
            for name, payload in zip(("config", "independent", "reference", "venue", "obligations"),
                                     self.docs):
                f = root / (name + ".json")
                f.write_text(json.dumps(payload), encoding="utf-8")
                files.append(f)
            raw = sample_csv()
            def fetcher(url, headers, *, limit):
                self.assertTrue(url.endswith("VIX_History.csv"))
                self.assertGreater(limit, len(raw))
                return raw
            report = run(*files, root / "out", probe_cboe=True, fetcher=fetcher)
            zipped = root / "out" / "cboe_vix_public_source.csv.gz"
            self.assertEqual(gzip.decompress(zipped.read_bytes()), raw)
            self.assertEqual(report["raw_publication_gzip_sha256"],
                             sha256(zipped.read_bytes()).hexdigest())
            self.assertEqual(report["official_close_certified"], 0)
            again = run(*files, root / "out", probe_cboe=True, fetcher=fetcher)
            self.assertEqual(report, again)
            self.assertEqual(report["input_sha256"]["independent"],
                             sha256(files[1].read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
