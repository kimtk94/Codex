"""Offline contract tests for Daily20 corporate-action exception forensics."""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from daily20 import load_spec
import corporate_action_forensics as fx
import corporate_actions_reference as refmod


SPEC=load_spec()
NAMES=[s for s in SPEC["core"]+SPEC["context"] if s!="^VIX"]
SESSION="2026-11-20"


def observed(days, symbol="HYG"):
    return {day: {"DIVIDEND": Decimal(str(v)), "SPLIT": Decimal(0)}
            for day,v in days.items()}


def source():
    return {
        "version": refmod.VERSION, "session": SESSION,
        "query_end_process_date":SESSION,
        "finality_verified":0,
        "queried_symbols":NAMES, "status":"ALPACA_ACTIONS_INCOMPLETE_OR_UNKNOWN_HOLD",
        "events":[],
        "unmapped_historical_identity_count":0,
        "unmapped_historical_identity_examples":[],
    }


def case_row(symbol,day,status,yahoo="0",alpaca="0.3"):
    return {"symbol":symbol,"ex_date":day,"kind":"DIVIDEND",
            "status":status,"yahoo_value":yahoo,
            "alpaca_value":alpaca}


def event(symbol,day,rate,event_id,process=None):
    return {"type":"cash_dividends","id":event_id,
            "symbol":symbol,"ex_date":day,
            "process_date":process or day,"rate":str(rate),"currency":None}


