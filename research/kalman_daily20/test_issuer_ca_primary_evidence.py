"""Offline issuer primary-source evidence invariants. No external requests."""
from __future__ import annotations

from copy import deepcopy
import csv
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.error import HTTPError

import issuer_ca_primary_evidence as ie


MANIFEST = json.loads(Path("research/kalman_daily20/issuer_ca_primary_sources.json").read_text())


def row(symbol,day,reason="ALPACA_VS_YAHOO_VALUE_CONFLICT_UNEXPLAINED",
        yahoo="0.35",alpaca="1.75"):
    return {
        "symbol":symbol,"ex_date":day,
        "diagnostic_reason":reason,
        "comparison_status":"CROSS_PROVIDER_VALUE_CONFLICT_HOLD",
        "yahoo_repaired_event":yahoo,"alpaca_rate":alpaca
    }


def cases():
    return [
        row("SPY","2018-06-15","YAHOO_ONLY_HISTORICAL_UNEXPLAINED","1.246",""),
        row("SPY","2021-12-17",yahoo="1.633",alpaca="1.636431"),
        row("AVGO","2018-03-21"),
        row("AVGO","2018-06-19"),
        row("QLD","2025-03-26",yahoo="0.013",alpaca="0.025641"),
        row("QLD","2025-12-24",yahoo="0.023",alpaca="0.022572"),
        row("QLD","2026-03-25",yahoo="0.013",alpaca="0.01319"),
        row("QQQ","2022-09-19",
            "SAME_EXDATE_IDENTICAL_RATES_DISTINCT_EVENT_IDS","0.519",""),
        row("HYG","2018-12-03",
            "YAHOO_REPAIR_SUPPRESSED_DIVIDEND_OBSERVED","0","0.376387"),
    ]


def fake_html(url):
    if "ssga.com" in url:
        return ("<div>12 Jun 2018 | 15 Jun 2018 | Gross Distribution 1.24557</div>"
                "<div>17 Dec 2021 | 20 Dec 2021 | 1.63643</div>").encode()
    if "broadcom-limited" in url:
        return b"<p>March 15, 2018 | quarterly dividend of $1.75 per share</p>"
    if "broadcom-inc" in url:
        return b"<p>June 29, 2018 | dividend paid $1.75 per share</p>"
    if "proshares.com" in url:
        return b"<table>3/26/2025 | 4/1/2025 ... 12/24/2025 | 12/31/2025 ... 3/25/2026 | 3/31/2026</table>"
    raise AssertionError("unknown source")


