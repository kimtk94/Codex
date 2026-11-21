"""No-network, fail-closed contract tests for the Alpaca CA collector and comparison."""
from __future__ import annotations
import csv
from datetime import date
import gzip
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import corporate_actions_reference as ca
import corporate_actions_compare as cmp
from daily20 import load_spec

SPEC=load_spec()
SYMBOLS=[s for s in SPEC["core"]+SPEC["context"] if s!="^VIX"]
SESSION="2026-11-20"


def row(typ="cash_dividends", symbol="HYG", ex="2026-11-19", value=0.30, eid="evt1"):
    base={"id":eid,"symbol":symbol,"process_date":"2026-11-19",
          "ex_date":ex,"currency":"USD"}
    if typ=="cash_dividends":
        base["rate"]=value
    else:
        base.update(old_rate=1.,new_rate=value)
    return base


def page(groups, token=None):
    return json.dumps({"corporate_actions":groups,"next_page_token":token}).encode()


class CorporateActionCollectorTests(unittest.TestCase):
    def test_offline_no_requests_is_research_hold(self):
        result=ca.collect(SYMBOLS,SESSION,offline=True)
        self.assertEqual(result["status"],"CREDENTIALS_ISOLATED_PR_HOLD")
        self.assertEqual(result["finality_verified"],0)
        self.assertEqual(result["events"],[])
        self.assertEqual(result["query_start_process_date"],"2017-01-01")

    def test_actual_response_format_and_pagination(self):
        calls=[]
        def fetch(url, headers, **kwargs):
            calls.append(url)
            self.assertIn("data_quality=all",url)
            self.assertIn("region=us",url)
            self.assertIn("start=2017-01-01",url)
            self.assertIn("end=2026-11-20",url)
            self.assertNotIn("SECRET",url)
            if len(calls)==1:
                return page({"cash_dividends":[row()]},token="next-secret-cursor")
            self.assertIn("page_token=next-secret-cursor",url)
            return page({"forward_splits":[row(typ="forward_splits",symbol="NVDA",
                                            ex="2024-06-10",value=10.,eid="evt2")]})
        with patch.dict("os.environ", {"ALPACA_API_KEY_ID":"KEY",
                                    "ALPACA_API_SECRET_KEY":"SECRET"}):
            result=ca.collect(SYMBOLS,SESSION,fetcher=fetch,stamp="2026-11-21T09:00:00Z")
        self.assertEqual(result["status"],"ALPACA_ACTIONS_RETRIEVED_UNCERTIFIED")
        self.assertEqual(result["page_count"],2)
        self.assertEqual(result["event_count"],2)
        self.assertEqual(result["per_symbol_events"]["HYG"],1)
        self.assertEqual(result["per_symbol_events"]["NVDA"],1)
        self.assertNotIn("next-secret-cursor",json.dumps(result))
        self.assertNotIn("SECRET",json.dumps(result))
        self.assertEqual(result["factor_independently_certified"],0)

    def test_empty_complete_response_is_not_auto_certified(self):
        with patch.dict("os.environ", {"ALPACA_API_KEY_ID":"K","ALPACA_API_SECRET_KEY":"S"}):
            r=ca.collect(SYMBOLS,SESSION,fetcher=lambda *_args,**_kw:page({}))
        self.assertEqual(r["status"],"ALPACA_ACTIONS_RETRIEVED_UNCERTIFIED")
        self.assertEqual(r["event_count"],0)
        self.assertEqual(r["factor_independently_certified"],0)

    def test_api_403_is_hold(self):
        def reject(url,*args,**kwargs):
            raise HTTPError(url,403,"Subscription not permitted",{},None)
        with patch.dict("os.environ", {"ALPACA_API_KEY_ID":"K","ALPACA_API_SECRET_KEY":"S"}):
            r=ca.collect(SYMBOLS,SESSION,fetcher=reject)
        self.assertEqual(r["status"],"SOURCE_FETCH_OR_SCHEMA_HOLD")
        self.assertEqual(r["error_class"],"HTTP_403")

    def test_invalid_response_schema_is_hold(self):
        with patch.dict("os.environ", {"ALPACA_API_KEY_ID":"K","ALPACA_API_SECRET_KEY":"S"}):
            r=ca.collect(SYMBOLS,SESSION,fetcher=lambda *_a,**_kw:b'{"unexpected":[]}')
        self.assertEqual(r["status"],"SOURCE_FETCH_OR_SCHEMA_HOLD")

    def test_incomplete_or_unknown_issuer_event_never_certifies(self):
        with patch.dict("os.environ", {"ALPACA_API_KEY_ID":"K","ALPACA_API_SECRET_KEY":"S"}):
            r=ca.collect(SYMBOLS,SESSION,fetcher=lambda *_a,**_kw:page({
                "cash_dividends":[{"id":"incomplete","symbol":"HYG",
                                   "process_date":"2026-11-20","ex_date":None}],
                "new_corporate_action":[{"id":"unsupported","symbol":"HYG",
                                        "process_date":"2026-11-20"}],
            }))
        self.assertEqual(r["status"],"ALPACA_ACTIONS_INCOMPLETE_OR_UNKNOWN_HOLD")
        self.assertIn("new_corporate_action",r["unknown_action_groups"])
        self.assertFalse(r["historical_identity_certified"])

    def test_unmapped_historical_symbol_retained_separately(self):
        with patch.dict("os.environ", {"ALPACA_API_KEY_ID":"K","ALPACA_API_SECRET_KEY":"S"}):
            r=ca.collect(SYMBOLS,SESSION,fetcher=lambda *_a,**_kw:page({
                "cash_dividends":[row(symbol="OLD_TICKER",eid="old1"),row(eid="ok")],
            }))
        self.assertEqual(r["status"],"ALPACA_ACTIONS_INCOMPLETE_OR_UNKNOWN_HOLD")
        self.assertEqual(r["unmapped_historical_identity_count"],1)
        self.assertEqual(r["unmapped_historical_identity_examples"][0]["returned_symbol"],"OLD_TICKER")
        self.assertEqual(r["event_count"],1)
        self.assertEqual(r["factor_independently_certified"],0)

    def test_repeating_cursor_holds_partial_not_pretend_complete(self):
        with patch.dict("os.environ", {"ALPACA_API_KEY_ID":"K","ALPACA_API_SECRET_KEY":"S"}):
            r=ca.collect(SYMBOLS,SESSION,fetcher=lambda *_a,**_kw:page({},token="loop"))
        self.assertEqual(r["status"],"PAGINATION_LOOP_HOLD")
        self.assertEqual(r["page_count"],2)


