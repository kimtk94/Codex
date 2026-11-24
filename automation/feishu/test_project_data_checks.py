"""Synthetic evidence tests: no actual project data, API or credentials."""
import unittest
from project_data_checks import ProjectEvidence, carryover_fields, DATA_FIELDS
from project_progress_board import prepare_project_board, progress_phase, percent

PID = "AMEA2026000001"
OTHER = "AMEA2026000002"
X = "X209SC26000001-Z01"
RID = "a0P000000000001"
QID = "QID-2026-00001"

def portfolio(**kw):
    return {"Approved AMEA ID": PID, "Quote Name": "Quote A", "Active": "YES",
            "Approval Match": "APPROVED", "Quote QID": QID,
            "Salesforce Quote ID (18)": RID+"AAA", **kw}

def export(**kw):
    return {"AMEA Quotation ID": QID, "Salesforce Record ID": RID,
            "IsActive": "TRUE", **kw}

def life(**kw):
    return {"AMEA": PID, "Project / Sub-project": X,
            "Feishu Status (latest)": "Sequencing", **kw}

def sources(**kw):
    return {"CSS Project Dashboard": [{"project_id": PID, "current_stage": "Sequencing"}],
            "CSS Contract-SIF Tracker": [], "BI Project Lifecycle Overview": [life()],
            "Quote Portfolio": [portfolio()], "SFDC Quote Export": [export()],
            **kw}

def board(**kw):
    return {"Source Key": "PROJECT:"+PID, "AMEA": PID, "Quote Full Name": "Quote A",
            "Progress Phase": "04 시퀀싱", "Progress %": 70,
            "Completion Evidence": "NOT_VERIFIED", **kw}

def assess(s=None, b=None):
    return ProjectEvidence(s or sources()).assess(b or board(), progress_phase)


class DataChecks(unittest.TestCase):
    def test_exact_snapshot_not_end_to_end_or_live_claim(self):
        a = assess()
        self.assertEqual(a["PM Data Check"], "CHECKED")
        self.assertEqual(a["PM Quote Link"], "EXACT_QUOTE_SNAPSHOT")
        self.assertEqual(a["PM X Link"], "EXACT_LIFECYCLE_ONLY")
        self.assertEqual(a["PM Status Check"], "STAGE_REPORTED")
        self.assertEqual(set(a), set(DATA_FIELDS))

    def test_same_name_multiple_ids_conflict(self):
        a = assess(sources(**{"Quote Portfolio": [
            portfolio(), portfolio(**{"Salesforce Quote ID (18)": "a0P000000000002AAA"})
        ]}))
        self.assertEqual(a["PM Data Check"], "CONFLICT")
        self.assertEqual(a["PM Quote Link"], "CONFLICT_MULTIPLE_QUOTE_IDS")

    def test_quote_id_casing_not_collapsed(self):
        first = "a0PAb0000000001"
        second = "a0PaB0000000001"
        a = assess(sources(**{"Quote Portfolio": [
            portfolio(**{"Salesforce Quote ID (18)": first})],
            "SFDC Quote Export": [export(**{"Salesforce Record ID": second})]}))
        self.assertTrue(a["PM Quote Link"].startswith("CONFLICT_"))

    def test_quote_shared_between_projects(self):
        a = assess(sources(**{"Quote Portfolio": [portfolio(), portfolio(**{"Approved AMEA ID": OTHER})]}))
        self.assertEqual(a["PM Quote Link"], "CONFLICT_QUOTE_SHARED_AMEA")

    def test_quote_inactive_or_missing_never_exact(self):
        for data, expected in [
            ([], "REVIEW_QUOTE_EXPORT_MISSING"),
            ([export(IsActive="FALSE")], "CONFLICT_QUOTE_EXPORT_INACTIVE"),
            ([export(), export()], "CONFLICT_QUOTE_EXPORT_AMBIGUOUS"),
        ]:
            self.assertEqual(assess(sources(**{"SFDC Quote Export": data}))["PM Quote Link"], expected)

    def test_name_only_not_verified(self):
        a = assess(sources(**{"Quote Portfolio": [
            portfolio(**{"Quote QID": "", "Salesforce Quote ID (18)": ""})]}))
        self.assertEqual(a["PM Quote Link"], "REVIEW_QUOTE_ID_MISSING")

    def test_multiple_distinct_x_valid_but_not_sam_allocation(self):
        a = assess(sources(**{"BI Project Lifecycle Overview": [
            life(), life(**{"Project / Sub-project": "X209SC26000002-Z01"})]}))
        self.assertEqual(a["PM X Link"], "EXACT_LIFECYCLE_ONLY")

    def test_shared_x_and_duplicate_x(self):
        a = assess(sources(**{"BI Project Lifecycle Overview": [life(), life(AMEA=OTHER)]}))
        self.assertEqual(a["PM X Link"], "CONFLICT_X_SHARED_AMEA")
        a = assess(sources(**{"BI Project Lifecycle Overview": [life(), life()]}))
        self.assertEqual(a["PM X Link"], "REVIEW_DUPLICATE_X_ROWS")

    def test_missing_x_and_mixed_stage(self):
        a = assess(sources(**{"BI Project Lifecycle Overview": [life(**{"Project / Sub-project": ""})]}))
        self.assertEqual(a["PM X Link"], "REVIEW_X_ID_MISSING_OR_INVALID")
        a = assess(sources(**{"BI Project Lifecycle Overview": [
            life(), life(**{"Project / Sub-project": "X209SC26000002-Z01", "Feishu Status (latest)": "Sample QC"})]}))
        self.assertEqual(a["PM Status Check"], "MIXED_X_STAGES")

    def test_stage_disagreement_and_unknown_progress(self):
        a = assess(sources(**{"BI Project Lifecycle Overview": [life(**{"Feishu Status (latest)": "Sample QC"})]}),
                   board(**{"Progress %": None}))
        self.assertEqual(a["PM Status Check"], "STAGE_DIVERGENCE_REVIEW")
        self.assertIn("REVIEW_PROGRESS_UNKNOWN", a["PM Check Reasons"])

    def test_handoff_is_not_delivery_certificate(self):
        a = assess(b=board(**{"Completion Evidence": "CSS_EXPLICIT_FINAL_HANDOFF"}))
        self.assertEqual(a["PM Status Check"], "HANDOFF_SIGNAL_ONLY")
        self.assertIn("REVIEW_HANDOFF_VS_LIFECYCLE", a["PM Check Reasons"])

    def test_zero_progress_is_observed(self):
        self.assertEqual(percent(0), 0)
        self.assertNotIn("REVIEW_PROGRESS_UNKNOWN", assess(b=board(**{"Progress %": 0}))["PM Check Reasons"])

    def test_carryover_only_check_fields(self):
        a = carryover_fields()
        self.assertEqual(set(a), set(DATA_FIELDS))
        self.assertEqual(a["PM Source Coverage"], "CARRYOVER_REVIEW")
        self.assertEqual(a["PM Quote Link"], "NOT_RECHECKED")

    def test_projector_exposes_advisory_without_overwriting_business_state(self):
        s = sources()
        r = prepare_project_board(s, [{**board(), "Current Stage": "Sequencing",
                                     "Project": "Quote A"}])[0]
        self.assertEqual(r["PM Data Check"], "CHECKED")
        self.assertEqual(r["Workflow Lane"], "PRODUCTION_ACTIVE")
        self.assertEqual(r["Progress %"], 70)


if __name__ == "__main__":
    unittest.main()
