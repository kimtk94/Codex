"""Generated Watch must not expose row-position legacy contract values as approved."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo
from css_amea_contract_candidate_crosswalk import HEAD as CROSSWALK_HEAD
from css_unissued_safe_watch import project, HEAD

NOW=dt.datetime(2026,10,31,23,10,tzinfo=ZoneInfo("Asia/Seoul"))
WHEAD=["AMEA Project ID","Project / Institution / Service","Forecast Month",
"Estimated Completion","Quote KRW","Quote K USD","Matched Invoice Count",
"Forecast Status","TAT Basis","Source","Review Status"]
A="AMEA2026090309"
B="AMEA2026091134"
def w(a,quote="9640005"):
    return [a,"Korea-ChangWon Univ.-"+a,"2026-11","2026-11-07",
            quote,"6.8","0","OVERDUE_ESTIMATE_NOT_VERIFIED",
            "TAT_PROJECTION","QUOTE_FORECAST","ISSUANCE_NOT_VERIFIED"]
def x(a,state="FINANCE_AMEA_CANDIDATE",quote="9640005"):
    row=[""]*20
    row[0]=a
    row[1]="Korea-ChangWon Univ.-"+a
    row[2]=quote
    row[3]="X209SC26065705-Z01" # unrelated legacy unsafe identifier
    if state=="FINANCE_AMEA_CANDIDATE":
        row[7]="X209SC26107211"
    row[8]=state
    row[14]="2026-10-31"
    row[15]="2026-10-26"
    row[16]=("CANDIDATE_ONLY_REQUIRES_ORIGINAL_CONTRACT_REVIEW"
             if state in {"FINANCE_AMEA_CANDIDATE","ONLINE_AMEA_CANDIDATE","ONLINE_FINANCE_SAME_X_CANDIDATE"} else "QUARANTINE_NO_CONTRACT_ATTRIBUTION")
    row[18]="2026-10-31 22:50:02 KST"
    return row

class SafeWatchTests(unittest.TestCase):
    def test_quote_forecast_preserved_but_no_approved_contract(self):
        rows,summary=project([WHEAD,w(A)],[CROSSWALK_HEAD,x(A)],NOW)
        self.assertEqual(len(rows[0]),len(HEAD))
        self.assertEqual(rows[0][2],"2026-11")
        self.assertEqual(rows[0][4],"9640005")
        self.assertEqual(rows[0][11:14],["","",""])
        self.assertEqual(rows[0][14:17],["","",""])
        self.assertEqual(rows[0][17],"X209SC26107211")
        self.assertNotIn("X209SC26065705",str(rows[0]))
        self.assertEqual(rows[0][18],"FINANCE_AMEA_CANDIDATE")
        self.assertEqual(rows[0][20],"ISSUANCE_NOT_VERIFIED;PAYMENT_NOT_VERIFIED")
        self.assertEqual(summary["approved_contracts"],0)
        self.assertEqual(summary["source_writes"],0)
    def test_missing_candidate_is_quarantined_without_loss_of_quote(self):
        rows,s=project([WHEAD,w(A)],
            [CROSSWALK_HEAD,x(A,"NO_AMEA_SOURCE_CANDIDATE")],NOW)
        self.assertEqual(rows[0][14:18],["","","",""])
        self.assertEqual(rows[0][19],"QUARANTINE_NO_CONTRACT_ATTRIBUTION")
        self.assertEqual(s["quarantined"],1)
    def test_watch_drift_or_missing_amea_fails(self):
        with self.assertRaisesRegex(ValueError,"WATCH_CROSSWALK_SET_MISMATCH"):
            project([WHEAD,w(A)],[CROSSWALK_HEAD,x(A),x(B)],NOW)
        with self.assertRaisesRegex(ValueError,"CROSSWALK_MISSING_AMEA"):
            project([WHEAD,w(A),w(B)],[CROSSWALK_HEAD,x(A)],NOW)
    def test_foreign_quote_mapping_never_inherits_another_customers_invoice(self):
        with self.assertRaisesRegex(ValueError,"PROJECT_OR_QUOTE_MISMATCH"):
            project([WHEAD,w(A)],[CROSSWALK_HEAD,x(A,quote="11100000")],NOW)
        with self.assertRaisesRegex(ValueError,"PROJECT_OR_QUOTE_MISMATCH"):
            changed=x(A)
            changed[1]="Korea-Yonsei Univ."
            project([WHEAD,w(A)],[CROSSWALK_HEAD,changed],NOW)
    def test_stale_crosswalk_or_forged_approval_is_refused(self):
        row=x(A)
        row[18]="2026-10-28 10:00:00 KST"
        with self.assertRaisesRegex(ValueError,"CROSSWALK_STALE_OR_FUTURE"):
            project([WHEAD,w(A)],[CROSSWALK_HEAD,row],NOW)
        row=x(A)
        row[16]="CONTRACT_APPROVED"
        with self.assertRaisesRegex(ValueError,"CONTRACT_GATE_CONTRADICTION"):
            project([WHEAD,w(A)],[CROSSWALK_HEAD,row],NOW)
    def test_conflict_never_leaks_bad_candidate(self):
        row=x(A,"ONLINE_FINANCE_X_CONFLICT")
        row[4]="H209SC26107211"
        row[5]="X209SC26107211-Z01"
        rows,_=project([WHEAD,w(A)],[CROSSWALK_HEAD,row],NOW)
        self.assertEqual(rows[0][11:18],[""]*7)
        self.assertEqual(rows[0][19],"QUARANTINE_NO_CONTRACT_ATTRIBUTION")
    def test_duplicate_crosswalk_amea_fails(self):
        with self.assertRaisesRegex(ValueError,"CROSSWALK_AMEA_DUPLICATE_OR_INVALID"):
            project([WHEAD,w(A)],[CROSSWALK_HEAD,x(A),x(A)],NOW)
if __name__=="__main__":
    unittest.main()
