"""Offline, credential-free contracts for Nasdaq 16-public-page NOCP access audit."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import tempfile
import unittest

from nasdaq_nocp_access_audit import (
    build, classify_html, page_url, run, VERSION,
)
from official_close_source_access import build as make_access
from test_official_close_source_access import fixture as official_fixture
from test_official_price_proof_obligations import DIGEST


def fixture():
    spec, independent, reference, venue, obligations = official_fixture()
    spec["research_only"] = True
    # Represent the 2026-11-20 real aggregate route distribution exactly
    # while using synthetic individual venue labels, never licensed values.
    for i, row in enumerate(venue["rows"]):
        row["primary_canonical"] = (
            "NASDAQ" if i < 16 else "NYSE" if i < 19 else "NYSE_ARCA"
        )
    access = make_access(
        spec, independent, reference, venue, obligations,
        input_sha256={"config": DIGEST, "independent": DIGEST,
                      "reference": DIGEST, "venue": DIGEST,
                      "obligations": DIGEST})
    return spec, access


def blank_evidence():
    return {
        "probe_status": "NASDAQ_HTTP_403_HOLD",
        "http_status": 403,
        "response_sha256": None,
        "response_bytes": None,
        "html_unavailable_placeholder": None,
    }


class NasdaqNocpAccessTests(unittest.TestCase):
    def setUp(self):
        self.spec, self.access = fixture()

    def evaluate(self, *, access=None, probes=None, attempted=False):
        return build(self.spec, access or self.access, probes=probes or {},
                     probe_attempted=attempted,
                     file_hashes={"config": DIGEST, "access": DIGEST})

    def test_16_routes_exact_frozen_session_no_numeric(self):
        r = self.evaluate()
        self.assertEqual(r["version"], VERSION)
        self.assertEqual(r["nasdaq_current_master_route_count"], 16)
        self.assertEqual(r["official_nocp_numeric_records_admitted"], 0)
        self.assertEqual(r["independent_regular_close_certified"], 0)
        self.assertEqual(r["factor_certified"], 0)
        self.assertEqual(len(r["rows"]), 16)
        self.assertTrue(all(x["official_certified"] is False
                            and x["nocp_price"] is None for x in r["rows"]))

    def test_stocks_etfs_not_mislabeled_in_urls(self):
        self.assertEqual(
            page_url("QQQ"),
            "https://www.nasdaq.com/market-activity/etf/qqq/historical-nocp",
        )
        self.assertEqual(
            page_url("AAPL"),
            "https://www.nasdaq.com/market-activity/stocks/aapl/historical-nocp",
        )

    def test_reject_symbol_injection(self):
        for sym in ("QQQ/a", "aapl", "NVDA?x=1", "", "^VIX", "A" * 30):
            with self.subTest(sym=sym), self.assertRaisesRegex(
                ValueError, "NOCP_UNSAFE_SYMBOL"
            ):
                page_url(sym)

    def test_public_html_says_not_available_not_numeric(self):
        r = classify_html(
            b"<html><h1>AAPL Historical NOCP</h1>"
            b"Data is currently not available</html>", 200,
        )
        self.assertEqual(r["http_status"], 200)
        self.assertTrue(r["html_unavailable_placeholder"])
        self.assertTrue(r["probe_status"].endswith("_HOLD"))
        self.assertEqual(len(r["response_sha256"]), 64)

    def test_html_with_dates_dollars_is_not_authenticated(self):
        payload = (b"Historical NOCP 2026-11-20 $342.56 fake price "
                   b"last sale 13:05 ET")
        r = classify_html(payload, 200)
        self.assertEqual(r["probe_status"],
                         "NASDAQ_HISTORICAL_NOCP_HTML_NOT_AUTHENTICATED_NUMERIC_HOLD")
        self.assertNotIn("nocp_price", r)

    def test_html_other_page_detected_not_verified(self):
        r = classify_html(b"<html>Generic historical stock quote</html>", 200)
        self.assertEqual(r["probe_status"], "NASDAQ_PAGE_WITHOUT_NOCP_IDENTITY_HOLD")

    def test_reject_missing_html_bytes(self):
        with self.assertRaisesRegex(ValueError, "NOCP_INVALID_HTML_BYTES"):
            classify_html(b"", 200)

    def test_online_all16_stays_hold(self):
        names = [x["symbol"] for x in self.access["rows"]
                 if x["current_listed_venue"] == "NASDAQ"]
        result = self.evaluate(probes={s: blank_evidence() for s in names},
                               attempted=True)
        self.assertEqual(result["public_pages_attempted"], 16)
        self.assertEqual(result["public_html_200_count"], 0)
        self.assertEqual(result["independent_regular_close_certified"], 0)

    def test_reject_partial_probes(self):
        name = self.access["rows"][0]["symbol"]
        with self.assertRaisesRegex(ValueError, "NOCP_PROBE_ALL_CURRENT_NASDAQ"):
            self.evaluate(probes={name: blank_evidence()}, attempted=True)

    def test_reject_unknown_venue_probes(self):
        with self.assertRaisesRegex(ValueError, "NOCP_UNKNOWN_PROBE_SYMBOL"):
            self.evaluate(probes={"XOM": blank_evidence()}, attempted=True)

    def test_reject_offline_fake_probe(self):
        name = self.access["rows"][0]["symbol"]
        with self.assertRaisesRegex(ValueError, "NOCP_OFFLINE_PROBE_MUST_BE_EMPTY"):
            self.evaluate(probes={name: blank_evidence()}, attempted=False)

    def test_reject_venuemap_false_certification(self):
        data = deepcopy(self.access)
        data["rows"][0]["point_in_time_close_certified"] = True
        with self.assertRaisesRegex(ValueError, "NOCP_UPSTREAM_SYMBOL_SESSION"):
            self.evaluate(access=data)

    def test_reject_upstream_false_close_certification(self):
        data = deepcopy(self.access)
        data["official_close_certified"] = 1
        with self.assertRaisesRegex(ValueError, "NOCP_UPSTREAM_RESEARCH_SCOPE"):
            self.evaluate(access=data)

    def test_reject_duplicate_symbol(self):
        data = deepcopy(self.access)
        data["rows"][0]["symbol"] = data["rows"][1]["symbol"]
        with self.assertRaisesRegex(ValueError, "NOCP_UPSTREAM_SYMBOL_SESSION"):
            self.evaluate(access=data)

    def test_reject_cross_session_row(self):
        data = deepcopy(self.access)
        data["rows"][0]["session"] = "2026-11-19"
        with self.assertRaisesRegex(ValueError, "NOCP_UPSTREAM_SYMBOL_SESSION"):
            self.evaluate(access=data)

    def test_dated_venue_baseline_not_backfilled_to_future(self):
        data = deepcopy(self.access)
        data["session"] = "2026-11-23"
        data["rows"] = [
            {**x, "session": "2026-11-23"} for x in data["rows"]
        ]
        # Venue migrations in future change the count; do not hardcode 16.
        for row in data["rows"]:
            if row["current_listed_venue"] == "NYSE":
                row["current_listed_venue"] = "NASDAQ"
                row["publisher"] = "Nasdaq"
                row["access_status"] = (
                    "AUTHENTICATED_SESSION_NUMERIC_RECORD_NOT_CONNECTED_HOLD")
        result = self.evaluate(access=data)
        self.assertEqual(result["nasdaq_current_master_route_count"], 19)

    def test_fail_closed_fake_actual_nocp_probe(self):
        names = [x["symbol"] for x in self.access["rows"]
                 if x["current_listed_venue"] == "NASDAQ"]
        p = {s: blank_evidence() for s in names}
        p[names[0]] = {
            **blank_evidence(),
            "probe_status": "CERTIFIED",
            "http_status": 200,
            "nocp_price": 42.50,
        }
        with self.assertRaisesRegex(ValueError, "NOCP_PROBE_RESPONSE_SCHEMA"):
            self.evaluate(probes=p, attempted=True)

    def test_report_csv_sha_and_no_price_from_mocked_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config.json"
            access = root / "access.json"
            config.write_text(json.dumps(self.spec), encoding="utf-8")
            access.write_text(json.dumps(self.access), encoding="utf-8")
            offline = run(config, access, root / "offline")
            csv_path = root / "offline" / "public_portal_probe.csv"
            self.assertEqual(sha256(csv_path.read_bytes()).hexdigest(),
                             offline["csv_sha256"])
            self.assertEqual(len(csv_path.read_text().splitlines()), 17)
            visits = []
            def no_data_fetcher(url):
                visits.append(url)
                return classify_html(
                    ("<h1>Historical NOCP</h1>"
                     "Data is currently not available").encode(), 200)
            report = run(config, access, root / "online", probe_public=True,
                         fetcher=no_data_fetcher)
            self.assertEqual(len(visits), 16)
            self.assertEqual(report["public_unavailable_placeholders"], 16)
            self.assertEqual(report["official_nocp_numeric_records_admitted"], 0)
            self.assertEqual(report["independent_regular_close_certified"], 0)
            self.assertEqual(report["input_sha256"]["access"],
                             sha256(access.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