class ForensicReasonTests(unittest.TestCase):
    def test_alpaca_only_repair_suppression_requires_raw_positive_same_exdate(self):
        day="2021-12-16"
        r=source()
        r["events"]=[event("HYG",day,"0.29623","event01")]
        case=fx.triage(case_row("HYG",day,"ALPACA_ONLY_EVENT_HOLD"),
                       observed({day:0}), observed({day:0.296}), r, r["status"], SESSION)
        self.assertEqual(case["diagnostic_reason"],fx.REPAIR_DIAGNOSTIC)
        self.assertEqual(case["yahoo_raw_event"],"0.296")
        self.assertEqual(case["yahoo_repaired_event"],"0")
        self.assertTrue(case["vendor_policy_effect_observed"])
        self.assertFalse(case["resolved_by_issuer_evidence"])

    def test_alpaca_only_same_zero_raw_does_not_falsely_explain(self):
        day="2020-09-21"
        r=source()
        case=fx.triage(case_row("QQQ",day,"ALPACA_ONLY_EVENT_HOLD"),
                       observed({day:0}), observed({day:0}),r,r["status"],SESSION)
        self.assertNotEqual(case["diagnostic_reason"],fx.REPAIR_DIAGNOSTIC)
        self.assertFalse(case["vendor_policy_effect_observed"])

    def test_old_yahoo_only_different_from_recent_process_date_censor(self):
        r=source()
        recent=fx.triage(case_row("MSFT","2026-11-19","YAHOO_ONLY_EVENT_HOLD"),
                         observed({"2026-11-19":0.98}),observed({"2026-11-19":0.98}),
                         r,r["status"],SESSION)
        old=fx.triage(case_row("SPY","2018-06-15","YAHOO_ONLY_EVENT_HOLD"),
                      observed({"2018-06-15":1.246}),observed({"2018-06-15":1.246}),
                      r,r["status"],SESSION)
        self.assertEqual(recent["diagnostic_reason"],fx.SOURCE_BOUNDARY)
        self.assertEqual(old["diagnostic_reason"],"YAHOO_ONLY_HISTORICAL_UNEXPLAINED")
        self.assertFalse(recent["resolved_by_issuer_evidence"])

    def test_qqq_same_exdate_two_ids_same_rate_with_different_process_dates(self):
        r=source()
        r["events"]=[
            event("QQQ","2022-09-19","0.51856","A","2022-09-23"),
            event("QQQ","2022-09-19","0.51856","B","2022-10-31"),
        ]
        case=fx.triage(case_row("QQQ","2022-09-19",
                  "MULTIPLE_SAME_DAY_EVENTS_AMBIGUOUS_HOLD"),
                       observed({"2022-09-19":0.519}),
                       observed({"2022-09-19":0.519}),
                       r,r["status"],SESSION)
        self.assertEqual(case["diagnostic_reason"],fx.DUPLICATE)
        self.assertEqual(case["alpaca_event_ids"],"A;B")
        self.assertEqual(case["alpaca_process_dates"],"2022-09-23;2022-10-31")
        self.assertFalse(case["resolved_by_issuer_evidence"])

    def test_value_conflicts_remain_unexplained_not_auto_split_normalized(self):
        r=source()
        case=fx.triage(case_row("AVGO","2018-03-21",
                "CROSS_PROVIDER_VALUE_CONFLICT_HOLD"),
                       observed({"2018-03-21":0.35}),observed({"2018-03-21":0.35}),
                       r,r["status"],SESSION)
        self.assertEqual(case["diagnostic_reason"],
                         "ALPACA_VS_YAHOO_VALUE_CONFLICT_UNEXPLAINED")
        self.assertFalse(case["independent_price_factor_certified"])

    def test_numeric_candidate_not_in_exception_queue(self):
        r=source()
        case=fx.triage(case_row("AAPL","2024-01-01",
                 "CROSS_PROVIDER_NUMERIC_MATCH_RESEARCH_ONLY"),
                       observed({"2024-01-01":0.5}), observed({"2024-01-01":0.5}),
                       r,r["status"],SESSION)
        self.assertIsNone(case)

    def test_collector_parses_expected_merger_and_name_change_role_only_identifiers(self):
        data=json.dumps({"corporate_actions":{
            "stock_mergers":[{"id":"event-1","process_date":"2024-05-03",
                              "acquiree_symbol":"X","acquirer_symbol":"AAPL"}],
            "name_changes":[{"id":"event-2","process_date":"2022-06-09",
                             "old_symbol":"FB","new_symbol":"META"}],
            "cash_dividends":[{"id":"event-3","symbol":"HYG",
                               "process_date":"2026-11-20","ex_date":"2026-11-19",
                               "rate":"0.5"}]},
            "next_page_token":None}).encode()
        rows,token,digest,malformed,unknown,links=refmod.parse_page(data,set(NAMES),1)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["symbol"],"HYG")
        self.assertEqual(len(links),2)
        self.assertEqual(malformed,0)
        self.assertEqual(links[0]["identity_roles"]["acquirer_symbol"],"AAPL")
        self.assertEqual(links[0]["queried_symbol_role_candidates"]["acquirer_symbol"],"AAPL")
        self.assertEqual(links[1]["queried_symbol_role_candidates"]["new_symbol"],"META")
        self.assertTrue(all(not l["issuer_lineage_certified"] for l in links))
        self.assertEqual(unknown,[])

    def test_unexpected_generic_symbol_missing_still_schema_hold(self):
        data=json.dumps({"corporate_actions":{
            "cash_dividends":[{"id":"event-3","process_date":"2026-11-20"}]},
            "next_page_token":None}).encode()
        rows,token,digest,malformed,unknown,links=refmod.parse_page(data,set(NAMES),1)
        self.assertEqual(len(rows),0)
        self.assertEqual(malformed,1)
        self.assertEqual(links[0]["identity_schema"],
                         "UNEXPECTED_OR_UNLINKABLE_IDENTITY_HOLD")

    def test_identity_only_records_do_not_increment_canonical_dividend_counts(self):
        payload=json.dumps({"corporate_actions":{
            "name_changes":[{"id":"E","old_symbol":"FB","new_symbol":"META",
                             "process_date":"2022-06-09"}]},
            "next_page_token":None}).encode()
        with patch.dict("os.environ",{"ALPACA_API_KEY_ID":"K",
                                      "ALPACA_API_SECRET_KEY":"S"}):
            result=refmod.collect(NAMES,SESSION,fetcher=lambda *_a,**_kw:payload)
        self.assertEqual(result["event_count"],0)
        self.assertEqual(result["unmapped_historical_identity_count"],1)
        self.assertEqual(result["role_based_identity_event_count"],1)
        self.assertEqual(result["queried_symbol_role_link_candidates"],1)
        self.assertEqual(result["status"],"ALPACA_ACTIONS_INCOMPLETE_OR_UNKNOWN_HOLD")
        self.assertFalse(result["historical_identity_certified"])


