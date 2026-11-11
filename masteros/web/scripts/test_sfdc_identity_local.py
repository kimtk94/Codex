#!/usr/bin/env python3
"""No browser and no CRM writes; test the private index on a synthetic sqlite DB."""
import datetime as dt
import pathlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from sfdc_identity_local import read_identity_index

NOW=dt.datetime(2026,11,10,10,tzinfo=dt.timezone.utc)

class SearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=pathlib.Path(self.tmp.name)/"safe.db"
        with closing(sqlite3.connect(self.path)) as cx:
            cx.executescript("""
              CREATE TABLE meta(k TEXT PRIMARY KEY,v TEXT NOT NULL);
              CREATE TABLE quote_reference(
                qid TEXT,quote_record_id TEXT,account_id TEXT,account_name TEXT,contact_id TEXT,
                contact_external_id TEXT,contact_name TEXT,contact_email TEXT);
            """)
            cx.executemany("INSERT INTO meta VALUES(?,?)",[
              ("quote_count","4"),
              ("index_refreshed_utc","2026-11-10T09:30:00+00:00")
            ])
            cx.executemany("INSERT INTO quote_reference VALUES(?,?,?,?,?,?,?,?)",[
              ("QID-4","a0P000000000000AAA","001000000000000AAA","연세대학교","003000000000000AAA","","김지훈","a@x.test"),
              ("QID-3","a0P000000000000AAB","001000000000000AAB","의료원","003000000000000AAB","","김지훈","b@x.test"),
              ("QID-2","a0P000000000000AAA","001000000000000AAA","연세대학교","003000000000000AAA","","김지훈","a@x.test"),
              ("QID-1","","001000000000000AAC","","003000000000000AAC","","김지훈","c@x.test")
            ])
            cx.commit()
    def tearDown(self):self.tmp.cleanup()

    def test_names_always_have_institution_and_distinct_homonyms(self):
        result=read_identity_index("김지훈",now=NOW,db=self.path)
        self.assertEqual(result["status"],"PASS")
        self.assertEqual(result["freshness"],"FRESH")
        self.assertEqual(len(result["rows"]),2)
        self.assertEqual({r["account_name"] for r in result["rows"]},{"연세대학교","의료원"})
        self.assertTrue(all(r["crm_contact_verified"] for r in result["rows"]))
        self.assertTrue(all(r["source_quote_id"].startswith("a0P") for r in result["rows"]))
    def test_institution_query_finds_attached_contact(self):
        result=read_identity_index("연세",now=NOW,db=self.path)
        self.assertEqual(len(result["rows"]),1)
        self.assertEqual(result["rows"][0]["contact_name"],"김지훈")
    def test_escaped_wildcards_not_wide_database_scan(self):
        self.assertEqual(read_identity_index("%",now=NOW,db=self.path)["rows"],[])
        self.assertEqual(read_identity_index("_",now=NOW,db=self.path)["rows"],[])
    def test_selected_account_excludes_same_name_contact_from_other_institutions(self):
        scoped=read_identity_index("김지훈",now=NOW,db=self.path,
                                   account_id="001000000000000AAA")
        self.assertEqual(len(scoped["rows"]),1)
        self.assertEqual(scoped["rows"][0]["account_name"],"연세대학교")
        self.assertEqual(scoped["account_filter"],"001000000000000AAA")
        other=read_identity_index("김지훈",now=NOW,db=self.path,
                                  account_id="001000000000000AAB")
        self.assertEqual(len(other["rows"]),1)
        self.assertEqual(other["rows"][0]["account_name"],"의료원")
        with self.assertRaisesRegex(ValueError,"ACCOUNT_FILTER_INVALID"):
            read_identity_index("김지훈",now=NOW,db=self.path,account_id="001bad")
    def test_stale_flag_is_not_fabricated_fresh(self):
        late=NOW+dt.timedelta(days=5)
        self.assertEqual(read_identity_index("김",now=late,db=self.path)["freshness"],"STALE")
    def test_index_coverage_mismatch_blocks(self):
        with closing(sqlite3.connect(self.path)) as cx:
            cx.execute("UPDATE meta SET v='100' WHERE k='quote_count'")
            cx.commit()
        with self.assertRaisesRegex(ValueError,"COVERAGE_MISMATCH"):
            read_identity_index("김",now=NOW,db=self.path)
    def test_invalid_query_blocks(self):
        for x in [""," "*5,"x"*81]:
            with self.assertRaises(ValueError):
                read_identity_index(x,now=NOW,db=self.path)
if __name__=="__main__":unittest.main()
