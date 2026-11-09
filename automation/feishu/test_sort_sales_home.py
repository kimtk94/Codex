#!/usr/bin/env python3
"""Unit tests for persistent Feishu Sales Home sort."""
import unittest
from unittest import mock
import sort_sales_home as s


class SortTests(unittest.TestCase):
    def test_config(self):
        self.assertTrue(s.sort_matches({"sort_config":[{"field":"표시순서","desc":False}]}, "fld123"))
        self.assertTrue(s.sort_matches({"data":{"sort_config":[{"field":"fld123","desc":False}]}}, "fld123"))
        for value in ({"sort_config":[]}, {"sort_config":[{"field":"표시순서","desc":True}]},
                      {"sort_config":[{"field":"화면","desc":False}]}):
            self.assertFalse(s.sort_matches(value, "fld123"))

    def test_filter_guard(self):
        valid={"view_name":s.CURATED_VIEW,"view_type":"grid",
               "property":{"filter_info":{"conjunction":"and","conditions":[{
                   "field_id":"fldFilter", "operator":"is", "value":'["주요"]'}]}}}
        s.verify_filtered_view(valid, "fldFilter")
        with self.assertRaisesRegex(s.SafeError,"MISMATCH"):
            s.verify_filtered_view(valid, "other")

    def test_cli_safe_failure(self):
        with mock.patch.object(s.subprocess, "run") as proc:
            proc.return_value.returncode=1
            with self.assertRaisesRegex(s.SafeError, "CLI_FAILED"):
                s.run_cli("+view-set-sort",s.EXPECTED_BASE,"tbl","vew",s.EXPECTED)

    def test_sorted_records_verification(self):
        view_rows=[{"fields":{"Menu Key":key}}
                   for key in s.CURATED_ORDER]
        full_rows=[{"fields":{"Menu Key":key,"표시순서":str(i)}}
                   for i,key in enumerate(s.CURATED_ORDER,1)]
        with mock.patch.object(s,"api",side_effect=[
                {"items":list(reversed(view_rows)),"has_more":False},
                {"items":full_rows,"has_more":False}]):
            self.assertTrue(s.verify_view_rows("token","root","view"))
        bad_rows=list(full_rows)
        bad_rows[0]={"fields":{"Menu Key":s.CURATED_ORDER[0],"표시순서":99}}
        with mock.patch.object(s,"api",side_effect=[
                {"items":view_rows,"has_more":False},
                {"items":bad_rows,"has_more":False}]):
            with self.assertRaisesRegex(s.SafeError,"READBACK_MISMATCH"):
                s.verify_view_rows("token","root","view")

    def test_network_read_failure_is_separately_labeled(self):
        with mock.patch.object(s, "verify_view_rows",
                               side_effect=s.SafeError("portal_sorted_records_NETWORK_ERROR")):
            try:
                s.verify_view_rows("t","p","v")
            except s.SafeError as exc:
                self.assertTrue(str(exc).endswith("_NETWORK_ERROR"))

    def test_numeric_rank(self):
        self.assertEqual(s.numeric_rank("12"),12)
        self.assertEqual(s.numeric_rank(1.0),1)
        self.assertEqual(s.numeric_rank({"value":"9"}),9)
        self.assertIsNone(s.numeric_rank(None))


if __name__=="__main__":
    unittest.main()
