#!/usr/bin/env python3
"""PO manual document verification must never be inferred from notice alone."""
import unittest
from unittest import mock
import contract_po_tracker as p


def due():
    return {
        "Project ID": "AMEA2026042239", "PO Status": "PO_REQUIRED", "Contract Source": "CSS",
        "Next Action": "REQUEST_PO", "Contract Mail Key": "source-mail",
        "Evidence Rule": "ORIGINAL_EXACT_SENDER_SUBJECT_V1", "Last Sync UTC": "now",
    }


def manual(verified="FILE_VERIFIED", ref="Feishu://po-file-123",
           by="reviewer", checked="2026-11-06T06:00:00+00:00"):
    return {"PO Document Verification": verified, "PO Document Reference": ref,
            "PO Verified By": by, "PO Verified At": checked}


class POManualVerificationTests(unittest.TestCase):
    def test_incomplete_document_attestation_does_not_clear_po_queue(self):
        for item in (manual(ref=""), manual(by=""), manual(checked=""),
                     manual(verified=""), manual(checked="2026-11-06"),
                     manual(verified="RECEIVED_NOTICE")):
            self.assertFalse(p.manual_file_verified(item))
            row = due()
            p.apply_followup([row], {"AMEA2026042239": {"fields": item}})
            self.assertEqual(row["PO Followup Queue"], "PO_REQUIRED")
            self.assertEqual(row["Next Action"], "REQUEST_PO")

    def test_complete_document_attestation_marks_only_derived_queue(self):
        row = due()
        p.apply_followup([row], {"AMEA2026042239": {"fields": manual()}})
        self.assertEqual(row["PO Followup Queue"], "FILE_VERIFIED_ATTESTED")
        self.assertEqual(row["PO Status"], "PO_REQUIRED")
        self.assertEqual(row["Next Action"], "NO_PO_FOLLOWUP_MANUAL_FILE_ATTESTED")
        self.assertEqual(row["Contract Mail Key"], "source-mail")
        self.assertNotIn("PO Document Reference", row)

    def test_mail_receipt_notice_still_needs_file_verification(self):
        row = {**due(), "PO Status": "PO_RECEIVED_NOTICE"}
        p.apply_followup([row], {})
        self.assertEqual(row["PO Followup Queue"], "PO_FILE_REVIEW")
        self.assertEqual(row["Next Action"], "VERIFY_PO_FILE")

    def test_po_receipt_notice_with_manual_proof_is_done(self):
        row = {**due(), "PO Status": "PO_RECEIVED_NOTICE"}
        p.apply_followup([row], {"AMEA2026042239": {"fields": manual()}})
        self.assertEqual(row["PO Followup Queue"], "FILE_VERIFIED_ATTESTED")

    def test_manual_proof_does_not_edit_source_rows(self):
        row = due()
        original = dict(row)
        p.apply_followup([row], {})
        self.assertEqual(row["PO Status"], original["PO Status"])
        self.assertEqual(row["Contract Mail Key"], original["Contract Mail Key"])
        self.assertNotIn("PO Document Verification", row)

    def test_fields_schema_contains_manual_and_derived_fields(self):
        self.assertTrue({"PO Followup Queue", "PO Document Verification",
                         "PO Document Reference", "PO Verified At",
                         "PO Verified By"}.issubset(set(p.FIELDS)))

    def test_sync_updates_followup_without_overwriting_manual_fields(self):
        expected=due()
        old_fields={**due(), **manual()}
        record={"record_id":"r1","fields":old_fields}
        writes=[]
        def post(method,path,token,data=None,action=""):
            self.assertEqual(method, "POST")
            payload=data["records"]
            self.assertEqual(len(payload),1)
            fields=payload[0]["fields"]
            self.assertNotIn("PO Document Verification",fields)
            self.assertNotIn("PO Document Reference",fields)
            self.assertEqual(fields["PO Followup Queue"], "FILE_VERIFIED_ATTESTED")
            writes.append(fields)
            return {"records":[{"record_id":"r1"}]}
        def records(path,token,action):
            if action=="contract_po_existing":
                return [record]
            assert action=="contract_po_readback"
            return [{"record_id":"r1", "fields":{**old_fields,**writes[0]}}]
        with mock.patch.object(p,"api",side_effect=post), mock.patch.object(
                p,"list_all",side_effect=records):
            self.assertEqual(p.sync("tok","path",[expected]),(0,1,1))
        self.assertEqual(expected["PO Followup Queue"],"FILE_VERIFIED_ATTESTED")
        self.assertEqual(old_fields["PO Document Reference"],manual()["PO Document Reference"])

    def test_pending_view_filters_derived_queue_not_notice_status(self):
        field_id="fldFOLLOWUP"
        async_view={
            "view_name":"PO 수령 필요",
            "property":{"filter_info":{"conjunction":"and","conditions":[{
                "field_id":field_id,"operator":"is","value":'["PO_REQUIRED"]'}]}}
        }
        events=[]
        def api(method,path,token,data=None,action=""):
            events.append((method,data))
            if method=="GET":return {"view":async_view}
            return {}
        with mock.patch.object(p,"list_views",return_value={"PO 수령 필요":"view1"}), \
             mock.patch.object(p,"api",side_effect=api):
            self.assertEqual(p.ensure_pending_view("t","path",field_id),"view1")
        self.assertEqual(events[0][1]["property"]["filter_info"]["conditions"][0]["field_id"],field_id)


if __name__=="__main__":
    unittest.main()
