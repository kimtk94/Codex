"""Offline issuer primary-source evidence invariants. No external requests."""
from __future__ import annotations

from copy import deepcopy
import csv
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
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
        row("QQQ","2020-09-21","ALPACA_ONLY_UNCONFIRMED_BY_EITHER_YAHOO_VARIANT","0","0.38824"),
        row("QQQ","2018-06-18","ALPACA_VS_YAHOO_VALUE_CONFLICT_UNEXPLAINED","0.378","0.37638"),
        row("QLD","2023-09-20","YAHOO_ONLY_HISTORICAL_UNEXPLAINED","0.088",""),
        row("HYG","2023-12-14","ALPACA_VS_YAHOO_VALUE_CONFLICT_UNEXPLAINED","0.379","0.37847"),
        row("HYG","2018-12-03",
            "YAHOO_REPAIR_SUPPRESSED_DIVIDEND_OBSERVED","0","0.376387"),
        row("MSFT","2026-11-19","ALPACA_PROCESS_DATE_CUTOFF_POSSIBLE","0.98",""),
        row("XOM","2026-11-16","ALPACA_PROCESS_DATE_CUTOFF_POSSIBLE","1.07",""),
        row("MSTR","2025-05-21","ALPACA_ONLY_UNCONFIRMED_BY_EITHER_YAHOO_VARIANT","0","0.335"),
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
    if "news.microsoft.com" in url:
        return (b"<p>Microsoft declared a quarterly dividend of $0.98 per share. "
                b"The ex-dividend date will be Nov. 19, 2026.</p>")
    if "investor.exxonmobil.com" in url:
        return (b"<p>ExxonMobil declared a fourth-quarter dividend of $1.07 per share, "
                b"payable December 10, 2026 to shareholders of record "
                b"November 16, 2026.</p>")
    if "strategy.com" in url:
        return (b"<p>The Company has historically not paid any dividends on its "
                b"shares of class A common stock, and past performance is "
                b"not indicative of future results.</p>")
    if "blackrock.com/jp" in url:
        return b"%PDF-1.7\nsynthetic fixture"
    if "sec.gov" in url and "dp137172_" in url:
        return (b"<p>On September 18, 2020, Invesco QQQ Trust declared "
                b"a cash dividend of $0.38824 per share payable on October 30.</p>")
    if "sec.gov" in url and "dp182689_" in url:
        return (b"<p>On September 16, 2022, Invesco QQQ Trust declared "
                b"a cash dividend of $0.51856 per share payable on October 31.</p>")
    raise AssertionError("unknown source")


