"""Post-writer verification is a read-only, fail-closed snapshot gate."""
import unittest

from css_feishu_post_sync_verify import evaluate

NAMES=("Payment Outstanding", "Payment Receipt", "Prepayments", "eTax Invoice")
CATEGORIES=("SOURCE_FILLED_MIRROR_EMPTY","MIRROR_FILLED_SOURCE_EMPTY",
            "WHITESPACE_ONLY","UNICODE_NORMALIZATION_ONLY",
            "NUMERIC_DISPLAY_ONLY","SUBSTANTIVE_NONEMPTY_CHANGE")
ROLES=("FINANCIAL_FIELD","DATE_TIME_FIELD","STATUS_FIELD","NOTE_FIELD",
       "REFERENCE_FIELD","OTHER_OR_UNCLASSIFIED_FIELD")


def source_row(changed=0, kind="SUBSTANTIVE_NONEMPTY_CHANGE"):
    shapes={x:0 for x in CATEGORIES}
    shapes[kind]=changed
    roles={x:0 for x in ROLES}
    roles["FINANCIAL_FIELD"]=changed
    return {"status":"SINK_LAG" if changed else "PASS_SNAPSHOT_PROJECTION_ONLY",
            "content_different_cell_count":changed,
            "drift_characteristics":shapes,
            "drift_business_field_roles":roles}


class PostWriterProofTests(unittest.TestCase):
    def base(self):
        return {"source_probe":"PASS_ORIGINAL_READ",
                "mirror_projection_status":"PASS",
                "formats":{k:source_row() for k in NAMES}}

    def test_complete_exact_source_projection_can_pass_snapshot_only(self):
        r=evaluate(self.base())
        self.assertTrue(r["projection_equal"])
        self.assertEqual(r["state"],"PASS_SNAPSHOT_PROJECTION_ONLY")
        self.assertFalse(r["bank_receipt_verified"])
        self.assertFalse(r["finance_authority_verified"])
        self.assertFalse(r["sfdc_save_verified"])

    def test_one_financial_cell_mismatch_blocks_all_downstream(self):
        x=self.base()
        x["formats"]["Payment Receipt"]=source_row(1)
        x["mirror_projection_status"]="SINK_LAG"
        r=evaluate(x)
        self.assertEqual(r["state"],"SOURCE_MIRROR_HOLD")
        self.assertEqual(r["formats"]["Payment Receipt"]["financial_field_cells"],1)
        self.assertEqual(r["customer_data_writes"],0)

    def test_presentation_difference_also_blocks(self):
        x=self.base()
        x["formats"]["Prepayments"]=source_row(2,"NUMERIC_DISPLAY_ONLY")
        x["mirror_projection_status"]="SINK_LAG"
        self.assertFalse(evaluate(x)["projection_equal"])

    def test_source_missing_never_acts_like_zero(self):
        r=evaluate({"mirror_projection_status":"PASS", "formats":{}})
        self.assertEqual(r["state"],"SOURCE_MIRROR_HOLD")
        self.assertIsNone(r["formats"]["Payment Outstanding"]["changed_cells"])
        r=evaluate({"source_probe":"SOURCE_UNAVAILABLE","mirror_projection_status":"PASS",
                    "formats":{k:source_row() for k in NAMES}})
        self.assertFalse(r["projection_equal"])

    def test_manifest_mismatch_cannot_be_hidden_by_zero_cell_changes(self):
        x=self.base()
        x["formats"]["eTax Invoice"]=dict(source_row(),status="SINK_LAG")
        x["mirror_projection_status"]="SINK_LAG"
        r=evaluate(x)
        self.assertEqual(r["formats"]["eTax Invoice"]["triage"],
                         "SOURCE_VERSION_OR_METADATA_REVIEW")
        self.assertFalse(r["projection_equal"])


if __name__=="__main__":
    unittest.main()
