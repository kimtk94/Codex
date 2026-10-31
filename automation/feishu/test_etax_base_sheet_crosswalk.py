"""Offline invariants for Feishu Base-vs-dated eTax evidence (no secrets)."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo
from etax_base_sheet_crosswalk import crosswalk,column_map,flatten,invoice_id,money

NOW=dt.datetime(2026,10,31,16,30,tzinfo=ZoneInfo("Asia/Seoul"))
DATE=dt.date(2026,10,26)

class CrosswalkTests(unittest.TestCase):
    def test_exact_join_cannot_certify_paid_or_current_month(self):
        base=[{"CMS":"209126001012","ERP":"209102181","AMOUNT":1100},
              {"CMS":"209126001013","ERP":"209102182","AMOUNT":2200}]
        dated=[{"CMS":"209126001012","ERP":"209102181","AMOUNT":1100},
               {"CMS":"209126001013","ERP":"209102182","AMOUNT":2200}]
        rows,metrics=crosswalk(base,dated,DATE,NOW)
        self.assertEqual(metrics["exact_matches"],2)
        self.assertEqual(metrics["source_age_days"],5)
        self.assertEqual(metrics["payment_certified"],0)
        self.assertEqual(metrics["issuance_certified"],0)
        self.assertTrue(all(r[7]=="NOT_VERIFIED" for r in rows))
        self.assertTrue(all(r[4]=="ID_AND_AMOUNT_MATCHED_SNAPSHOT_ONLY" for r in rows))

    def test_conflicting_amount_does_not_become_a_valid_match(self):
        base=[{"CMS":"209126001012","ERP":"","AMOUNT":1100}]
        dated=[{"CMS":"209126001012","ERP":"","AMOUNT":1200}]
        rows,stats=crosswalk(base,dated,DATE,NOW)
        self.assertEqual(stats["exact_matches"],0)
        self.assertEqual(rows[0][4],"ID_MATCH_AMOUNT_CONFLICT")

    def test_duplicate_dated_id_must_not_join_arbitrarily(self):
        base=[{"CMS":"209126001012","ERP":"","AMOUNT":1100}]
        dated=[{"CMS":"209126001012","ERP":"","AMOUNT":1100},
               {"CMS":"209126001012","ERP":"","AMOUNT":1100}]
        rows,stats=crosswalk(base,dated,DATE,NOW)
        self.assertEqual(stats["exact_matches"],0)
        self.assertEqual(rows[0][4],"AMBIGUOUS_SNAPSHOT_MATCH")

    def test_base_only_and_dated_only_are_review_not_paid(self):
        base=[{"CMS":"209126001014","ERP":"","AMOUNT":1100}]
        dated=[{"CMS":"209126001012","ERP":"","AMOUNT":1100}]
        rows,stats=crosswalk(base,dated,DATE,NOW)
        self.assertEqual(rows[0][4],"BASE_ONLY_NOT_IN_DATED_SNAPSHOT")
        self.assertEqual(rows[1][4],"DATED_ONLY_OR_UNRESOLVED_REVIEW")
        self.assertEqual(stats["exact_matches"],0)

    def test_multiple_ids_matching_different_rows_rejected(self):
        base=[{"CMS":"209126001012","ERP":"209102181","AMOUNT":1100}]
        dated=[{"CMS":"209126001012","ERP":"209102182","AMOUNT":1100},
               {"CMS":"209126001013","ERP":"209102181","AMOUNT":1100}]
        rows,stats=crosswalk(base,dated,DATE,NOW)
        self.assertEqual(rows[0][4],"AMBIGUOUS_SNAPSHOT_MATCH")
        self.assertEqual(stats["exact_matches"],0)

    def test_bad_source_date_and_future_date_refuse_a_match(self):
        base=[{"CMS":"209126001012","ERP":"","AMOUNT":1100}]
        for date in [dt.date(2026,9,30),dt.date(2026,11,1)]:
            with self.assertRaisesRegex(ValueError,"SNAPSHOT_MONTH_UNVERIFIED"):
                crosswalk(base,base,date,NOW)

    def test_alias_fields_and_invalid_values(self):
        c=column_map(["ERP Invoice Number","CMS Invoice Num","Amount"])
        self.assertEqual(c,{"CMS":1,"ERP":0,"AMOUNT":2})
        row=flatten([["209102181","209126001012","1,100.00"]],c)
        self.assertEqual(row,[{"CMS":"209126001012","ERP":"209102181","AMOUNT":1100}])
        self.assertEqual(money("abc"),None)
        self.assertEqual(invoice_id("Customer Name"),"")
        with self.assertRaisesRegex(ValueError,"AMBIGUOUS_COLUMN_CMS"):
            column_map(["CMS Invoice Num","CMS Invoice Number","Amount"])

if __name__=="__main__":unittest.main()