class IssuerPrimaryEvidenceTests(unittest.TestCase):
    def test_manifest_official_hosts_and_specific_ten_claims(self):
        sources,claims=ie.validate_manifest(MANIFEST)
        self.assertEqual(len(sources),10)
        self.assertEqual(len(claims),13)
        self.assertEqual(sum(c["reported_amount_usd"] is not None for c in claims.values()),9)
        self.assertEqual(sum(c["reported_amount_usd"] is None for c in claims.values()),4)

    def test_offline_no_source_body_never_asserts_issuer_payment(self):
        with TemporaryDirectory() as d:
            report=ie.run(MANIFEST,cases(),d,offline=True)
            self.assertEqual(report["unresolved_cases_analyzed"],15)
            self.assertEqual(report["official_leads_applicable"],13)
            self.assertEqual(report["issuer_fund_historical_document_leads"],1)
            self.assertEqual(report["sec_filed_third_party_quote_leads"],2)
            self.assertEqual(report["live_source_anchor_supported_cases"],0)
            self.assertEqual(report["raw_source_fetch_success"],0)
            self.assertEqual(report["issuer_action_payments_certified"],0)
            self.assertEqual(report["source_finality_verified"],0)
            self.assertFalse((Path(d)/"raw").exists())

    def test_live_fake_issuer_pages_anchor_near_value_without_factor_promotion(self):
        with TemporaryDirectory() as d:
            with patch.object(ie,"text_of_pdf",return_value="Distributions 12月14日 0.37847 USD"):
                report=ie.run(MANIFEST,cases(),d,getter=fake_html)
            self.assertEqual(report["raw_source_fetch_success"],10)
            self.assertEqual(report["live_source_anchor_supported_cases"],13)
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
            self.assertEqual(len(rows),15)
            self.assertTrue(all(r["independent_close_certified"]=="False" for r in rows))
            spy=next(r for r in rows if r["symbol"]=="SPY" and r["ex_date"]=="2021-12-17")
            self.assertEqual(spy["primary_evidence_grade"],"ISSUER_AMOUNT_FAVORS_ALPACA_NUMERIC_ONLY")
            avgo=next(r for r in rows if r["symbol"]=="AVGO")
            self.assertEqual(avgo["amount_comparison_basis"],"RAW_PRE_SPLIT_ISSUER_AMOUNT_NOT_YAHOO_COMPARABLE")
            qld=next(r for r in rows if r["symbol"]=="QLD")
            self.assertEqual(qld["primary_evidence_grade"],"ISSUER_EXPECTED_CALENDAR_DATE_ONLY_NO_PAYMENT_ASSERTION")
            msft=next(r for r in rows if r["symbol"]=="MSFT")
            self.assertEqual(msft["primary_evidence_grade"],"ISSUER_AMOUNT_FAVORS_YAHOO_NUMERIC_ONLY")
            self.assertEqual(msft["exdate_explicitly_issuer_published"],"True")
            xom=next(r for r in rows if r["symbol"]=="XOM")
            self.assertEqual(xom["primary_evidence_grade"],"ISSUER_AMOUNT_FAVORS_YAHOO_NUMERIC_ONLY")
            self.assertEqual(xom["exdate_explicitly_issuer_published"],"False")
            mstr=next(r for r in rows if r["symbol"]=="MSTR")
            self.assertEqual(mstr["primary_evidence_grade"],
                             "ISSUER_COMMON_CLASS_NO_DIVIDEND_POLICY_OBSERVED_IDENTITY_HOLD")
            self.assertEqual(mstr["primary_amount_usd"],"")
            self.assertEqual(mstr["amount_matches_alpaca_raw"],"")
            self.assertEqual(mstr["amount_comparison_basis"],
                             "ISSUER_POLICY_NO_COMMON_DIVIDEND_SECURITY_CLASS_HOLD")
            hyg=next(r for r in rows if r["symbol"]=="HYG")
            self.assertEqual(hyg["primary_evidence_grade"],"ISSUER_AMOUNT_FAVORS_ALPACA_NUMERIC_ONLY")
            sec=next(r for r in rows if r["symbol"]=="QQQ" and r["ex_date"]=="2022-09-19")
            self.assertEqual(sec["primary_evidence_grade"],
                 "SEC_HOSTED_THIRD_PARTY_QUOTE_NUMERIC_ONLY_NOT_ISSUER_ATTESTED")
            self.assertEqual(sec["amount_comparison_basis"],
                 "SEC_THIRD_PARTY_QUOTE_NOT_ORIGINAL_ISSUER_STATEMENT")
            for sym,day in (("QQQ","2018-06-18"),("QLD","2023-09-20")):
                case=next(r for r in rows if r["symbol"]==sym and r["ex_date"]==day)
                self.assertEqual(case["primary_evidence_grade"],"NO_CURATED_PRIMARY_SOURCE_HOLD")

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

    def test_common_stock_policy_must_not_include_made_up_cash_amount(self):
        bad=deepcopy(MANIFEST)
        for claim in bad["claims"]:
            if claim["symbol"] == "MSTR":
                claim["reported_amount_usd"] = "0.335"
        with self.assertRaisesRegex(ValueError,"SCHEDULE_MUST_NOT_ASSERT_PAID_AMOUNT"):
            ie.validate_manifest(bad)

    def test_declared_but_not_paid_date_semantics_retained(self):
        claims={(x["symbol"],x["ex_date"]):x for x in MANIFEST["claims"]}
        self.assertTrue(claims["MSFT","2026-11-19"]["exdate_explicitly_issuer_published"])
        self.assertFalse(claims["XOM","2026-11-16"]["exdate_explicitly_issuer_published"])
        self.assertEqual(claims["MSTR","2025-05-21"]["reported_amount_usd"],None)

    def test_japanese_fund_pdf_requires_actual_pdf_magic_and_extracted_text(self):
        source=next(s for s in MANIFEST["sources"]
                    if s["id"]=="HYG_BLACKROCK_2024_JP_ANNUAL")
        claim=next(c for c in MANIFEST["claims"]
                   if c["source_id"]==source["id"])
        with TemporaryDirectory() as root:
            bad=ie.probe_source(source,[claim],root,
                                getter=lambda u:"<html>12月14日 0.37847</html>".encode("utf-8"))
            self.assertEqual(bad["status"],"ValueError_SOURCE_HOLD")
            self.assertEqual(bad["anchor_grade_by_claim"],{})
        with TemporaryDirectory() as root:
            with patch.object(ie,"text_of_pdf",return_value="12月14日 0.37847"):
                good=ie.probe_source(source,[claim],root,
                                     getter=lambda u:b"%PDF-1.7\\nmock")
            self.assertEqual(good["status"],"FETCHED_SOURCE_UNCERTIFIED")
            self.assertEqual(good["anchor_grade_by_claim"]["HYG|2023-12-14"],
                             "BOTH_NEARBY_ANCHORS_OBSERVED")
            self.assertTrue(good["raw_archive"].endswith(".pdf.gz"))

    def test_sec_quote_cannot_be_recast_as_direct_issuer_fact(self):
        claims={(c["symbol"],c["ex_date"]):c for c in MANIFEST["claims"]}
        sec=claims["QQQ","2020-09-21"]
        self.assertEqual(sec["claim_type"],"SEC_FILED_THIRD_PARTY_ISSUER_AMOUNT_QUOTE")
        self.assertFalse(sec["exdate_explicitly_issuer_published"])
        with self.assertRaisesRegex(ValueError,"SEC_QUOTE_PROVENANCE_MISMATCH"):
            invalid=deepcopy(MANIFEST)
            for cl in invalid["claims"]:
                if cl["symbol"]=="QQQ" and cl["ex_date"]=="2020-09-21":
                    cl["source_id"]="MSFT_2026_DIVIDEND"
            ie.validate_manifest(invalid)

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
