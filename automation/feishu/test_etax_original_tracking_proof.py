#!/usr/bin/env python3
"""The original Feishu eTax status must not auto-convert to Revenue."""
import unittest
from unittest import mock
from qq_mail_ingest import SafeError
import etax_original_tracking_proof as m


class OriginalTrackingProofTests(unittest.TestCase):
    def test_distinguish_status_from_accounting_proof(self):
        self.assertEqual(m.classify_status("YES"),
                         "TRACKING_MARKED_ISSUED_NOT_ACCOUNTING_PROOF")
        self.assertEqual(m.classify_status("已开票"),
                         "TRACKING_MARKED_ISSUED_NOT_ACCOUNTING_PROOF")
        self.assertEqual(m.classify_status("No"),
                         "TRACKING_MARKED_NOT_ISSUED")
        self.assertEqual(m.classify_status("=XLOOKUP(D21,...)"),
                         "UNKNOWN_NO_TRUSTED_STATUS")
        self.assertEqual(m.classify_status(""),"UNKNOWN_NO_TRUSTED_STATUS")
        self.assertEqual(m.classify_status("2026-10-22"),
                         "TRACKING_DATE_PRESENT_VERIFY_DATE_TYPE")
        self.assertEqual(m.classify_status("A different status"),
                         "TRACKING_VALUE_UNRECOGNIZED_REVIEW")

    def test_map_exact_D_id_to_H_status_only(self):
        rows=[["ERP Invoice","unused","unused","unused","Issued"],
              ["20910000203",None,None,None,"YES"],
              ["20910000208",None,None,None,"NO"],
              ["20910000209",None,None,None,""],
              ["20910000197",None,None,None,"PENDING"],
              ["209126001032",None,None,None,"2026-10-30"]]
        keys=m.build_index(rows)
        self.assertEqual(keys["20910000203"],("YES",2))
        self.assertEqual(keys["20910000208"],("NO",3))
        self.assertEqual(keys["20910000209"],("",4))
        self.assertEqual(len(keys),5)

    def test_duplicate_invoice_fails_without_even_one_false_confirmation(self):
        with self.assertRaisesRegex(SafeError,"DUPLICATE_INVOICE_ID"):
            m.build_index([["20910000203",None,None,None,"YES"],
                           ["20910000203",None,None,None,"YES"]])

    def test_other_customers_not_in_targets_are_not_leaked_into_report(self):
        x=m.build_index([["209126000001",None,None,None,"YES"],
                         ["20910000203",None,None,None,"YES"]])
        self.assertEqual(set(x),{"20910000203"})

    def test_api_calls_are_get_only_to_original_spreadsheet(self):
        calls=[]
        def fake(verb,path,token,action):
            calls.append((verb,path))
            if path.endswith("/sheets/query"):
                return {"sheets":[
                    {"title":"Unrelated","sheet_id":"x1"},
                    {"title":"Tracking file 2026","sheet_id":"abc123",
                     "grid_properties":{"row_count":1}}]}
            if "/values/" in path:
                return {"valueRange":{"values":[
                    ["20910000203",None,None,None,"YES"]]},"revision":10}
            raise AssertionError(path)
        with mock.patch.object(m,"api",side_effect=fake):
            rows,revision=m.read_tracking("read-only")
        self.assertEqual(revision,10)
        self.assertEqual(m.build_index(rows)["20910000203"][0],"YES")
        self.assertEqual(len(calls),2)
        self.assertTrue(all(call[0]=="GET" for call in calls))
        self.assertTrue(all("WI6msu7UihcZQotx8XKjDbFypvh" in call[1]
                            for call in calls))

    def test_declared_range_more_than_hard_cap_is_never_partial_proof(self):
        with mock.patch.object(m,"api",return_value={"sheets":[
                {"title":"Tracking file 2026","sheet_id":"aaa",
                 "grid_properties":{"row_count":20001}}]}) as call:
            with self.assertRaisesRegex(SafeError,"FULL_ROW_COVERAGE_NOT_PROVABLE"):
                m.read_tracking("t")
            call.assert_called_once()

    def test_multiple_pages_exhaustively_scanned_before_not_found(self):
        paths=[]
        def reply(method,path,token,action):
            paths.append(path)
            if path.endswith("/sheets/query"):
                return {"sheets":[{"title":"Tracking file 2026",
                                   "sheet_id":"abc123",
                                   "grid_properties":{"row_count":1002}}]}
            if "D1%3AH1000" in path or "D1%3AH1000" in path.upper():
                return {"valueRange":{"values":[
                    ["20910000203",None,None,None,"YES"]]},"revision":12}
            if "D1001%3AH1002" in path or "D1001%3AH1002" in path.upper():
                return {"valueRange":{"values":[
                    ["20910000208",None,None,None,"NO"],
                    ["20910000209",None,None,None,"2026.10.28"]]},
                    "revision":12}
            raise AssertionError(path)
        with mock.patch.object(m,"api",side_effect=reply):
            rows,revision=m.read_tracking("t")
        self.assertEqual(len(rows),1002)
        indexes=m.build_index(rows)
        self.assertEqual(indexes["20910000208"],("NO",1001))
        self.assertEqual(indexes["20910000209"],("2026.10.28",1002))
        self.assertEqual(revision,12)
        self.assertEqual(m.classify_status("2026.10.28"),
                         "TRACKING_DATE_PRESENT_VERIFY_DATE_TYPE")
        self.assertEqual(len(paths),3)
        self.assertTrue(all("/sheets/" in p or "/values/" in p for p in paths))

    def test_permissions_not_silently_a_no_record(self):
        with mock.patch.object(m,"api",side_effect=SafeError(
                "etax_tracking_sheet_catalog_CODE_1310213")):
            with self.assertRaisesRegex(SafeError,"1310213"):
                m.read_tracking("read-only")


if __name__=="__main__":
    unittest.main()
