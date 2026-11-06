#!/usr/bin/env python3
"""Source-backed project-by-project Feishu native web verification."""
import unittest
from project_progress_board import prepare_project_board,percent,bar


PID="AMEA2026100751"
BASE={"Source Key":"PROJECT:"+PID,"AMEA":PID,"Project":"Korea-Yonsei-5-mRNA-AMEA2026100751",
      "Institution":"Yonsei Univ.","Customer":"Park","Service":"mRNASeq","Current Stage":"Sample Received",
      "Progress %":40,"SIF State":"NOT_VERIFIED","Next Action":"Please submit SIF","Evidence":"CSS PROJECT"}
def sources(**more):
    base={"CSS Project Dashboard":[{"project_id":PID,"current_stage":"Sample Received",
        "project_description":"Korea-Yonsei-5-mRNA-AMEA2026100751"}],
      "CSS Contract-SIF Tracker":[], "Quote Portfolio":[],
      "Feishu Latest Prepayments":[], "BI Project Lifecycle Overview":[]}
    return {**base,**more}

class ProjectBoardTests(unittest.TestCase):
    def test_full_exact_sfdc_quote_name_and_progress_bar(self):
        q="Korea-Yonsei-33-16SV4V5-WOBI-Prof.LeeTaeKwon-ParkSoHee-AMEA2026100751"
        r=prepare_project_board(sources(**{"Quote Portfolio":[
            {"Approved AMEA ID":PID,"Quote Name":q,"Active":"ACTIVE","Approval Match":"APPROVED"}
        ]}),[BASE])[0]
        self.assertEqual(r["Quote Full Name"],q)
        self.assertEqual(r["Quote Match State"],"SFDC_EXACT_VERIFIED")
        self.assertEqual(r["Progress Bar"],"████░░░░░░  40%")
        self.assertEqual(r["Progress %"],40)

    def test_prepaid_sif_waiver_still_follows_sample(self):
        sif={"project_id":PID,"Prepayment":"TRUE","Status":"SIF requested"}
        r=prepare_project_board(sources(**{"CSS Contract-SIF Tracker":[sif]}),[BASE])[0]
        self.assertEqual(r["Prepayment"],"YES")
        self.assertEqual(r["SIF State"],"WAIVED_PREPAYMENT")
        self.assertIn("SIF 면제",r["Next Action"])

    def test_submitted_sif_advances_and_tracks_followup(self):
        sif={"project_id":PID,"Prepayment":"TRUE","Status":"SIF received",
             "sif_first_seen_at":"2026-11-06"}
        r=prepare_project_board(sources(**{"CSS Contract-SIF Tracker":[sif]}),[BASE])[0]
        self.assertEqual(r["SIF State"],"SUBMITTED")
        self.assertIn("후속 공정",r["Next Action"])

    def test_invoice_does_not_automatically_complete_production(self):
        row={**BASE,"Current Stage":"Invoice issued","Progress %":100}
        r=prepare_project_board(sources(**{"CSS Project Dashboard":[
            {"project_id":PID,"current_stage":"Invoice issued"}
        ]}),[row])[0]
        self.assertNotIn("Progress %",r)
        self.assertEqual(r["Progress Bar"],"미확인")

    def test_css_fallback_does_not_claim_salesforce_verification(self):
        r=prepare_project_board(sources(),[BASE])[0]
        self.assertEqual(r["Quote Match State"],"CSS_ORIGINAL_UNVERIFIED")
        self.assertTrue(r["Quote Full Name"].startswith("Korea-Yonsei"))

    def test_multiple_valid_quotations_retained_and_flagged(self):
        r=prepare_project_board(sources(**{"Quote Portfolio":[
          {"Approved AMEA ID":PID,"Quote Name":"Q1","Active":"ACTIVE","Approval Match":"APPROVED"},
          {"Approved AMEA ID":PID,"Quote Name":"Q2","Active":"ACTIVE","Approval Match":"APPROVED"},
          {"Approved AMEA ID":PID,"Quote Name":"Wrong","Active":"ACTIVE","Approval Match":"NOT_APPROVED"}
        ]}),[BASE])[0]
        self.assertEqual(r["Quote Match State"],"MULTIPLE_QUOTE_REVIEW")
        self.assertEqual(r["Quote Full Name"],"Q1\nQ2")

    def test_unrelated_prepayment_fails_closed(self):
        r=prepare_project_board(sources(**{"Feishu Latest Prepayments":[{
          "Quotation Number":"AMEA2026999999","Project Number":"X209SC26090000"
        }]}),[BASE])[0]
        self.assertEqual(r["Prepayment"],"NOT_VERIFIED")

    def test_exact_x_prepayment_only_on_unique_subproject_parent(self):
        life={"AMEA":PID,"Project / Sub-project":"X209SC26102746-Z01"}
        prep={"Quotation Number":"AMEA2026100751-01","Project Number":"X209SC26102746"}
        r=prepare_project_board(sources(**{"BI Project Lifecycle Overview":[life],
          "Feishu Latest Prepayments":[prep]}),[BASE])[0]
        self.assertEqual(r["Prepayment"],"YES")
        self.assertEqual(r["Prepayment Evidence"],"FEISHU_UNIQUE_X")

    def test_po_report_is_inferred_not_po_mail_verified(self):
        life={"AMEA":PID,"CSS Stage (legacy)":"Final report ready"}
        r=prepare_project_board(sources(**{"BI Project Lifecycle Overview":[life]}),[BASE])[0]
        self.assertEqual(r["PO Evidence"],"REPORT_STATEMENT_INFERRED")

    def test_clamp_invalid_progress(self):
        self.assertIsNone(percent("-1"))
        self.assertIsNone(percent("103"))
        self.assertEqual(bar(None),"미확인")

if __name__=="__main__":
    unittest.main()
