"""Credential-free Drive permission-surface checks. All outcomes remain HOLD."""
import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

from automation.css_mail.qq_replay_writer_access_audit import (
    analyze_permissions, fetch_permissions, main
)


def baseline():
    return [
        {"id": "id_owner", "type": "user", "role": "owner",
         "emailAddress": "private-owner@example.invalid"},
        {"id": "id_writer", "type": "user", "role": "writer",
         "emailAddress": "private-writer@example.invalid"},
        {"id": "id_sa1", "type": "user", "role": "writer",
         "emailAddress": "one@project.iam.gserviceaccount.com"},
        {"id": "id_sa2", "type": "user", "role": "writer",
         "emailAddress": "two@project.iam.gserviceaccount.com"},
    ]


class DriveWriterAuditTests(unittest.TestCase):
    def test_current_four_editors_are_never_serialized(self):
        result = analyze_permissions(baseline())
        self.assertEqual(result["reason_code"], "KNOWN_MULTI_WRITER_HOLD")
        self.assertEqual(result["editor_count"], 4)
        self.assertEqual(result["service_account_editor_count"], 2)
        self.assertEqual(result["count_baseline_matched"], 1)
        self.assertEqual(result["all_external_writers_excluded"], 0)
        self.assertEqual(result["qq_stage_writes"], 0)
        self.assertFalse(result["can_execute_replay"])
        self.assertNotIn("private-owner", json.dumps(result))

    def test_user_added_or_role_changed_detected(self):
        cases = (
            baseline() + [{"id": "extra", "type": "user", "role": "reader",
                           "emailAddress": "new@example.invalid"}],
            [dict(item, role="reader") if item["id"]=="id_writer" else item
             for item in baseline()],
            [dict(item, emailAddress="new@example.invalid")
             if item["id"]=="id_sa2" else item for item in baseline()],
        )
        for case in cases:
            with self.subTest(permissions=case):
                result = analyze_permissions(case)
                self.assertEqual(result["reason_code"], "PERMISSION_COUNT_DRIFT")
                self.assertEqual(result["all_external_writers_excluded"], 0)

    def test_domain_public_and_group_grants_are_exposure(self):
        for typ, role in (("anyone", "reader"), ("domain", "writer"),
                          ("group", "writer")):
            p=baseline() + [{"id": typ, "type": typ, "role": role}]
            r=analyze_permissions(p)
            self.assertEqual(r["reason_code"],"EXPANDED_PERMISSION_SURFACE")
            self.assertEqual(r["can_execute_replay"],False)

    def test_missing_id_missing_writer_email_and_duplicate_are_incomplete(self):
        for change in ({"id": None}, {"emailAddress": None}, {"id": "id_sa1"},
                       {"role": "unknown-role"}, {"deleted": True}):
            p=baseline()
            p[3]={**p[3], **change}
            r=analyze_permissions(p)
            self.assertEqual(r["reason_code"],"PERMISSION_INVENTORY_INCOMPLETE")

    def test_no_permissions_or_wrong_type_fail_closed(self):
        for case in ([], None, "x", [None]):
            self.assertEqual(analyze_permissions(case)["status"],"HOLD")
            self.assertEqual(analyze_permissions(case)["editor_count"],0)

    def test_get_only_and_page_two_safely_processed(self):
        calls=[]
        class Response:
            def __init__(self, payload):
                self.status_code=200
                self.payload=payload
            def json(self):
                return self.payload
        class Session:
            def get(self,url,params,timeout,allow_redirects):
                calls.append((url,dict(params),timeout,allow_redirects))
                if len(calls)==1:
                    return Response({"permissions":baseline()[:2],
                                     "nextPageToken":"PAGE_TWO"})
                return Response({"permissions":baseline()[2:]})
        out=fetch_permissions(Session(),"A"*30)
        self.assertEqual(len(out),4)
        self.assertEqual(len(calls),2)
        self.assertTrue(all(not c[3] for c in calls))
        self.assertTrue(all(c[2]==30 for c in calls))
        self.assertTrue(all("permissions" in c[0] for c in calls))

    def test_redirect_and_malformed_response_hard_hold(self):
        class Response:
            status_code=302
            def json(self):
                return {}
        class Session:
            def get(self,*args,**kwargs):
                return Response()
        with self.assertRaisesRegex(ValueError, "SOURCE_PERMISSION_READ_FAILED"):
            fetch_permissions(Session(),"B"*28)
        with self.assertRaisesRegex(ValueError, "SOURCE_FILE_ID_INVALID"):
            fetch_permissions(Session(),"bad/file")

    def test_missing_credentials_prints_no_identifiers(self):
        sink=io.StringIO()
        with mock.patch.dict(os.environ,{
            "CSS_SHEET_ID":"", "CKD_DRIVE_SA_JSON":""
        }), redirect_stdout(sink):
            self.assertEqual(main(),0)
        obj=json.loads(sink.getvalue().split("=",1)[1])
        self.assertEqual(obj["reason_code"],"PERMISSION_AUDIT_NOT_CONFIGURED")
        self.assertEqual(obj["qq_stage_writes"],0)
        self.assertFalse(obj["can_execute_replay"])


if __name__=="__main__":
    unittest.main()