class ForensicsEndToEndTests(unittest.TestCase):
    def test_complete_offline_25_ticker_repository_contract(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            factor=root/"factor"
            factor.mkdir()
            rows=[]
            for sym in NAMES:
                name=sym.lower()+".csv.gz"
                day="2021-12-16"
                with gzip.open(factor/name,"wt",newline="") as f:
                    w=csv.DictWriter(f,fieldnames=[
                        "session","yahoo_dividend","yahoo_stock_split"])
                    w.writeheader()
                    w.writerow({"session":day,"yahoo_dividend":
                                "0.296" if sym=="HYG" else "0",
                                "yahoo_stock_split":"0"})
                row={"symbol":sym,"csv_gzip_file":name}
                if sym=="HYG":
                    name2=sym.lower()+"_repaired.csv.gz"
                    with gzip.open(factor/name2,"wt",newline="") as f:
                        w=csv.DictWriter(f,fieldnames=[
                            "session","yahoo_dividend","yahoo_stock_split"])
                        w.writeheader()
                        w.writerow({"session":day,"yahoo_dividend":"0","yahoo_stock_split":"0"})
                    row["repaired_csv_gzip_file"]=name2
                rows.append(row)
            (factor/"report.json").write_text(json.dumps({
                "session":SESSION,"rows":rows}))
            r=source()
            r["events"]=[event("HYG","2021-12-16",0.29623,"id1"),
                         event("QQQ","2020-09-21",0.38824,"id2")]
            r["unmapped_historical_identity_count"]=1
            r["role_based_identity_event_count"]=1
            r["queried_symbol_role_link_candidates"]=1
            r["unmapped_historical_identity_examples"]=[
                {"group":"name_changes","event_id":"name1",
                 "process_date":"2022-06-09",
                 "identity_roles":{"old_symbol":"FB","new_symbol":"META"},
                 "queried_symbol_role_candidates":{"new_symbol":"META"},
                 "identity_schema":"EXPECTED_EVENT_TYPE_ROLE_FIELDS_UNCERTIFIED"}]
            ref_path=root/"ref.json"
            ref_path.write_text(json.dumps(r))
            comp=root/"compare"
            comp.mkdir()
            (comp/"report.json").write_text(json.dumps({
                "session":SESSION,"research_only":True,"finality_verified":0,
                "independent_factor_certification":0}))
            with (comp/"event_comparison.csv").open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=[
                    "symbol","ex_date","kind","status","yahoo_value","alpaca_value"])
                w.writeheader()
                w.writerow(case_row("HYG","2021-12-16",
                    "ALPACA_ONLY_EVENT_HOLD"))
                w.writerow(case_row("QQQ","2020-09-21",
                    "ALPACA_ONLY_EVENT_HOLD"))
            report=fx.run(factor,ref_path,comp,root/"out",spec=SPEC)
            self.assertEqual(report["review_exception_count"],2)
            self.assertEqual(report["yahoo_repair_suppression_observed"],1)
            self.assertEqual(report["identity_role_schema_events"],1)
            self.assertEqual(report["identity_examples_preserved"],1)
            self.assertEqual(report["finality_verified"],0)
            self.assertEqual(report["issue_resolutions_issuer_verified"],0)
            with (root/"out"/"review_queue.csv").open() as f:
                cases=list(csv.DictReader(f))
            self.assertEqual(len(cases),2)
            self.assertFalse(any(x["resolved_by_issuer_evidence"]=="True" for x in cases))
            self.assertTrue((root/"out"/"identity_links.csv").exists())


if __name__=="__main__":
    unittest.main()
