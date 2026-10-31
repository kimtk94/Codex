"""Offline regression for manual eTax / quote matching; no real sales data."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo
from css_manual_etax_quote_review import audit,net

NOW=dt.datetime(2026,10,31,17,30,tzinfo=ZoneInfo("Asia/Seoul"))

def fixtures():
    header=["Other"]*35
    for col,label in {2:"Source",3:"Type",4:"ERP Invoice Number",5:"CMS Invoice Num",
                      9:"Project Number",10:"Quotation Number",15:"Amount",25:"Sales"}.items():header[col]=label
    def dated(erp,amount,sales="Kim Taehoon"):
        arr=[""]*35
        for i,x in {2:"Manual Invoice",3:"Projects Invoice",4:erp,5:"",
                    9:"X209SC26107211",10:"AMEA2026090309",15:str(amount),25:sales}.items():arr[i]=x
        return arr
    d=[header,dated("20910000208",1287000),dated("20910000209",9317000),
       dated("20910000198",4400,sales="Other Sales")]
    p=[["Source Key Type","Feishu Invoice Key","CMS Invoice No","Feishu Gross KRW","Personal QQ Gross KRW",
        "Personal QQ Evidence","Source Sales Label (not owner)","Dated Snapshot","Source Age Days",
        "Finance Decision"],
        ["ERP","20910000208","","1287000","","MANUAL_INVOICE_NO_CMS_QQ_UNPROVEN",
         "Kim Taehoon","2026-10-26","5","NOT_VERIFIED"],
        ["ERP","20910000209","","9317000","","MANUAL_INVOICE_NO_CMS_QQ_UNPROVEN",
         "Kim Taehoon","2026-10-26","5","NOT_VERIFIED"],
        ["ERP","20910000198","","4400","","MANUAL_INVOICE_NO_CMS_QQ_UNPROVEN",
         "Other Sales","2026-10-26","5","NOT_VERIFIED"]]
    watch=[["AMEA Project ID","Project / Institution / Service","Forecast Month","Estimated Completion",
           "Quote KRW","Quote K USD","Matched Invoice Count","Forecast Status","TAT Basis",
           "Source","Review Status","","H Contract","X Sub-project"],
           ["AMEA2026090309","Korea-ChangWon Univ", "2026-10","2026-10-08",
            "9640005","6.42667","0","OVERDUE_ESTIMATE_NOT_VERIFIED",
            "AMEA_DATE_PLUS_35D_PROXY","QUOTE_FORECAST","ISSUANCE_NOT_VERIFIED",
            "","H209SC26065705","X209SC26065705-Z01"]]
    manifest=[["Source","Source Date","Synced At KST","Source ID","Rows","Schema","Meaning"],
              ["eTax Invoice","2026-10-26","2026-10-31T15:55:00+09:00","test","3","HEADER_MATCHED",""]]
    return d,p,watch,manifest

class ManualQuoteTests(unittest.TestCase):
    def test_exact_split_candidate_with_five_won_quote_delta_not_issued(self):
        rows,summary=audit(*fixtures(),NOW)
        self.assertEqual(len(rows),2)
        self.assertEqual(summary["gross_sum"],10604000)
        self.assertEqual(summary["quote_amount_candidate_projects"],0)
        self.assertEqual(summary["contract_mismatch_projects"],1)
        self.assertEqual(summary["issued_certifications"],0)
        self.assertEqual(summary["payment_approvals"],0)
        self.assertEqual(summary["revenue_changes"],0)
        self.assertEqual([r[6] for r in rows],[-5,-5])
        self.assertTrue(all(r[8]=="PROJECT_CONTRACT_MISMATCH_REVIEW" for r in rows))
        self.assertTrue(all(r[12]=="NOT_VERIFIED" for r in rows))
        self.assertEqual(net(10604000),9640000)
    def test_matching_contract_is_only_amount_candidate_not_issuance(self):
        d,p,w,m=fixtures()
        w[1][13]="X209SC26107211-Z01"
        rows,stats=audit(d,p,w,m,NOW)
        self.assertEqual(stats["quote_amount_candidate_projects"],1)
        self.assertEqual(stats["contract_mismatch_projects"],0)
        self.assertTrue(all(r[8]=="NET_QUOTE_AMOUNT_CANDIDATE_NO_ISSUANCE_PROOF" for r in rows))
        self.assertEqual(stats["issued_certifications"],0)

    def test_changed_watch_status_must_not_auto_authorize(self):
        d,p,w,m=fixtures()
        w[1][10]="ISSUED"
        with self.assertRaisesRegex(ValueError,"UNISSUED_WATCH_DECISION_CHANGED"):
            audit(d,p,w,m,NOW)
    def test_amount_mismatch_never_silently_reconciled(self):
        d,p,w,m=fixtures();d[1][15]="1287001"
        with self.assertRaisesRegex(ValueError,"PERSONAL_MANUAL_AMOUNT_CONFLICT"):
            audit(d,p,w,m,NOW)
    def test_partial_group_does_not_match_quote(self):
        d,p,w,m=fixtures();p.pop(2)
        w[1][13]="X209SC26107211-Z01"
        rows,stats=audit(d,p,w,m,NOW)
        self.assertEqual(len(rows),1)
        self.assertEqual(stats["quote_amount_candidate_projects"],0)
        self.assertEqual(rows[0][8],"AMOUNT_OR_SPLIT_MISMATCH_REVIEW")
    def test_stale_mirror_or_manifest_fails(self):
        d,p,w,m=fixtures();m[1][4]="2"
        with self.assertRaisesRegex(ValueError,"ETAX_SOURCE_ROW_COUNT_DRIFT"):
            audit(d,p,w,m,NOW)
        d,p,w,m=fixtures();p[2][7]="2026-10-25"
        with self.assertRaisesRegex(ValueError,"PERSONAL_MANUAL_SNAPSHOT_DRIFT"):
            audit(d,p,w,m,NOW)
    def test_no_personal_qualified_manual_source_is_not_silent_success(self):
        d,p,w,m=fixtures()
        d[1][25]="Not personal sales";d[2][25]="Not personal sales"
        with self.assertRaisesRegex(ValueError,"NO_PERSONAL_MANUAL_CANDIDATES"):
            audit(d,p,w,m,NOW)
if __name__=="__main__":unittest.main()
