"""Offline contract tests for Cboe VIX and Alpaca SIP auction-source ingestion."""
from __future__ import annotations

from datetime import date,timedelta
import json
import os
from unittest.mock import patch
from urllib.error import HTTPError
import unittest

import collect_independent_close as ci

DATE="2026-11-20"
ANCHOR="2026-11-20T21:00:00Z"

def official_csv():
    start=date(2024,1,1)
    rows=["Last updated by Cboe, not an OHLC price row",
          "DATE,OPEN,HIGH,LOW,CLOSE"]
    for n in range(1000):
        d=start+timedelta(days=n)
        rows.append(f"{d.strftime('%m/%d/%Y')},18.0,19.0,17.0,18.5")
    rows.append("11/20/2026,22.0,23.0,21.0,22.45")
    return ("\n".join(rows)+"\n").encode()

def official_record(price=101.,exchange="Q",condition="M",stamp=ANCHOR):
    return {"c":condition,"p":price,"t":stamp,"x":exchange}

def alpaca_payload(names,*,changed=None):
    return json.dumps({"auctions":{
        symbol:[{"d":DATE,"c":[
            official_record(100.,exchange="Q"),
            official_record(100.,exchange="Q",condition="6"),
        ],"o":[]}]
        for symbol in names
    },"next_page_token":None}).encode()

def no_credentials():
    return patch.dict(os.environ,{"ALPACA_API_KEY_ID":"","APCA_API_KEY_ID":"",
                "ALPACA_API_SECRET_KEY":"","APCA_API_SECRET_KEY":""})

