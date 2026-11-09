"""Offline private price cache tests, with synthetic source IDs only."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sfdc_pair_cache as cache
import sfdc_pair_cache_warm as warm

OPP="006000000000000AAA"
QUOTE="a0P000000000000AAA"
LIST_REQ={"resource":"opportunity","mode":"list","query":""}
BUNDLE_REQ={"resource":"opportunity","mode":"bundle","recordId":OPP}


def listing():
    return {"status":"PASS","resource":"opportunity","scope":"SALESFORCE_CURRENT_LIST_VIEW",
        "read_only":True,"records":[{"id":OPP,"name":"Synthetic Account/Oppo"}],
        "count":1,"query":""}


def bundle():
    return {"status":"PASS","read_only":True,"selectionStatus":"EXACT_ONE",
        "resource":"opportunity","mode":"bundle","quoteCount":1,
        "opportunity":{"id":OPP,"source":"LIVE_SALESFORCE","read_only":True,
            "accountId":"001000000000000AAA","contactId":"003000000000000AAA",
            "name":"Synthetic Oppo"},
        "linkedQuotes":[{"id":QUOTE,"opportunityId":OPP,
            "source":"LIVE_SALESFORCE","read_only":True,"totalPriceKrw":2350000,
            "grandTotalKrw":2585000,"productCount":1,"pricingStatus":"PROCESS_BREAKDOWN_UNVERIFIED"}]}


class PrivateCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        p=Path(self.temp.name)
        self.a=patch.object(cache,"CACHE_DIR",p)
        self.b=patch.object(cache,"CACHE_FILE",p/"private.sqlite3")
        self.a.start()
        self.b.start()
        self.addCleanup(self.a.stop)
        self.addCleanup(self.b.stop)

    def test_list_cached_then_expired_no_stale_price(self):
        self.assertTrue(cache.save(LIST_REQ,listing(),now=1000))
        r=cache.lookup(LIST_REQ,now=1005)
        self.assertEqual(r["cache"]["state"],"FRESH_CACHE")
        self.assertEqual(r["cache"]["age_seconds"],5)
        self.assertTrue(r["cache"]["not_live"])
        self.assertEqual(r["records"][0]["id"],OPP)
        self.assertIsNone(cache.lookup(LIST_REQ,now=1900))
        status=cache.stats(now=1900)
        self.assertEqual(status["tiers"]["list"]["fresh"],0)
        self.assertEqual(status["tiers"]["list"]["stale"],1)

    def test_bundle_cache_keeps_unverified_price_a_hold(self):
        self.assertTrue(cache.save(BUNDLE_REQ,bundle(),now=1000))
        cached=cache.lookup(BUNDLE_REQ,now=1199)
        self.assertEqual(cached["linkedQuotes"][0]["pricingStatus"],"PROCESS_BREAKDOWN_UNVERIFIED")
        self.assertTrue(cached["cache"]["not_live"])
        self.assertIsNone(cache.lookup(BUNDLE_REQ,now=2200))

    def test_nonmatching_quote_parent_cannot_be_cached(self):
        x=bundle()
        x["linkedQuotes"][0]["opportunityId"]="006000000000000AAB"
        self.assertFalse(cache.save(BUNDLE_REQ,x,now=1000))
        self.assertIsNone(cache.lookup(BUNDLE_REQ,now=1001))

    def test_no_unique_quote_is_not_cached(self):
        x=bundle();x["selectionStatus"]="NO_MATCH";x["linkedQuotes"]=[]
        self.assertFalse(cache.save(BUNDLE_REQ,x,now=1000))

    def test_authenticated_ui_stamp_required(self):
        x=bundle();x["opportunity"]["source"]="FAKE_SALESFORCE"
        self.assertFalse(cache.save(BUNDLE_REQ,x,now=1000))
        x=bundle();x["read_only"]=False
        self.assertFalse(cache.save(BUNDLE_REQ,x,now=1000))

    def test_search_queries_do_not_use_stale_list_cache(self):
        cache.save(LIST_REQ,listing(),now=1000)
        self.assertIsNone(cache.lookup({"resource":"opportunity","mode":"list","query":"New"},now=1100))
        self.assertIsNone(cache.key_for({"resource":"lead","mode":"detail","recordId":"00Q000000000000AAA"}))

    def test_invalid_json_checksum_fails_closed(self):
        cache.save(BUNDLE_REQ,bundle(),now=1000)
        with sqlite3.connect(cache.CACHE_FILE) as cx:
            cx.execute("UPDATE entries SET payload_json='{}'")
        self.assertIsNone(cache.lookup(BUNDLE_REQ,now=1100))

    def test_replacing_source_refreshes_expiration(self):
        self.assertTrue(cache.save(BUNDLE_REQ,bundle(),now=1000))
        b=bundle();b["linkedQuotes"][0]["totalPriceKrw"]=2300000
        self.assertTrue(cache.save(BUNDLE_REQ,b,now=2100))
        seen=cache.lookup(BUNDLE_REQ,now=2110)
        self.assertEqual(seen["linkedQuotes"][0]["totalPriceKrw"],2300000)
        self.assertEqual(seen["cache"]["checked_at_utc"],"1970-01-01T00:35:00+00:00")

    def test_cache_status_contains_no_customer_ids_or_prices(self):
        cache.save(BUNDLE_REQ,bundle(),now=1000)
        status=json.dumps(cache.stats(now=1100))
        self.assertNotIn(OPP,status)
        self.assertNotIn(QUOTE,status)
        self.assertNotIn("2350000",status)
        self.assertIn('"salesforce_write": false',status)

    def test_max_payload_is_bounded(self):
        x=listing();x["records"][0]["name"]="A"*250000
        self.assertFalse(cache.save(LIST_REQ,x,now=1000))

    def test_read_live_meta_never_claims_real_time_from_cache(self):
        meta=cache.live_meta("bundle",now=1000)
        self.assertFalse(meta["not_live"])
        self.assertEqual(meta["state"],"LIVE_SOURCE")

    def test_refresh_request_bounded(self):
        for x in (
            {"mode":"SAVE","limit":3,"offset":0},
            {"mode":"WARM","limit":6,"offset":0},
            {"mode":"WARM","limit":3,"offset":-1},
            {"mode":"WARM","limit":True,"offset":0},
        ):
            with self.assertRaises(ValueError):
                warm.validate(x)
        self.assertEqual(warm.validate({"mode":"WARM","limit":3,"offset":4}),(3,4))


if __name__=="__main__":
    unittest.main()
