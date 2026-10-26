import unittest
from css_statement_ledger_plan import plan_statement_updates, load_mail_rows

class LedgerPlanTests(unittest.TestCase):
    def setUp(self):
        self.mail = {"Mail UID":"inbox:34725",
          "Subject":"Final Report & Statement Ready For Confirmation – X209SC26082826-Z01 H209SC26082826 AMEA2026073102",
          "Body Text":"PO SQ-AMEA2026073102\n6.00 220000.00 1320000.00 KRW\nTotal Amount 1320000.00 KRW"}

    def test_plan_no_revenue_and_no_sam_guess(self):
        p=plan_statement_updates([self.mail], [])
        self.assertEqual(len(p["proposed"]),1)
        v=p["proposed"][0]
        self.assertEqual(v["Statement Amount KRW"],"1320000.00")
        self.assertEqual(v["SAM Batch"],"")
        self.assertEqual(v["Invoice Number"],"")
        self.assertEqual(v["Revenue Treatment"],"NO_REVENUE_ADDITION")
        self.assertEqual(p["operational_writes"],0)

    def test_existing_source_uid_preserved(self):
        p=plan_statement_updates([self.mail],[{"Evidence Source":"CSS Timeline; MAIL_UID=inbox:34725"}])
        self.assertEqual(p["proposed"],[])

    def test_missing_body_header_rejected(self):
        with self.assertRaises(ValueError):
            load_mail_rows([["Mail UID","Subject"],["inbox:1","test"]])

    def test_no_inferred_amount(self):
        m=dict(self.mail)
        m["Body Text"]="PO SQ-AMEA2026073102\n6 220000 999999 KRW\nTotal Amount 999999 KRW"
        result=plan_statement_updates([m],[])
        self.assertEqual(len(result["deferred"]),1)

if __name__=="__main__":
    unittest.main()
