#!/usr/bin/env python3
"""Synthetic tests: no personal data, network, Google Sheets or SFDC writes."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo
import three_report_quote_value_audit as m

QID="QID-2026-11-01-12345"
SF="a0P"+"A"*12
NOW=dt.datetime(2026,11,7,16,0,tzinfo=ZoneInfo("Asia/Seoul"))

def fixture():
    head=["SFDC Quotation ID","Active","Opportunity ID",
          "Total Price USD (converted) Currency","Total Price USD (converted)"]
    entry=[QID,"1","006OPP","USD","374.00"]
    return {
     "SFDC Email Quotation Raw":[head,entry,entry],
     "Quote Approval Dedup":[["Approval KST","Quotation Name","SFDC Record ID"],
                             ["2026-11-05 10:00:00","Sales Quote "+QID+" approved",SF]],
     "Quote Portfolio":[["Salesforce Quote ID (18)","Quote QID","Quote USD"],[SF,QID,"374"]],
     "SFDC Email Ingest Audit":[["Entity","Source Received KST","State"],
                                ["Quotation","2026-11-07 12:00:07 KST","STAGED_NOT_PROMOTED"]],
    }

class QuoteValueTests(unittest.TestCase):
    def test_exact_qid_dedup_across_product_rows(self):
        data=fixture()
        report=m.analyze(data,now=NOW)
        x=report["four_weeks"][-1]
        self.assertEqual(report["product_rows"],2)
        self.assertEqual(report["quote_index"]["unique_qids"],1)
        self.assertEqual(x["approval_evidence_rows"],1)
        self.assertEqual(x["qid_exact_report_match"],1)
        self.assertEqual(x["historic_record_id_confirmed"],1)
        self.assertEqual(x["verified_crosswalk_k_usd"],"0.3740")
        self.assertEqual(report["historic_overlap"]["old_value_equal"],1)
        self.assertIn("SALES_OWNER_SCOPE_NOT_VERIFIED",report["blockers"])
        self.assertNotIn(QID,m.markdown(report))
        self.assertNotIn(SF,m.markdown(report))
    def test_inconsistent_product_values_are_not_added(self):
        data=fixture()
        data["SFDC Email Quotation Raw"][2]=[QID,"1","006OPP","USD","375"]
        r=m.analyze(data,now=NOW)
        self.assertEqual(r["quote_index"]["valid_qids"],0)
        self.assertIn("QUOTE_PRODUCT_ROW_INCONSISTENCIES",r["blockers"])
        self.assertEqual(r["four_weeks"][-1]["verified_crosswalk_k_usd"],"0.0000")
    def test_unmatched_historic_sf_crosswalk_cannot_promote(self):
        data=fixture()
        data["Quote Portfolio"]=[data["Quote Portfolio"][0]]
        r=m.analyze(data,now=NOW)
        x=r["four_weeks"][-1]
        self.assertEqual(x["fresh_active_qid_candidate_only"],1)
        self.assertEqual(x["verified_crosswalk_k_usd"],"0.0000")
    def test_stale_report_and_wrong_active_are_blocked(self):
        data=fixture()
        data["SFDC Email Ingest Audit"][1][1]="2026-10-24 10:00:00 KST"
        data["SFDC Email Quotation Raw"][1][1]="0"
        data["SFDC Email Quotation Raw"][2][1]="0"
        r=m.analyze(data,now=NOW)
        self.assertFalse(r["fresh"])
        self.assertEqual(r["four_weeks"][-1]["report_inactive"],1)
        self.assertIn("3REPORT_QUOTATION_SNAPSHOT_STALE",r["blockers"])
    def test_historic_price_mismatch_not_silent(self):
        data=fixture()
        data["Quote Portfolio"][1][2]="500"
        r=m.analyze(data,now=NOW)
        self.assertEqual(r["historic_overlap"]["old_value_conflicts"],1)
        self.assertIn("HISTORIC_PRICE_PARITY_MISMATCH",r["blockers"])
    def test_qid_requires_one_precise_identifier(self):
        self.assertEqual(m.single_qid("Quotation "+QID+" complete"),QID)
        self.assertIsNone(m.single_qid("Missing QID"))
        self.assertIsNone(m.single_qid(QID+" and QID-2026-11-02-9876"))
        self.assertIsNone(m.single_qid("prefix"+QID))
        self.assertIsNone(m.money("2e4"))
        self.assertIsNone(m.strict_active("Pending"))
    def test_report_row_key_and_schema_validation(self):
        with self.assertRaisesRegex(ValueError,"SCHEMA"):
            m.rows([["Quotation ID"],["QID"]],m.REQUIRED["SFDC Email Quotation Raw"])
        self.assertEqual(m.sf15(SF+"XYZ"),SF)

if __name__=="__main__":
    unittest.main()
