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
        rows=[{"fields":{"Menu Key":key,"표시순서":i}}
              for i,key in enumerate(s.CURATED_ORDER,1)]
        with mock.patch.object(s,"api",return_value={"items":rows,"has_more":False}):
            self.assertTrue(s.verify_view_rows("token","root","view"))
        with mock.patch.object(s,"api",return_value={"items":list(reversed(rows)),"has_more":False}):
            self.assertTrue(s.verify_view_rows("token","root","view"))
        bad_rows = list(rows)
        bad_rows[0] = {"fields":{"Menu Key":s.CURATED_ORDER[0],"표시순서":99}}
        with mock.patch.object(s,"api",return_value={"items":bad_rows,"has_more":False}), \
             mock.patch.object(s.time,"sleep"):
            with self.assertRaisesRegex(s.SafeError,"READBACK_MISMATCH"):
                s.verify_view_rows("token","root","view")


if __name__=="__main__":
    unittest.main()
