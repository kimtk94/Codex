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
          "Total Price USD (converted) Currency","Total Price USD (converted)",
          "Quotation Product ID","Unit Price USD","Sample Quantity"]
    entry=[QID,"1","006OPP","USD","374.00","QD-TEST-1","350","1"]
    return {
     "SFDC Email Quotation Raw":[head,entry.copy(),entry.copy()],
     "Quote Approval Dedup":[["Approval KST","Quotation Name","SFDC Record ID"],
                             ["2026-11-05 10:00:00","Sales Quote "+QID+" approved",SF]],
     "Quote Portfolio":[["Salesforce Quote ID (18)","Quote QID","Quote USD"],[SF,QID,"374"]],
     "SFDC Email Ingest Audit":[["Entity","Source Received KST","State"],
                                ["Quotation","2026-11-07 12:00:07 KST","STAGED_NOT_PROMOTED"]],
     "SFDC Email Opportunities Raw":[["Opportunity ID","Opportunity Owner","Amount Currency"],
                                     ["006OPP","Kim Taehoon","USD"]],
     "SFDC Import Opportunities":[["Opportunity ID","Opportunity Owner"],
                                  ["006OPP","Kim Taehoon"]],
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
        self.assertEqual(x["my_owner_verified"],1)
        self.assertEqual(x["amount_display"],"WITHHELD_UNIT_PARITY")
        self.assertEqual(report["historic_overlap"]["old_value_equal"],1)
        self.assertEqual(report["portfolio_unit_check"]["direct_usd_parity"],1)
        self.assertNotIn("OWNER_SCOPE_REVIEW_REQUIRED",report["blockers"])
        self.assertNotIn(QID,m.markdown(report))
        self.assertNotIn(SF,m.markdown(report))
    def test_inconsistent_product_values_are_not_added(self):
        data=fixture()
        data["SFDC Email Quotation Raw"][2]=[QID,"1","006OPP","USD","375","QD-TEST-1","350","1"]
        r=m.analyze(data,now=NOW)
        self.assertEqual(r["quote_index"]["valid_qids"],0)
        self.assertIn("QUOTE_PRODUCT_ROW_INCONSISTENCIES",r["blockers"])
        self.assertEqual(r["four_weeks"][-1]["amount_display"],"WITHHELD_UNIT_PARITY")
    def test_unmatched_historic_sf_crosswalk_cannot_promote(self):
        data=fixture()
        data["Quote Portfolio"]=[data["Quote Portfolio"][0]]
        r=m.analyze(data,now=NOW)
        x=r["four_weeks"][-1]
        self.assertEqual(x["fresh_active_qid_candidate_only"],1)
        self.assertEqual(x["amount_display"],"WITHHELD_UNIT_PARITY")
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
    def test_owner_must_match_exact_verified_opportunity(self):
        data=fixture()
        data["SFDC Email Opportunities Raw"][1][1]="Other Sales Owner"
        result=m.analyze(data,now=NOW)
        latest=result["four_weeks"][-1]
        self.assertEqual(latest.get("my_owner_verified",0),0)
        self.assertEqual(latest["other_sales_owner_verified"],1)
        self.assertIn("OWNER_SCOPE_REVIEW_REQUIRED",result["blockers"])
        data["SFDC Email Opportunities Raw"][1][1]="Kim Taehoon"
        data["SFDC Email Opportunities Raw"][1][0]="DIFFERENT_OPP"
        result=m.analyze(data,now=NOW)
        self.assertEqual(result["four_weeks"][-1]["owner_unresolved"],1)
    def test_ratio_1500_detected_but_not_applied_as_usd(self):
        data=fixture()
        data["Quote Portfolio"][1][2]="561000"  # 374 * 1500, no unit proof
        result=m.analyze(data,now=NOW)
        self.assertEqual(result["portfolio_unit_check"]["ratio_near_1500"],1)
        self.assertIn("SOURCE_AMOUNT_UNIT_CONFLICT",result["blockers"])
        self.assertEqual(result["four_weeks"][-1]["amount_display"],"WITHHELD_UNIT_PARITY")
    def test_currency_specific_ratio_and_product_sanity_are_not_quote_total(self):
        data=fixture()
        # Independent product unit price * quantity: 4200 USD, not 3 USD.
        data["SFDC Email Quotation Raw"][1][4]="3"
        data["SFDC Email Quotation Raw"][2][4]="3"
        data["SFDC Email Quotation Raw"][1][6]="4200"
        data["SFDC Email Quotation Raw"][2][6]="4200"
        data["SFDC Email Opportunities Raw"][1][2]="KRW"
        data["Quote Portfolio"][1][2]="4500"
        result=m.analyze(data,now=NOW)
        evidence=result["currency_and_unit_evidence"]["by_opportunity_currency"]["KRW"]
        self.assertEqual(evidence["compared"],1)
        self.assertEqual(evidence["ratio_near_1500"],1)
        self.assertEqual(evidence["historic_close_to_unit_sum_10pct"],1)
        self.assertEqual(evidence["price_unit_sum_present"],1)
        self.assertEqual(result["four_weeks"][-1]["amount_display"],"WITHHELD_UNIT_PARITY")
    def test_inconsistent_duplicate_product_price_does_not_sum(self):
        data=fixture()
        data["SFDC Email Quotation Raw"][2][6]="200"
        result=m.analyze(data,now=NOW)
        self.assertEqual(result["currency_and_unit_evidence"]["ambiguous_product_prices"],1)
        self.assertEqual(result["currency_and_unit_evidence"]["by_opportunity_currency"]["USD"]["price_unit_sum_present"],0)
    def test_missing_opportunity_held_when_absent_in_both_exports(self):
        data=fixture()
        data["SFDC Email Opportunities Raw"][1][0]="OTHER_OPP"
        data["SFDC Import Opportunities"][1][0]="OTHER_OPP"
        result=m.analyze(data,now=NOW)
        self.assertEqual(result["four_weeks"][-1]["owner_opp_missing_in_both_reports"],1)
        self.assertIn("Owner IDs absent from both fresh and older",m.markdown(result))

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
