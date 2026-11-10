#!/usr/bin/env python3
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from project_quote_home_links import desired_rows, matches

class TestProjectHomeLinks(unittest.TestCase):
    def setUp(self):
        self.ids={"프로젝트 운영 · 진행 중 (Quote)":"tblIy2hhOEGNw34E",
                  "프로젝트 운영 · 완료·결제 (Quote)":"tblhfb6lQJst2gR7"}
    def test_two_links_keep_dashboard_untouched(self):
        links=desired_rows(self.ids)
        self.assertEqual(set(links),{"PROJECT_ACTIVE_QUOTE","PROJECT_BILLING_QUOTE"})
        self.assertNotIn("X_MY_PROJECTS",links)
    def test_exact_source_base(self):
        x=desired_rows(self.ids)["PROJECT_ACTIVE_QUOTE"]
        self.assertEqual(x["바로가기"]["link"],
            "https://ocnz4cb25scn.feishu.cn/base/IpMkbUD0vaFqtYs93a3csXtdn1b?table=tblIy2hhOEGNw34E")
    def test_missing_destination_blocks_writes(self):
        with self.assertRaisesRegex(RuntimeError,"DERIVED_TABLE_NOT_FOUND"):
            desired_rows({})
    def test_correct_row_no_update(self):
        row=desired_rows(self.ids)["PROJECT_BILLING_QUOTE"]
        self.assertTrue(matches(row,row))
        self.assertFalse(matches({**row,"화면":"wrong"},row))

if __name__=="__main__":
    unittest.main()
