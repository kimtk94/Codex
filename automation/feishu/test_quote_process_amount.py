#!/usr/bin/env python3
import datetime as dt
import unittest
from zoneinfo import ZoneInfo
import quote_process_amount as q

QID="QID-2026-11-02-410984"
QID2="QID-2026-10-12-405295"
SF="a0P"+"A"*12
NOW=dt.datetime(2026,11,7,18,12,tzinfo=ZoneInfo("Asia/Seoul"))

def fixture(count=1):
    quotation=[
      {"SFDC Quotation ID":QID,"Quotation Product ID":"QD-1",
       "Opportunity ID":"006OPP","Active":"1",
       "Unit Price USD":"20.00","Sample Quantity":"3.00",
       "Process Name: SFDC Process ID":"PROC-1"},
      {"SFDC Quotation ID":QID,"Quotation Product ID":"QD-1",
       "Opportunity ID":"006OPP","Active":"1",
       "Unit Price USD":"0.00","Sample Quantity":"3.00",
       "Process Name: SFDC Process ID":"PROC-0"},
      {"SFDC Quotation ID":QID,"Quotation Product ID":"QD-1",
       "Opportunity ID":"006OPP","Active":"1",
       "Unit Price USD":"47.00","Sample Quantity":"2.00",
       "Process Name: SFDC Process ID":"PROC-2"}]
    opportunities=[{"Opportunity ID":"006OPP",
                    "Opportunity Owner":"Kim Taehoon","Amount Currency":"KRW"}]
    approvals=[{"Approval KST":"2026-11-04 13:00:00",
                "Quotation Name":QID+" sales approved",
                "SFDC Record ID":SF}]
    return {"SFDC Email Quotation Raw":quotation,
            "SFDC Email Opportunities Raw":opportunities,
            "Quote Approval Dedup":approvals,
            "Quote Portfolio":[{"Quote QID":QID,
                                "Salesforce Quote ID (18)":SF+"XYZ","Quote USD":"154.00"}],
            "SFDC Email Ingest Audit":[], "SFDC Weekly Overview":[
                {"week_start":"2026-10-30","week_end":"2026-11-05",
                 "quotation_approvals":str(count),"krw_per_usd":"1500"}]}

def finalize(src):
    audits=[]
    for entity,tab,key in (("Quotation","SFDC Email Quotation Raw","SFDC Quotation ID"),
                           ("Opportunities","SFDC Email Opportunities Raw","Opportunity ID")):
        rows=src[tab]
        audits.append({"Entity":entity,"Source Received KST":"2026-11-07 12:00:07 KST",
            "Rows":str(len(rows)),"Unique IDs":str(len({r[key] for r in rows})),
            "State":"STAGED_NOT_PROMOTED","Source Kind":"QQ IMAP",
            "Content SHA256":q.exact_source_sha(rows)})
    src["SFDC Email Ingest Audit"]=audits
    return src

