"""Fail-closed tests for primary listing, SIP M venues, adjusted price boundary."""
from __future__ import annotations

import json
import os
from unittest import TestCase,main
from unittest.mock import patch
from urllib.error import HTTPError

import resolve_primary_listing as pl
from daily20 import load_spec

SESSION="2026-11-20"
SPEC=load_spec()
EQUITIES=SPEC["core"]+[x for x in SPEC["context"] if x!="^VIX"]
REGISTRY={"P":"NYSE Arca","Q":"NASDAQ Stock Market",
          "N":"New York Stock Exchange", "T":"NYSE National"}

def fake_source(quotes_by_asset=None):
    source={}
    for s in EQUITIES:
        prices=(quotes_by_asset or {}).get(s, [("Q",101.),("P",102.)])
        source[s]={"status":"MULTI_VENUE_OFFICIAL_CLOSE_PRICES_CONFLICT",
                   "quotes":[{"exchange":ex,"price":price,"condition":"M",
                              "timestamp_utc":"2026-11-20T21:00:00Z"}
                             for ex,price in prices]}
    return {"version":"daily20-independent-feed-diagnostics-v1",
            "session":SESSION,
            "alpaca":{"symbols":source,"raw_response_sha256":["x"*64]}}

REFERENCE={"schema":"daily20-quote-reference-v1","session":SESSION,
           "research_only":True,
           "quotes":[{"symbol":"^VIX","quote_type":"REGULAR_CLOSE",
                      "price":35.89,"adjustment":"RAW",
                      "provider":"Cboe","feed":"VIX_Index_History",
                      "observed_at_utc":"2026-11-20T21:00:00Z",
                      "fetched_at_utc":"2026-11-21T07:00:00Z"}]}


