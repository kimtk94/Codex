"""Synthetic-only 2026 QQ approval source audit; never prints private Quote details."""
import unittest
from quote_2026_historical_coverage import aggregate_2026_approval_eligibility

def approval(qid,created="2026-01-05"):
    return {
      "approved_at_kst":"2026-01-06 12:00:00",
      "quotation_created_date":created,
      "quotation_name":qid,
      "quotation_id":"AMEA2026010501",
      "salesforce_record_id":"a0P000000000AAA"
    }
def row(qid,product="QD-100001",active="1",date="01/05/2026",pid="Process-2020-04-29-00039"):
    return {
      "SFDC Quotation ID":qid,"Quotation Product ID":product,"Active":active,
      "Created Date":date,"Process Name: SFDC Process ID":pid,
      "Quote Process Name":"Library preparation"
    }

class HistoricalAuditTests(unittest.TestCase):
    def test_synthetic_single_multi_inactive_date_mismatch_and_duplicate(self):
        q1="QID-2026-01-05-100001"
        q2="QID-2026-01-05-100002"
        q3="QID-2026-01-05-100003"
        q4="QID-2026-01-05-100004"
        approvals=[approval(q) for q in (q1,q2,q3,q4)]
        approvals.append(approval(q1))
        data=[row(q1),row(q2,"QD-100001"),row(q2,"QD-100002"),
              row(q3,active="0"),row(q4,date="01/06/2026")]
        result=aggregate_2026_approval_eligibility(approvals,data)
        self.assertEqual(result["approval_rows_2026"],5)
        self.assertEqual(result["distinct_qids"],4)
        self.assertEqual(result["eligibility_counts"],{
            "SINGLE_PRODUCT_ELIGIBLE":1,
            "MULTI_PRODUCT":1,
            "INACTIVE":1,
            "CREATED_DATE_MISMATCH":1,
            "DUPLICATE_APPROVAL":1
        })
        self.assertIs(result["native_krw_process_price_available_in_qq"],False)
        self.assertIs(result["price_auto_apply"],False)
        self.assertEqual(result["crm_writes"],0)
        self.assertNotIn(q1,str(result))

    def test_process_id_conflict_and_missing_report_never_promote(self):
        q1="QID-2026-02-03-100001"
        q2="QID-2026-02-03-100002"
        approvals=[approval(q1,"2026-02-03"),approval(q2,"2026-02-03")]
        records=[
          row(q1,date="02/03/2026",pid="Process-2020-04-29-00031"),
          row(q1,date="02/03/2026",pid="Process-2020-04-29-00039")
        ]
        result=aggregate_2026_approval_eligibility(approvals,records)
        self.assertEqual(result["eligibility_counts"],{
            "PROCESS_ID_CONFLICT":1,"NO_MATCHING_QQ_LINES":1})
        self.assertEqual(result["monthly_approval_counts"],{"2026-02":2})

    def test_wrong_date_and_non_2026_are_not_promoted(self):
        q="QID-2026-04-01-100001"
        records=[approval(q,"2026-04-01"),approval("QID-2025-04-01-100002","2025-04-01")]
        quote=[row(q,date="04/02/2026")]
        result=aggregate_2026_approval_eligibility(records,quote)
        self.assertEqual(result["approval_rows_2026"],1)
        self.assertEqual(result["eligibility_counts"]["CREATED_DATE_MISMATCH"],1)

    def test_malformed_rows_and_empty_source_do_not_claim_pass(self):
        with self.assertRaisesRegex(ValueError,"APPROVAL_COVERAGE_INCOMPLETE"):
            aggregate_2026_approval_eligibility([],[])
        with self.assertRaisesRegex(ValueError,"APPROVAL_ROW_NOT_DICTIONARY"):
            aggregate_2026_approval_eligibility([None],[])
        with self.assertRaisesRegex(ValueError,"QQ_ROW_NOT_DICTIONARY"):
            aggregate_2026_approval_eligibility([],["bad"])

if __name__=="__main__":
    unittest.main()