class ProcessQuoteTests(unittest.TestCase):
    def test_sum_all_distinct_positive_processes_not_max_product(self):
        data=finalize(fixture())
        sums,stats=q.process_totals(data["SFDC Email Quotation Raw"])
        self.assertEqual(sums[QID]["amount_usd"],q.D("154.00"))
        self.assertEqual(stats["unique_quote_ids"],1)
        self.assertEqual(stats["candidate_quote_ids"],1)
        self.assertEqual(stats["hold_reasons"],{})
        rows,report=q.weekly_calculations(data,NOW)
        self.assertEqual(report["source_state"],"SOURCE_QQ_REPORT_VERIFIED")
        self.assertEqual(rows["2026-10-30"]["calculated_count"],1)
        self.assertEqual(rows["2026-10-30"]["hist_parity_count"],1)
        self.assertEqual(rows["2026-10-30"]["candidate_usd"],q.D("154.00"))

    def test_same_process_id_with_different_price_is_additional_charge(self):
        data=fixture()
        data["SFDC Email Quotation Raw"][2]["Process Name: SFDC Process ID"]="PROC-1"
        data["Quote Portfolio"][0]["Quote USD"]="154.00"
        data=finalize(data)
        results,_=q.weekly_calculations(data,NOW)
        self.assertEqual(results["2026-10-30"]["calculated_count"],1)

    def test_duplicate_exact_priced_process_fails_closed(self):
        data=fixture()
        data["SFDC Email Quotation Raw"].append(dict(data["SFDC Email Quotation Raw"][0]))
        data=finalize(data)
        results,source=q.weekly_calculations(data,NOW)
        self.assertEqual(source["hold_reasons"]["EXACT_DUPLICATE_CHARGE"],1)
        self.assertEqual(results["2026-10-30"]["calculated_count"],0)
        self.assertEqual(results["2026-10-30"]["issues"]["no_safe_priced_quote"],1)

    def test_zero_cost_lines_are_not_zero_value_quote(self):
        data=fixture()
        for row in data["SFDC Email Quotation Raw"]:
            row["Unit Price USD"]="0"
        data=finalize(data)
        results,source=q.weekly_calculations(data,NOW)
        self.assertEqual(source["hold_reasons"]["NO_POSITIVE_PROCESS_PRICE"],1)
        self.assertEqual(results["2026-10-30"]["calculated_count"],0)

    def test_historic_mismatch_blocks_without_arbitrary_fx(self):
        data=fixture()
        data["Quote Portfolio"][0]["Quote USD"]="983.33"
        data=finalize(data)
        results,_=q.weekly_calculations(data,NOW)
        self.assertEqual(results["2026-10-30"]["calculated_count"],0)
        self.assertEqual(results["2026-10-30"]["issues"]["historic_amount_disagrees"],1)

    def test_no_historic_portfolio_yet_calculated_with_provenance(self):
        data=fixture()
        data["Quote Portfolio"]=[]
        data=finalize(data)
        results,_=q.weekly_calculations(data,NOW)
        self.assertEqual(results["2026-10-30"]["calculated_count"],1)
        self.assertEqual(results["2026-10-30"]["without_historic_count"],1)

    def test_two_quotes_one_unverified_opportunity(self):
        data=fixture(count=2)
        more=[dict(r) for r in data["SFDC Email Quotation Raw"]]
        for row in more:
            row["SFDC Quotation ID"]=QID2
        data["SFDC Email Quotation Raw"]+=more
        data["Quote Approval Dedup"].append(
            {"Approval KST":"2026-11-04 15:00:00",
             "Quotation Name":QID2, "SFDC Record ID":"a0P"+"B"*12})
        data["SFDC Email Opportunities Raw"][0]["Opportunity Owner"]="Unknown"
        data=finalize(data)
        results,source=q.weekly_calculations(data,NOW)
        self.assertEqual(source["candidate_quote_ids"],2)
        self.assertEqual(results["2026-10-30"]["calculated_count"],0)
        self.assertEqual(results["2026-10-30"]["issues"]["opportunity_owner_unverified_or_other"],2)

    def test_sha_and_coverage_must_match_original_report(self):
        data=finalize(fixture())
        self.assertEqual(q.validate_source(data,NOW),"SOURCE_QQ_REPORT_VERIFIED")
        data["SFDC Email Quotation Raw"][0]["Unit Price USD"]="9999.00"
        self.assertEqual(q.validate_source(data,NOW),"WITHHELD_3REPORT_SHA_MISMATCH")
        data=finalize(fixture())
        data["SFDC Email Ingest Audit"][0]["Rows"]="4"
        self.assertEqual(q.validate_source(data,NOW),"WITHHELD_3REPORT_COVERAGE_MISMATCH")
        data=finalize(fixture())
        data["SFDC Email Ingest Audit"][0]["Source Received KST"]="2026-10-24 12:00:00 KST"
        self.assertEqual(q.validate_source(data,NOW),"WITHHELD_3REPORT_STALE")

    def test_quote_qid_requires_exact_one(self):
        self.assertIsNone(q.quote_id(QID+" "+QID2))
        self.assertEqual(q.quote_id("Approval "+QID),QID)
        self.assertIsNone(q.sf15("not-a-salesforce-record"))
        self.assertEqual(q.week_for("2026-11-05 12:00:00"),"2026-10-30")
        self.assertEqual(q.week_for("2026-11-07 12:00:00"),"2026-11-06")

if __name__=="__main__":
    unittest.main()
