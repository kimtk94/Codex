import unittest
from qq_statement_extract_p046 import extract, parse_rows

SUBJECT = "Final Report & Statement Ready For Confirmation - J001-X209SC26082826-Z01 - H209SC26082826 - AMEA2026073102"
BODY = "Subtotal Amount | 1320000.00 | KRW\nTotal Amount | 1320000.00 | KRW"

class StatementTests(unittest.TestCase):
    def row(self, uid="34725", body=BODY):
        return {"Mail UID":uid,"Subject":SUBJECT,"Body":body}

    def test_verified_shape_stays_unverified(self):
        x=extract(self.row())
        self.assertEqual(x["state"],"PARSED_UNVERIFIED")
        self.assertEqual(x["amount"],"1320000.00")
        self.assertEqual(x["currency"],"KRW")
        self.assertEqual(x["amea"],["AMEA2026073102"])

    def test_missing_body_is_quarantined(self):
        self.assertEqual(extract(self.row(body=""))["reason"],"BODY_NOT_AVAILABLE")

    def test_conflicting_totals_are_quarantined(self):
        body="Subtotal Amount | 1300000 | KRW\nTotal Amount | 1320000 | KRW"
        self.assertEqual(extract(self.row(body=body))["reason"],"CONFLICTING_TOTALS")

    def test_uid_recollection_is_idempotent(self):
        self.assertEqual(len(parse_rows([self.row(),self.row()])),1)

    def test_uid_collision_is_quarantined(self):
        x=parse_rows([self.row(),self.row(body="Total Amount | 999 | KRW")])
        self.assertEqual(x[0]["reason"],"DUPLICATE_UID_CONFLICT")

if __name__=="__main__":
    unittest.main()
