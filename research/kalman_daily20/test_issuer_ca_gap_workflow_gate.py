import unittest
from issuer_ca_gap_workflow_gate import validate, VERIFIED

class IssuerGapWorkflowGateTests(unittest.TestCase):
    def setUp(self):
        self.report = {
            "version":"daily20-issuer-ca-gap-audit-v1",
            "status":"ISSUER_DISTRIBUTIONS_2_EVENTS_HOLD",
            "research_only":True,"production_writes":False,"strategy_promoted":False,
            "issuer_payments_certified":0,"source_finality_verified":0,
            "unarchived_research_leads_are_certified":False,
            "both_archived_sources_verified":True,
            "events":[
                {"symbol":"QQQ","ex_date":"2018-06-18","archived_evidence_status":VERIFIED,
                 "research_hold":True,"actual_payment_certified":False,
                 "independent_adjustment_factor_certified":False,"independent_close_certified":False,
                 "issuer_ex_date_and_amount_jointly_certified":False},
                {"symbol":"QLD","ex_date":"2023-09-20","archived_evidence_status":VERIFIED,
                 "research_hold":True,"actual_payment_certified":False,
                 "independent_adjustment_factor_certified":False,"independent_close_certified":False,
                 "issuer_ex_date_and_amount_jointly_certified":False},
            ]}
    def test_complete_sources_still_hold_cash_and_prices(self):
        r=validate(self.report)
        self.assertEqual(r["workflow_gate"],"PASS")
        self.assertEqual(r["evidence_state"],"COMPLETE_UNCERTIFIED")
        self.assertFalse(r["strategy_promoted"])
        self.assertEqual(r["issuer_payments_certified"],0)
    def test_external_403_is_hold_not_pipeline_failure(self):
        self.report["events"][0]["archived_evidence_status"]="SOURCE_NOT_FETCHED_HOLD"
        self.report["both_archived_sources_verified"]=False
        r=validate(self.report)
        self.assertEqual(r["workflow_gate"],"PASS")
        self.assertEqual(r["evidence_state"],"INCOMPLETE_HOLD")
        self.assertEqual(len(r["missing_source_events"]),1)
        self.assertTrue(r["downstream_research_may_continue"])
    def test_missing_raw_file_is_hold_not_pipeline_failure(self):
        self.report["events"][1]["archived_evidence_status"]="SOURCE_RAW_BYTES_MISSING_HOLD"
        self.report["both_archived_sources_verified"]=False
        self.assertEqual(validate(self.report)["evidence_state"],"INCOMPLETE_HOLD")
    def test_unknown_source_state_is_schema_failure(self):
        self.report["events"][0]["archived_evidence_status"]="UNEXPECTED_SUCCESS"
        with self.assertRaisesRegex(ValueError,"SOURCE_STATE_UNKNOWN"):
            validate(self.report)
    def test_any_payment_promotion_is_rejected(self):
        self.report["events"][0]["actual_payment_certified"]=True
        with self.assertRaisesRegex(ValueError,"EVENT_PROMOTION_INVALID"):
            validate(self.report)
    def test_top_level_promotion_is_rejected(self):
        self.report["strategy_promoted"]=True
        with self.assertRaisesRegex(ValueError,"GOVERNANCE_OR_FINALITY"):
            validate(self.report)
    def test_event_omission_is_rejected(self):
        self.report["events"].pop()
        with self.assertRaisesRegex(ValueError,"EVENT_COUNT_INVALID"):
            validate(self.report)
    def test_archive_boolean_must_match_event_states(self):
        self.report["events"][0]["archived_evidence_status"]="SOURCE_NOT_FETCHED_HOLD"
        with self.assertRaisesRegex(ValueError,"ARCHIVE_FLAG_DISAGREES"):
            validate(self.report)

if __name__=="__main__":
    unittest.main()
