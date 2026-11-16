import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from css_project_manager_local import assemble, create_project, stage_group
from css_projects_local import KST

NOW = dt.datetime(2026,11,16,16,0,tzinfo=KST)
SRC = [
 ["Project / Sub-project","AMEA","Institution","Customer","Service","Feishu Status (latest)",
  "CSS Stage (legacy)","CSS Progress %","Sample Count","Feishu Expected Completion","Invoice Count"],
 ["X209SC26011111-Z01","AMEA2026011111","A University","One","mRNA-Seq",
  "Sequencing","SIF Approved","50","12","2026-11-25","0"],
 ["X209SC26022222-Z01","AMEA2026022222","B University","Two","WGS",
  "Completed","Final Report & Statement Ready","100","3","2026-11-10","1"],
]
QUOTES=[
 ["Approved AMEA ID","Quote Name","Active","Approval Match","Source Timestamp"],
 ["AMEA2026011111","Korea-A-mRNA-AMEA2026011111","ACTIVE","APPROVED","2026-11-16 12:00:00 KST"],
]
SIF=[
 ["AMEA No.","Prepayment","Status","sif_first_seen_at","updated_at","Institution","Customer Name"],
 ["AMEA2026011111","TRUE","SIF requested","","2026-11-16 12:00:00 KST","A University","One"],
]
PAY=[
 ["Project ID","Payment outstanding","Last verified KST"],
 ["X209SC26022222-Z01","YES","2026-11-16 15:00:00 KST"],
]
MANIFEST=[
 ["Source","Synced At KST"],
 ["Online-Project","2026-11-16T15:00:00+09:00"],
]
MAIL=[["Updated At KST","State"],["2026-11-16 15:15:00 KST","WINDOW_CAUGHT_UP"]]


def run(**kw):
    return assemble(kw.get("lifecycle",SRC),kw.get("quotes",QUOTES),
                    kw.get("sifs",SIF),kw.get("pays",PAY),
                    kw.get("manifest",MANIFEST),kw.get("mail",MAIL),now=NOW)


class ProjectManagerTests(unittest.TestCase):
    def test_active_vs_payment_and_no_false_paid(self):
        r=run()
        self.assertEqual(r["status"],"PASS_MIRROR_ONLY")
        self.assertEqual(r["counts"]["active"],1)
        self.assertEqual(r["counts"]["payment"],1)
        self.assertEqual(r["counts"]["archive"],0)
        a,b=r["project_rows"]
        self.assertEqual(a["quote_name"],"Korea-A-mRNA-AMEA2026011111")
        self.assertEqual(a["quote_match_state"],"APPROVED_AMEA_MIRROR")
        self.assertEqual(a["sif_state"],"Prepayment 예외")
        self.assertIn("SIF 반복 요청 제외",a["next_action"])
        self.assertEqual(b["quote_name"],"")
        self.assertEqual(b["po_state"],"Report/Statement 근거로 제출 간주")
        self.assertEqual(b["bucket"],"PAYMENT")
        self.assertIn("미수금",b["next_action"])
        self.assertEqual(b["receipt_state"],"결제 증빙 미확인")
        self.assertFalse(r["payment_receipt_verified"])
        self.assertFalse(r["original_feishu_verified"])

    def test_multiple_quote_names_not_guessed(self):
        extra=["AMEA2026011111","Another approved Quote","ACTIVE","APPROVED","2026-11-16 12:00:00 KST"]
        result=run(quotes=QUOTES+[extra])["project_rows"][0]
        self.assertEqual(result["quote_name"],"")
        self.assertEqual(result["quote_match_state"],"MULTIPLE_QUOTE_REVIEW")
        self.assertTrue(result["needs_review"])

    def test_invoice_not_proof_of_payment(self):
        with_none=run(pays=[PAY[0]])["project_rows"][1]
        self.assertEqual(with_none["bucket"],"PAYMENT")
        self.assertEqual(with_none["receipt_state"],"결제 증빙 미확인")

    def test_source_mirror_partial_and_stale(self):
        partial=run(mail=[MAIL[0],["2026-11-16 15:15:00 KST","WINDOW_PARTIAL"]])
        self.assertEqual(partial["status"],"PARTIAL_MIRROR")
        stale=run(manifest=[MANIFEST[0],["Online-Project","2026-10-10T15:00:00+09:00"]])
        self.assertEqual(stale["status"],"STALE")

    def test_duplicate_project_and_wrong_schema_blocked(self):
        with self.assertRaisesRegex(ValueError,"PROJECT_COUNT_OR_DUPLICATES"):
            run(lifecycle=SRC+[SRC[1]])
        with self.assertRaisesRegex(ValueError,"SCHEMA_QUOTE"):
            run(quotes=[["wrong"]])

    def test_stage_progress_and_sif_evidence(self):
        self.assertEqual(stage_group("Library QC"),"라이브러리")
        sifs=SIF+[["AMEA2026022222","FALSE","SIF Approved",
                   "2026-11-11 00:00:00","2026-11-16 12:00:00 KST","B","Two"]]
        self.assertEqual(run(sifs=sifs)["project_rows"][1]["sif_state"],"제출 확인")


if __name__ == "__main__":
    unittest.main()
