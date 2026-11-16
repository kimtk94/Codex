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
                    kw.get("manifest",MANIFEST),kw.get("mail",MAIL),now=NOW,
                    approval_rows=kw.get("approval_rows"),
                    invoice_match_rows=kw.get("invoice_match_rows"),
                    owner_invoice_rows=kw.get("owner_invoice_rows"))


class ProjectManagerTests(unittest.TestCase):
    def test_active_vs_payment_and_no_false_paid(self):
        r=run()
        self.assertEqual(r["status"],"PASS_MIRROR_ONLY")
        self.assertEqual(r["counts"]["active"],1)
        self.assertEqual(r["counts"]["payment"],1)
        self.assertEqual(r["counts"]["archive"],0)
        self.assertEqual(r["counts"]["sif_source_linked"],1)
        self.assertEqual(r["counts"]["sif_prepayment_exception"],1)
        self.assertEqual(r["counts"]["po_report_statement_inferred"],1)
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

    def test_legacy_final_report_does_not_override_current_sequencing(self):
        project=SRC[1].copy()
        project[6]="Final Report & Statement Ready"
        result=run(lifecycle=[SRC[0],project])["project_rows"][0]
        self.assertEqual(result["bucket"],"ACTIVE")
        self.assertTrue(result["legacy_completion_conflict"])
        self.assertIn("LEGACY_COMPLETION_CONFLICT",result["review_reasons"])
        self.assertIn("충돌",result["next_action"])
        self.assertEqual(result["po_state"],"Report/Statement 근거로 제출 간주")

    def test_finance_handoff_uses_current_feishu_only(self):
        project=SRC[1].copy()
        project[5]="Waiting for Settlement"
        result=run(lifecycle=[SRC[0],project])["project_rows"][0]
        self.assertEqual(result["bucket"],"PAYMENT")
        self.assertEqual(result["completion_source"],"FEISHU_STAGE_MIRROR")
        self.assertFalse(result["legacy_completion_conflict"])
        project[5]="Waiting PO/payment"
        self.assertEqual(run(lifecycle=[SRC[0],project])["project_rows"][0]["bucket"],"ACTIVE")

    def test_unverified_approval_is_candidate_only(self):
        approvals=[["AMEA Quotation ID","Quotation Name","Approved AND Active",
                    "Link Verification"],
                   ["AMEA2026022222","Example quote AMEA2026022222","UNVERIFIED",
                    "LINK_NOT_AUTHENTICATED"]]
        result=run(approval_rows=approvals)["project_rows"][1]
        self.assertEqual(result["quote_name"],"")
        self.assertEqual(result["quote_candidate_name"],"Example quote AMEA2026022222")
        self.assertEqual(result["quote_candidate_state"],"UNVERIFIED_APPROVAL_DEDUP")
        self.assertEqual(result["quote_match_state"],"QUOTE_UNLINKED")
        self.assertIn("QUOTE_CANDIDATE_UNVERIFIED",result["review_reasons"])

    def test_approval_candidate_never_replaces_verified_quote(self):
        approvals=[["AMEA Quotation ID","Quotation Name","Approved AND Active",
                    "Link Verification"],
                   ["AMEA2026011111","Different candidate","UNVERIFIED",
                    "LINK_NOT_AUTHENTICATED"]]
        result=run(approval_rows=approvals)["project_rows"][0]
        self.assertEqual(result["quote_name"],"Korea-A-mRNA-AMEA2026011111")
        self.assertEqual(result["quote_candidate_name"],"")
        self.assertEqual(result["quote_match_state"],"APPROVED_AMEA_MIRROR")

    def test_legacy_100_percent_does_not_show_current_completed(self):
        project=SRC[1].copy()
        project[7]="100"
        result=run(lifecycle=[SRC[0],project])["project_rows"][0]
        self.assertEqual(result["progress_percent"],100)
        self.assertTrue(result["progress_conflict"])
        self.assertIsNone(result["progress_display_percent"])
        self.assertEqual(result["bucket"],"ACTIVE")
        self.assertIn("CSS_PROGRESS_100_STAGE_MISMATCH",result["review_reasons"])
        self.assertEqual(run()["counts"]["legacy_progress_100_conflicts"],0)

    def test_stage_group_uses_feishu_operations_vocabulary(self):
        self.assertEqual(stage_group("Waiting for Settlement"),"정산/완료")
        self.assertEqual(stage_group("Waiting PO/payment"),"계약/SIF")
        self.assertEqual(stage_group("Add-seq"),"시퀀싱")
        self.assertEqual(stage_group("Lib prep"),"라이브러리")
        self.assertEqual(stage_group("Resending Sample"),"샘플/QC")
        self.assertEqual(stage_group("BI Analysis"),"데이터/리포트")
        self.assertEqual(stage_group("NOT_IN_FEISHU_SOURCE"),"공정 미확인")

    def test_exact_x_invoice_evidence_never_certifies_paid(self):
        header=["Feishu X ID","Link Status","Verified Paid KRW"]
        invoice_rows=[header,
            ["X209SC26011111","EXACT_X_FEISHU_PROJECT","UNKNOWN"],
            ["X209SC26011111","INVOICE_SUBJECT_X_H_ONLY","UNKNOWN"]]
        result=run(invoice_match_rows=invoice_rows)["project_rows"][0]
        self.assertEqual(result["invoice_notice_count"],2)
        self.assertEqual(result["invoice_exact_x_count"],1)
        self.assertEqual(result["invoice_evidence_state"],"EXACT_X_INVOICE_MIRROR")
        self.assertEqual(result["receipt_state"],"결제 증빙 미확인")
        self.assertFalse(run(invoice_match_rows=invoice_rows)["payment_receipt_verified"])

    def test_amea_owner_invoice_is_review_not_quote_or_paid(self):
        owner=[["AMEA Project","Owner Decision","Paid Decision"],
               ["AMEA2026022222","NOT_VERIFIED","NOT_VERIFIED"]]
        result=run(owner_invoice_rows=owner)["project_rows"][1]
        self.assertEqual(result["quote_name"],"")
        self.assertEqual(result["owner_invoice_record_count"],1)
        self.assertEqual(result["invoice_evidence_state"],"AMEA_OWNER_INVOICE_REVIEW")
        self.assertIn("INVOICE_WITHOUT_VERIFIED_QUOTE",result["review_reasons"])
        self.assertEqual(result["receipt_state"],"결제 증빙 미확인")

    def test_colliding_x_base_does_not_share_invoice_across_subprojects(self):
        header=["Feishu X ID","Link Status","Verified Paid KRW"]
        inv=[header,["X209SC26011111","EXACT_X_FEISHU_PROJECT","UNKNOWN"]]
        clone=SRC[1].copy()
        clone[0]="X209SC26011111-Z02"
        clone[1]="AMEA2026011112"
        r=run(lifecycle=SRC+[clone],invoice_match_rows=inv)["project_rows"]
        self.assertEqual(r[0]["invoice_notice_count"],0)
        self.assertEqual(r[2]["invoice_notice_count"],0)

    def test_stage_progress_and_sif_evidence(self):
        self.assertEqual(stage_group("Library QC"),"라이브러리")
        sifs=SIF+[["AMEA2026022222","FALSE","SIF Approved",
                   "2026-11-11 00:00:00","2026-11-16 12:00:00 KST","B","Two"]]
        self.assertEqual(run(sifs=sifs)["project_rows"][1]["sif_state"],"제출 확인")


if __name__ == "__main__":
    unittest.main()