def observed():
    return {
        "2026-11-18":{"DIVIDEND":cmp.Decimal("0"),"SPLIT":cmp.Decimal("0")},
        "2026-11-19":{"DIVIDEND":cmp.Decimal("0.30"),"SPLIT":cmp.Decimal("0")},
        "2026-11-20":{"DIVIDEND":cmp.Decimal("0"),"SPLIT":cmp.Decimal("2")},
    }


class CorporateActionCompareTests(unittest.TestCase):
    def test_known_exdate_cash_and_split_match_research_only(self):
        events=[{"type":"cash_dividends",**row(value=0.60)},
                {"type":"forward_splits",**row("forward_splits","HYG","2026-11-20",2.,"evt2")}]
        summary,records=cmp.compare_one("HYG",observed(),events,True)
        self.assertEqual(summary["match_count"],1)
        self.assertEqual(summary["split_normalized_candidate_count"],1)
        self.assertEqual(summary["candidate_numeric_match_count"],2)
        self.assertEqual(summary["status"],"ALL_OBSERVED_EVENTS_NUMERICALLY_MATCH_UNCERTIFIED")
        self.assertEqual(
            {x["status"] for x in records},
            {"CROSS_PROVIDER_NUMERIC_MATCH_RESEARCH_ONLY",
             "SPLIT_NORMALIZED_AMOUNT_MATCH_RESEARCH_ONLY"})
        self.assertFalse(summary["factor_independently_certified"])

    def test_exdate_not_processdate(self):
        event={"type":"cash_dividends",**row(ex="2026-11-19")}
        event["process_date"]="2026-11-20"
        s,rows=cmp.compare_one("HYG",observed(),[event],True)
        self.assertEqual(s["match_count"],1)
        self.assertEqual(rows[0]["ex_date"],"2026-11-19")

    def test_conflicting_amount_does_not_count_as_match(self):
        e={"type":"cash_dividends",**row(value=0.29)}
        s,rows=cmp.compare_one("HYG",observed(),[e],True)
        self.assertIn("CROSS_PROVIDER_VALUE_CONFLICT_HOLD",s["status_counts"])

    def test_dividend_currency_missing_is_held(self):
        e={"type":"cash_dividends",**row()}
        e["currency"]=None
        s,_=cmp.compare_one("HYG",observed(),[e],True)
        self.assertEqual(s["unmatched_or_incomplete_action_count"],0)
        self.assertEqual(s["match_count"],0)
        self.assertEqual(s["currency_unattested_amount_match_count"],1)
        self.assertEqual(s["status"],"EVENT_DIFFERENCES_OR_INCOMPLETE_HOLD")

    def test_future_split_normalizes_historical_dividend_as_candidate_only(self):
        e1={"type":"cash_dividends",**row(value=0.60)}
        e1["currency"]=None
        e2={"type":"forward_splits",**row("forward_splits","HYG","2026-11-20",2.,"evt2")}
        summary,details=cmp.compare_one("HYG",observed(),[e1,e2],True,source_complete=False)
        self.assertEqual(summary["status"],"PARTIAL_REFERENCE_RESEARCH_HOLD")
        self.assertEqual(summary["split_normalized_candidate_count"],1)
        self.assertEqual(summary["candidate_numeric_match_count"],2)
        div=[x for x in details if x["kind"]=="DIVIDEND"][0]
        self.assertEqual(div["candidate_split_multiplier"],"2")
        self.assertEqual(div["candidate_normalized_value"],"0.3")
        self.assertEqual(div["status"],"SPLIT_NORMALIZED_CURRENCY_UNATTESTED_MATCH_RESEARCH")
        self.assertTrue(div["candidate_not_certified"])

    def test_three_decimal_dividend_rounding_is_candidate_not_exact(self):
        e={"type":"cash_dividends",**row(value=0.3004)}
        summary,details=cmp.compare_one("HYG",observed(),[e],True)
        self.assertEqual(summary["rounding_level_candidate_count"],1)
        self.assertEqual(summary["match_count"],0)
        self.assertTrue(any(x["status"]=="ROUNDING_LEVEL_AGREEMENT_RESEARCH_ONLY"
                            for x in details))

    def test_no_reference_can_never_be_reported_as_match(self):
        s,details=cmp.compare_one("HYG",observed(),[],False)
        self.assertEqual(s["status"],"NO_ALPACA_REFERENCE_HOLD")
        self.assertEqual(s["match_count"],0)
        self.assertTrue(all(x["status"]=="SOURCE_UNAVAILABLE_HOLD" for x in details))

    def test_partial_alpaca_source_can_show_candidate_but_never_complete(self):
        e={"type":"cash_dividends",**row()}
        e["currency"]=None
        summary,rows=cmp.compare_one("HYG",observed(),[e],True,source_complete=False)
        self.assertEqual(summary["status"],"PARTIAL_REFERENCE_RESEARCH_HOLD")
        self.assertEqual(summary["currency_unattested_amount_match_count"],1)
        self.assertEqual(summary["match_count"],0)
        self.assertTrue(any(x["status"]=="CROSS_PROVIDER_AMOUNT_MATCH_CURRENCY_UNATTESTED" for x in rows))
        self.assertFalse(summary["factor_independently_certified"])

    def test_multiple_events_not_summed_into_false_match(self):
        e1={"type":"cash_dividends",**row(value=0.2)}
        e2={"type":"cash_dividends",**row(value=0.1,eid="evt2")}
        s,details=cmp.compare_one("HYG",observed(),[e1,e2],True)
        self.assertEqual(s["match_count"],0)
        self.assertTrue(any(x["status"]=="MULTIPLE_SAME_DAY_EVENTS_AMBIGUOUS_HOLD"
                            for x in details))

    def test_full_25_offline_pipeline_still_holds(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            factor=root/"factor"
            factor.mkdir()
            ref=ca.collect(SYMBOLS,SESSION,offline=True)
            ref_path=root/"reference.json"
            ref_path.write_text(json.dumps(ref))
            frows=[]
            for sym in SYMBOLS:
                filename=sym.lower()+".csv.gz"
                with gzip.open(factor/filename,"wt",newline="") as file:
                    writer=csv.DictWriter(file,fieldnames=["session","yahoo_dividend","yahoo_stock_split"])
                    writer.writeheader()
                    writer.writerow({"session":SESSION,"yahoo_dividend":0,
                                     "yahoo_stock_split":0})
                frows.append({"symbol":sym,"csv_gzip_file":filename})
            (factor/"report.json").write_text(json.dumps({
                "session":SESSION,"finality_verified":0,"rows":frows}))
            report=cmp.run(factor,ref_path,root/"out")
            self.assertEqual(report["required"],25)
            self.assertEqual(report["yahoo_factor_sources_observed"],25)
            self.assertEqual(report["independent_factor_certification"],0)
            self.assertEqual(report["finality_verified"],0)
            self.assertEqual(report["matched_ex_date_events"],0)
            self.assertTrue((root/"out"/"event_comparison.csv").is_file())
            self.assertTrue((root/"out"/"report.json").is_file())


if __name__=="__main__":
    unittest.main()