class IndependentFeedTests(unittest.TestCase):
    def test_cboe_header_preface_date_and_close(self):
        report=ci.parse_cboe_csv(official_csv(),DATE)
        self.assertEqual(report["close"],22.45)
        self.assertEqual(report["latest_published_session"],DATE)
        self.assertEqual(report["historical_rows"],1001)
        self.assertEqual(len(report["body_sha256"]),64)

    def test_cboe_session_absent_is_not_approved(self):
        report=ci.parse_cboe_csv(official_csv(),"2026-11-23")
        self.assertIsNone(report["close"])
        self.assertEqual(report["latest_published_session"],DATE)

    def test_cboe_header_and_duplicate_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"HEADER_MISSING"):
            ci.parse_cboe_csv(b"foo\nnoheader\n",DATE)
        with self.assertRaisesRegex(RuntimeError,"DUPLICATE_SESSION"):
            ci.parse_cboe_csv(official_csv()+b"11/20/2026,1,2,3,4\n",DATE)

    def test_auction_market_center_condition_and_symbol_day(self):
        received={"SPY":[{"d":DATE,"c":[
            official_record(699.,condition="6"),
            official_record(689.81,condition="M"),
        ],"o":[]}],"QQQ":[]}
        results=ci.parse_alpaca_auctions(received,DATE,["SPY","QQQ"])
        self.assertEqual(results["SPY"]["quotes"][0]["price"],689.81)
        self.assertEqual(results["SPY"]["status"],
             "SIP_OFFICIAL_CONDITION_WITHOUT_LISTING_VENUE_CERTIFICATION")
        self.assertEqual(results["QQQ"]["status"],"NO_SESSION_AUCTIONS")

    def test_conflicting_close_venues_do_not_produce_reference(self):
        data={"SPY":[{"d":DATE,"c":[
            official_record(689.81,"Q"),official_record(690.1,"P")
        ],"o":[]}]}
        parsed=ci.parse_alpaca_auctions(data,DATE,["SPY"])
        self.assertEqual(parsed["SPY"]["status"],
                         "MULTI_VENUE_OFFICIAL_CLOSE_PRICES_CONFLICT")
        self.assertEqual(len(parsed["SPY"]["quotes"]),2)

    def test_afterhours_timestamp_rejected_even_if_condition_M(self):
        data={"SPY":[{"d":DATE,"c":[
            official_record(697.49,"Q",stamp="2026-11-21T02:00:00Z")
        ],"o":[]}]}
        parsed=ci.parse_alpaca_auctions(data,DATE,["SPY"])
        self.assertEqual(parsed["SPY"]["status"],
                         "NO_VALID_MARKET_CENTER_OFFICIAL_CLOSE")

    def test_late_afterhours_with_official_condition_is_not_accepted(self):
        # Do not confuse a late print with the 16:00 ET closing auction.
        data={"SPY":[{"d":DATE,"c":[
            official_record(697.49,"Q",stamp="2026-11-20T21:30:00Z")
        ],"o":[]}]}
        parsed=ci.parse_alpaca_auctions(data,DATE,["SPY"])
        self.assertEqual(parsed["SPY"]["status"],
                         "NO_VALID_MARKET_CENTER_OFFICIAL_CLOSE")

    def test_vix_is_no_longer_yahoo_only_without_api_keys(self):
        names=["^VIX"]+[f"STOCK{i:02d}" for i in range(25)]
        def fake(url,headers=None,**kwargs):
            self.assertEqual(url,ci.CBOE_URL)
            return official_csv()
        with no_credentials():
            report,reference=ci.collect(DATE,names,fetcher=fake)
        self.assertEqual(report["cboe"]["status"],"CBOE_OFFICIAL_VIX_HISTORY_PRESENT")
        self.assertEqual(report["alpaca"]["status"],"CREDENTIALS_NOT_CONFIGURED")
        self.assertEqual(len(reference["quotes"]),1)
        vix=reference["quotes"][0]
        self.assertEqual(vix["symbol"],"^VIX")
        self.assertEqual(vix["price"],22.45)
        self.assertEqual(vix["adjustment"],"RAW")
        self.assertFalse(vix["independently_exchange_certified_at_16_00"])
        self.assertFalse(vix["independently_exchange_certified_at_scheduled_close"])
        self.assertEqual(report["verified_regular_finality"],0)
        self.assertFalse(report["strategy_promoted"])

    def test_alpaca_secrets_are_never_in_json_evidence_and_25_feed_items(self):
        names=["^VIX"]+[f"STOCK{i:02d}" for i in range(25)]
        def fake(url,headers=None,**kwargs):
            if url==ci.CBOE_URL:
                return official_csv()
            self.assertIn("/v2/stocks/auctions?",url)
            self.assertIn("feed=sip",url)
            self.assertEqual(headers["APCA-API-KEY-ID"],"SECRET_KEY_SAMPLE")
            return alpaca_payload(names[1:])
        with patch.dict(os.environ,{
            "ALPACA_API_KEY_ID":"SECRET_KEY_SAMPLE",
            "ALPACA_API_SECRET_KEY":"SECRET_SECRET_SAMPLE",
            "APCA_API_KEY_ID":"","APCA_API_SECRET_KEY":"",
        }):
            report,reference=ci.collect(DATE,names,fetcher=fake)
        self.assertEqual(len(reference["quotes"]),26)
        self.assertEqual(report["alpaca"]["status"],"RESPONSE_RECEIVED_UNCERTIFIED")
        self.assertEqual(report["verified_regular_finality"],0)
        self.assertFalse(report["quote_type_certified"])
        self.assertNotIn("SECRET_KEY_SAMPLE",json.dumps(report))
        self.assertNotIn("SECRET_SECRET_SAMPLE",json.dumps(report))
        self.assertFalse(any(row["independently_exchange_certified_at_16_00"]
                             for row in reference["quotes"]))

    def test_missing_entitlement_must_stay_missing_and_hold(self):
        names=["SPY"]
        def deny(url,headers=None,**kwargs):
            raise HTTPError(url,403,"forbidden",None,None)
        with patch.dict(os.environ,{
            "ALPACA_API_KEY_ID":"SECRET_KEY_SAMPLE",
            "ALPACA_API_SECRET_KEY":"SECRET_SECRET_SAMPLE",
            "APCA_API_KEY_ID":"","APCA_API_SECRET_KEY":"",
        }):
            result=ci.fetch_alpaca(DATE,names,fetcher=deny)
        self.assertEqual(result["status"],"SOURCE_UNAVAILABLE")
        self.assertEqual(result["reason"],"HTTP_403")
        self.assertEqual(result["symbols"]["SPY"]["status"],
                         "ALPACA_SOURCE_UNAVAILABLE")

    def test_session_anchor_uses_timezone_and_dst(self):
        self.assertEqual(ci._session_anchor(DATE),"2026-11-20T21:00:00Z")
        self.assertEqual(ci._session_anchor("2026-07-01"),"2026-07-01T20:00:00Z")
        self.assertEqual(ci._session_anchor("2026-11-27"),"2026-11-27T18:00:00Z")

    def test_early_close_market_center_M_print_is_accepted(self):
        early="2026-11-27"
        stamp="2026-11-27T18:00:00Z"  # 13:00 ET, Black Friday early close
        parsed=ci.parse_alpaca_auctions(
            {"SPY":[{"d":early,"c":[official_record(689.81,"P",stamp=stamp)],"o":[]}]},
            early,["SPY"])
        self.assertEqual(parsed["SPY"]["status"],
            "SIP_OFFICIAL_CONDITION_WITHOUT_LISTING_VENUE_CERTIFICATION")
        self.assertEqual(parsed["SPY"]["quotes"][0]["timestamp_utc"],stamp)

    def test_early_close_window_rejects_late_or_16_et_prints(self):
        early="2026-11-27"
        for stamp in ("2026-11-27T18:30:00Z","2026-11-27T21:00:00Z"):
            parsed=ci.parse_alpaca_auctions(
                {"SPY":[{"d":early,"c":[official_record(689.81,"P",stamp=stamp)],"o":[]}]},
                early,["SPY"])
            self.assertEqual(parsed["SPY"]["status"],
                "NO_VALID_MARKET_CENTER_OFFICIAL_CLOSE")

    def test_non_xnys_holiday_has_no_scheduled_close(self):
        with self.assertRaisesRegex(RuntimeError,"AUCTION_SESSION_NOT_XNYS_SESSION"):
            ci._session_anchor("2026-11-26")

if __name__=="__main__":
    unittest.main()