class IssuerPrimaryEvidenceTests(unittest.TestCase):
    def test_manifest_official_hosts_and_specific_seven_claims(self):
        sources,claims=ie.validate_manifest(MANIFEST)
        self.assertEqual(len(sources),4)
        self.assertEqual(len(claims),7)
        self.assertEqual(sum(c["reported_amount_usd"] is not None for c in claims.values()),4)
        self.assertEqual(sum(c["reported_amount_usd"] is None for c in claims.values()),3)

    def test_offline_no_source_body_never_asserts_issuer_payment(self):
        with TemporaryDirectory() as d:
            report=ie.run(MANIFEST,cases(),d,offline=True)
            self.assertEqual(report["unresolved_cases_analyzed"],8)
            self.assertEqual(report["official_leads_applicable"],7)
            self.assertEqual(report["live_source_anchor_supported_cases"],0)
            self.assertEqual(report["raw_source_fetch_success"],0)
            self.assertEqual(report["issuer_action_payments_certified"],0)
            self.assertEqual(report["source_finality_verified"],0)
            self.assertFalse((Path(d)/"raw").exists())

    def test_live_fake_issuer_pages_anchor_near_value_without_factor_promotion(self):
        with TemporaryDirectory() as d:
            report=ie.run(MANIFEST,cases(),d,getter=fake_html)
            self.assertEqual(report["raw_source_fetch_success"],4)
            self.assertEqual(report["live_source_anchor_supported_cases"],7)
            self.assertEqual(report["factor_certified"],0)
            self.assertEqual(report["issuer_action_payments_certified"],0)
            for x in report["source_results"].values():
                self.assertEqual(x["status"],"FETCHED_SOURCE_UNCERTIFIED")
                self.assertIsNotNone(x["body_sha256"])
                body=gzip.decompress((Path(d)/x["raw_archive"]).read_bytes())
                self.assertEqual(ie.sha256(body).hexdigest(),x["body_sha256"])
            self.assertTrue((Path(d)/"report.json").exists())
            with (Path(d)/"unresolved_review.csv").open() as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),8)
            self.assertTrue(all(r["independent_close_certified"]=="False" for r in rows))
            spy=next(r for r in rows if r["symbol"]=="SPY" and r["ex_date"]=="2021-12-17")
            self.assertEqual(spy["primary_evidence_grade"],"ISSUER_AMOUNT_FAVORS_ALPACA_NUMERIC_ONLY")
            avgo=next(r for r in rows if r["symbol"]=="AVGO")
            self.assertEqual(avgo["amount_comparison_basis"],"RAW_PRE_SPLIT_ISSUER_AMOUNT_NOT_YAHOO_COMPARABLE")
            qld=next(r for r in rows if r["symbol"]=="QLD")
            self.assertEqual(qld["primary_evidence_grade"],"ISSUER_EXPECTED_CALENDAR_DATE_ONLY_NO_PAYMENT_ASSERTION")

    def test_issuer_2018_spy_amount_near_yahoo_but_alpaca_missing(self):
        c=MANIFEST["claims"][0]
        result=ie.compare_issuer_claim(
            row("SPY","2018-06-15","YAHOO_ONLY_HISTORICAL_UNEXPLAINED","1.246",""),
            c,{"url":"https://www.ssga.com/example",
               "status":"FETCHED_SOURCE_UNCERTIFIED",
               "anchor_grade_by_claim":{"SPY|2018-06-15":"BOTH_NEARBY_ANCHORS_OBSERVED"}})
        self.assertEqual(result["primary_evidence_grade"],"ISSUER_AMOUNT_FAVORS_YAHOO_NUMERIC_ONLY")
        self.assertIsNone(result["amount_matches_alpaca_raw"])
        self.assertTrue(result["amount_matches_yahoo_as_reported"])

    def test_nonissuer_qqq_event_remains_hold(self):
        r=ie.compare_issuer_claim(row("QQQ","2022-09-19"),None,None)
        self.assertEqual(r["primary_evidence_grade"],"NO_CURATED_PRIMARY_SOURCE_HOLD")

    def test_calendar_no_amount_invariant(self):
        bad=deepcopy(MANIFEST)
        bad["claims"][4]["reported_amount_usd"]="0.025641"
        with self.assertRaisesRegex(ValueError,"SCHEDULE_MUST_NOT_ASSERT_PAID_AMOUNT"):
            ie.validate_manifest(bad)

    def test_untrusted_external_url_rejected(self):
        bad=deepcopy(MANIFEST)
        bad["sources"][0]["url"]="https://example.org/spy"
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_ISSUER_DOMAIN"):
            ie.validate_manifest(bad)
        bad=deepcopy(MANIFEST)
        bad["sources"][0]["url"]="http://www.ssga.com/spy"
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_ISSUER_DOMAIN"):
            ie.validate_manifest(bad)

    def test_missing_date_or_duplicate_claim_rejected(self):
        bad=deepcopy(MANIFEST)
        bad["claims"].append(deepcopy(bad["claims"][0]))
        with self.assertRaisesRegex(ValueError,"DUPLICATED_OR_UNSOURCED_CLAIM"):
            ie.validate_manifest(bad)

    def test_source_403_never_accepts_curated_claim(self):
        def blocked(url):
            raise HTTPError(url,403,"Denied",{},None)
        with TemporaryDirectory() as d:
            result=ie.run(MANIFEST,cases(),d,getter=blocked)
            self.assertEqual(result["raw_source_fetch_success"],0)
            self.assertEqual(result["live_source_anchor_supported_cases"],0)
            self.assertEqual(result["status"],"ISSUER_PRIMARY_SOURCE_EVIDENCE_RESEARCH_HOLD")
            self.assertEqual(result["issuer_action_payments_certified"],0)

    def test_distant_anchor_is_not_source_evidence(self):
        c=MANIFEST["claims"][0]
        invalid=b"<h1>12 Jun 2018</h1>" + b"x"*3000 + b"<p>1.24557</p>"
        ok,_=ie.grade_anchors(invalid,c)
        self.assertFalse(ok)
        close=b"<h1>12 Jun 2018 1.24557</h1>"
        yes,_=ie.grade_anchors(close,c)
        self.assertTrue(yes)

    def test_failed_malformed_body_still_persists_sha_and_unknown_anchor(self):
        with TemporaryDirectory() as d:
            o=ie.probe_source(MANIFEST["sources"][0],
                [MANIFEST["claims"][0]],d,getter=lambda url:b"<p>missing expected fact</p>")
            self.assertIsNotNone(o["body_sha256"])
            self.assertEqual(o["anchor_grade_by_claim"]["SPY|2018-06-15"],
                             "ANCHORS_NOT_VERIFIED_HOLD")
            self.assertFalse(o["source_claim_independently_certified"])


if __name__=="__main__":
    unittest.main()
