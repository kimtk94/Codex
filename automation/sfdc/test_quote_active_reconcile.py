import unittest
from automation.sfdc.quote_active_reconcile import reconcile

class QuoteReconcileTest(unittest.TestCase):
    def test_approved_active_verified(self):
        approvals=[{"quotation_id":"AMEA1","salesforce_record_id":"Q1","approval_evidence":"APPROVED_TEXT"}]
        quotes=[{"Id":"Q1","IsActive":"true","CurrencyIsoCode":"KRW","GrandTotal":"1000"}]
        result=reconcile(approvals,quotes)[0]
        self.assertEqual(result["validation_status"],"APPROVED_ACTIVE_VERIFIED")
        self.assertEqual(result["eligible_amount"],"1000")

    def test_unknown_is_not_valid(self):
        approvals=[{"quotation_id":"AMEA1","salesforce_record_id":"Q1","approval_evidence":"APPROVED_TEXT"}]
        quotes=[{"Id":"Q1","CurrencyIsoCode":"KRW","GrandTotal":"1000"}]
        result=reconcile(approvals,quotes)[0]
        self.assertEqual(result["validation_status"],"ACTIVE_UNKNOWN")
        self.assertEqual(result["eligible_amount"],"")

    def test_duplicate_id_is_blocked(self):
        approvals=[{"salesforce_record_id":"Q1","approval_evidence":"APPROVED_TEXT"}]
        quotes=[{"Id":"Q1","IsActive":"true","GrandTotal":"5","CurrencyIsoCode":"KRW"}]*2
        self.assertEqual(reconcile(approvals,quotes)[0]["validation_status"],"AMBIGUOUS_OR_MISSING_QUOTE_ID")

if __name__=="__main__":
    unittest.main()