class PrimaryVenueTests(TestCase):
    def test_exchange_aliases_strict_and_options_trf_rejected(self):
        self.assertEqual(pl.canonical_exchange("NYSEARCA"),"NYSE_ARCA")
        self.assertEqual(pl.canonical_exchange("NASDAQ"),"NASDAQ")
        self.assertEqual(pl.canonical_exchange("New York Stock Exchange"),"NYSE")
        self.assertIsNone(pl.canonical_exchange("Nasdaq TRF"))
        self.assertIsNone(pl.canonical_exchange("NYSE Arca Options"))
        self.assertIsNone(pl.canonical_exchange("Unknown Stock Exchange"))

    def test_nasdaq_selects_Q_even_though_arca_close_differs(self):
        selected=pl.resolve("NASDAQ",REGISTRY,[
            {"exchange":"P","condition":"M","price":610.14},
            {"exchange":"Q","condition":"M","price":608.45}])
        self.assertEqual(selected["status"],
            "PROVIDER_DECLARED_PRIMARY_M_PRINT_RESEARCH_ONLY")
        self.assertEqual(selected["venue_codes"],["Q"])
        self.assertEqual(selected["selected"]["price"],608.45)

    def test_nyse_selects_N_not_T_or_P(self):
        selected=pl.resolve("NYSE",REGISTRY,[
            {"exchange":"P","condition":"M","price":20.74},
            {"exchange":"T","condition":"M","price":20.76},
            {"exchange":"N","condition":"M","price":20.72}])
        self.assertEqual(selected["selected"]["price"],20.72)
        self.assertEqual(selected["venue_codes"],["N"])

    def test_primary_code_ambiguous_will_not_use_price_proximity(self):
        ambiguous={**REGISTRY,"X":"NASDAQ Stock Market"}
        selected=pl.resolve("NASDAQ",ambiguous,[
            {"exchange":"Q","condition":"M","price":608.45}])
        self.assertEqual(selected["status"],"EXCHANGE_CODE_AMBIGUOUS")
        self.assertIsNone(selected["selected"])

    def test_primary_M_missing_no_secondary_fallback(self):
        selected=pl.resolve("NYSE",REGISTRY,[
            {"exchange":"P","condition":"M","price":102.}])
        self.assertEqual(selected["status"],"PRIMARY_VENUE_M_PRINT_MISSING")
        self.assertIsNone(selected["selected"])

    def test_primary_multiple_M_no_silent_first(self):
        selected=pl.resolve("NYSE",REGISTRY,[
            {"exchange":"N","condition":"M","price":100.},
            {"exchange":"N","condition":"M","price":101.}])
        self.assertEqual(selected["status"],"PRIMARY_VENUE_MULTIPLE_M_PRINTS")
        self.assertIsNone(selected["selected"])

    def test_historic_PLTR_migration_not_retrojected(self):
        self.assertEqual(pl.classify_session_listing("PLTR","2024-11-25","NASDAQ"),
                         "HISTORIC_LISTING_TRANSFER_MISMATCH_HOLD")
        self.assertEqual(pl.classify_session_listing("PLTR","2024-11-26","NASDAQ"),
                         "CURRENT_MASTER_AS_OF_FETCH_ONLY_NOT_HISTORIC_CERTIFICATION")

    def test_all_25_primary_selections_are_raw_uncertified(self):
        known={"QQQ":[("Q",608.45),("P",610.14)],
               "SPY":[("Q",690.4),("P",689.81)],
               "IONQ":[("N",20.72),("P",20.74),("T",20.76)]}
        data=fake_source(known)
        def fetch(url,headers=None,**kwargs):
            self.assertNotIn("password",url)
            if url==pl.EXCHANGE_ENDPOINT:
                return json.dumps(REGISTRY).encode()
            symbol=url.rsplit("/",1)[-1]
            exchange=("NYSEARCA" if symbol=="SPY" else
                      "NYSE" if symbol=="IONQ" else "NASDAQ")
            return json.dumps({"id":"id-"+symbol,"symbol":symbol,
                               "exchange":exchange,"status":"active"}).encode()
        with patch.dict(os.environ,{
            "ALPACA_API_KEY_ID":"UNIT_KEY", "ALPACA_API_SECRET_KEY":"UNIT_SECRET",
            "APCA_API_KEY_ID":"","APCA_API_SECRET_KEY":""
        }):
            report,ref=pl.audit(data,REFERENCE,SPEC,fetcher=fetch,stamp="2026-11-21T07:10:00Z")
        self.assertEqual(report["asset_metadata_count"],25)
        self.assertEqual(report["total_equities_etfs"],25)
        self.assertEqual(report["primary_M_quote_research_selection_count"],25)
        self.assertEqual(report["finality_verified"],0)
        self.assertFalse(report["raw_and_yahoo_adjusted_directly_comparable"])
        self.assertEqual(len(ref["quotes"]),26)
        refs={x["symbol"]:x for x in ref["quotes"]}
        self.assertEqual(refs["QQQ"]["price"],608.45)
        self.assertEqual(refs["SPY"]["price"],689.81)
        self.assertEqual(refs["IONQ"]["price"],20.72)
        self.assertEqual(refs["SPY"]["exchange"],"P")
        self.assertEqual(refs["QQQ"]["exchange"],"Q")
        self.assertEqual(refs["IONQ"]["exchange"],"N")
        self.assertTrue(all(item["adjustment"]=="RAW" for item in ref["quotes"]))
        self.assertTrue(all(item.get("independently_exchange_certified_at_16_00") is False
                            for item in ref["quotes"] if item["symbol"]!="^VIX"))
        self.assertNotIn("UNIT_SECRET",json.dumps(report))
        self.assertNotIn("UNIT_SECRET",json.dumps(ref))

    def test_no_credentials_do_not_result_in_fake_primary_quotes(self):
        with patch.dict(os.environ,{
            "ALPACA_API_KEY_ID":"","ALPACA_API_SECRET_KEY":"",
            "APCA_API_KEY_ID":"","APCA_API_SECRET_KEY":""
        }):
            report,ref=pl.audit(fake_source(),REFERENCE,SPEC,fetcher=lambda *a,**k:(
                self.fail("should not fetch")))
        self.assertEqual(report["primary_M_quote_research_selection_count"],0)
        self.assertEqual(report["selected_reference_count_including_cboe"],1)
        self.assertTrue(all(x["primary_selection_status"]=="CREDENTIALS_NOT_CONFIGURED"
                            for x in report["rows"]))

    def test_asset_lookup_401_is_hold(self):
        with patch.dict(os.environ,{
            "ALPACA_API_KEY_ID":"UNIT_KEY","ALPACA_API_SECRET_KEY":"UNIT_SECRET",
            "APCA_API_KEY_ID":"","APCA_API_SECRET_KEY":""
        }):
            def reject(url,headers=None,**kwargs):
                raise HTTPError(url,401,"Unauthorized",None,None)
            assets=pl.fetch_assets(["SPY"],fetcher=reject)
        self.assertEqual(assets["SPY"]["status"],"ASSET_LOOKUP_UNAVAILABLE")
        self.assertEqual(assets["SPY"]["error_class"],"HTTP_401")


if __name__=="__main__":
    main()
