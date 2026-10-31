"""Offline regression for cross-customer Unissued Invoice Watch X/H lineage."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo
from css_unissued_contract_lineage_guard import verify,normalized_x

NOW=dt.datetime(2026,10,31,17,35,tzinfo=ZoneInfo("Asia/Seoul"))
WATCH_HEAD=["AMEA Project ID","Project / Institution / Service","Forecast Month",
  "Estimated Completion","Quote KRW","Quote K USD","Matched Invoice Count",
  "Forecast Status","TAT Basis","Source","Review Status","",
  "H Contract","X Sub-project","Stage"]
OUT_HEAD=["Customer Name","ERP Invoice Number","Contact Person","Invoice Type","PO Number",
 "Project Number","CMS Invoice Number","Quotation Number","e-tax Number","Sales","Invoice Date",
 "Due Date","Invoice Amount","Balance"]
ETAX_HEAD=[""]*35
for i,n in ((9,"Project Number"),(10,"Quotation Number"),(15,"Amount")):ETAX_HEAD[i]=n
MANIFEST=[["Source","Source Date","Synced At KST","Source ID","Rows","Schema","Meaning"],
 ["Payment Outstanding","2026-10-26","2026-10-31 17:00 KST","a1","3","HEADER_MATCHED",""],
 ["eTax Invoice","2026-10-26","2026-10-31 17:00 KST","b2","1","HEADER_MATCHED",""]]

def make_watch(amea,x):
    return [amea,"Korea synthetic-"+amea,"2026-10","2026-10-08","9640005",
            "6.42","0","OVERDUE_ESTIMATE_NOT_VERIFIED","PROXY",
            "QUOTE_FORECAST","ISSUANCE_NOT_VERIFIED","",
            "H209SC26065705",x,"X209SC26065705-Z01-F001"]
def make_out(x,amea):
    r=[""]*14;r[5]=x;r[7]=amea;r[12]="1100";r[13]="1100";return r
def make_tax(x,amea):
    r=[""]*35;r[9]=x;r[10]=amea;r[15]="1100";return r
def fixture():
    watch=[WATCH_HEAD,
        make_watch("AMEA2026090309","X209SC26065705-Z01"),
        make_watch("AMEA2026091134","X209SC26020509-Z01"),
        make_watch("AMEA2026091438","X209SC26096286-Z01"),
        make_watch("AMEA2026091510",""),
        make_watch("AMEA2026091519","X209SC99999999-Z01"),
        make_watch("AMEA2026091520","X209SC26010203-Z01")]
    outstanding=[OUT_HEAD,
        make_out("X209SC26065705","AMEA2026042239"),
        make_out("X209SC26020509","AMEA2026012823"),
        make_out("X209SC26010203","AMEA2026091520")]
    etax=[ETAX_HEAD,make_tax("X209SC26096286","AMEA2026091720")]
    return watch,outstanding,etax,[x[:] for x in MANIFEST]

class ContractLineageTests(unittest.TestCase):
    def test_cross_project_refs_are_quarantined_not_paid(self):
        rows,summary=verify(*fixture(),NOW)
        by={row[0]:row for row in rows}
        self.assertEqual(summary["watch_projects"],6)
        self.assertEqual(summary["foreign_amea_links"],3)
        self.assertEqual(summary["source_age_days"],5)
        for k in ("AMEA2026090309","AMEA2026091134","AMEA2026091438"):
            self.assertEqual(by[k][10],"X_REFERENCES_DIFFERENT_AMEA")
            self.assertEqual(by[k][11],"QUARANTINE_CONTRACT_ATTRIBUTION")
        self.assertEqual(by["AMEA2026091510"][10],"MISSING_WATCH_X")
        self.assertEqual(by["AMEA2026091519"][10],"X_NOT_IN_FEISHU_SNAPSHOT")
        self.assertEqual(by["AMEA2026091520"][10],"X_MATCHED_SAME_AMEA_ON_STALE_SNAPSHOT")
        self.assertEqual(summary["business_source_writes"],0)
        self.assertEqual(summary["issuance_or_payment_certified"],0)

    def test_same_x_with_foreign_and_self_is_ambiguous(self):
        w,o,e,m=fixture()
        o.append(make_out("X209SC26065705","AMEA2026090309"))
        m[1][4]="4"
        rows,_=verify(w,o,e,m,NOW)
        self.assertEqual(rows[0][10],"X_AMBIGUOUS_MULTIPLE_AMEAS")

    def test_manifest_row_count_drift_blocks(self):
        w,o,e,m=fixture();m[1][4]="42"
        with self.assertRaisesRegex(ValueError,"OUTSTANDING_MIRROR_ROW_DRIFT"):
            verify(w,o,e,m,NOW)
        w,o,e,m=fixture();m[2][4]="7"
        with self.assertRaisesRegex(ValueError,"ETAX_MIRROR_ROW_DRIFT"):
            verify(w,o,e,m,NOW)

    def test_protected_watch_decision_cannot_be_assumed(self):
        w,o,e,m=fixture();w[1][10]="ISSUED"
        with self.assertRaisesRegex(ValueError,"WATCH_APPROVAL_WAS_CHANGED"):
            verify(w,o,e,m,NOW)

    def test_unverified_feishu_amea_is_not_negative_evidence(self):
        w,o,e,m=fixture();o[1][7]=""
        rows,_=verify(w,o,e,m,NOW)
        self.assertEqual(rows[0][10],"X_PRESENT_BUT_AMEA_NOT_VERIFIED")

    def test_normalize_only_stage_suffix(self):
        self.assertEqual(normalized_x("X209SC26065705-Z01"),"X209SC26065705")
        self.assertEqual(normalized_x("X209SC26065705-Z01-F001"),"X209SC26065705")
        self.assertEqual(normalized_x("garbage"),"")

    def test_foreign_id_format_is_fail_closed(self):
        w,o,e,m=fixture();o[1][5]="bad"
        with self.assertRaisesRegex(ValueError,"FEISHU_X_FORMAT_INVALID"):
            verify(w,o,e,m,NOW)

if __name__=="__main__":
    unittest.main()
