#!/usr/bin/env python3
import unittest
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from project_quote_home_links import desired_rows, matches, filter_keys, extend_filter, ALLOWED_VIEW_KEYS, EXPECTED_ORIGINAL_KEYS, MENU_FIELD_ID

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
    def _view(self,keys):
        return {"conjunction":"or","conditions":[
          {"field_id":MENU_FIELD_ID,"operator":"is","value":json.dumps([key]),"condition_id":"con-id"}
          for key in keys]}
    def test_original_five_conditions_preserved_and_two_added(self):
        initial=self._view(sorted(EXPECTED_ORIGINAL_KEYS))
        extended=extend_filter(initial)
        self.assertEqual(filter_keys(extended),ALLOWED_VIEW_KEYS)
        self.assertEqual(extended["conditions"][:5],
            [{k:v for k,v in x.items() if k!="condition_id"} for x in initial["conditions"]])
    def test_idempotent_after_seven(self):
        existing=self._view(sorted(ALLOWED_VIEW_KEYS))
        self.assertEqual(extend_filter(existing)["conditions"],existing["conditions"])
    def test_unknown_extra_key_blocks_changes(self):
        with self.assertRaisesRegex(RuntimeError,"UNEXPECTED_MENU_KEYS"):
            extend_filter(self._view(list(EXPECTED_ORIGINAL_KEYS)+["UNKNOWN_MENU"]))
    def test_non_menu_filter_blocks_changes(self):
        value=self._view(list(EXPECTED_ORIGINAL_KEYS))
        value["conditions"][0]["field_id"]="fldAnother"
        with self.assertRaisesRegex(RuntimeError,"UNEXPECTED_SHORTCUT_FILTER_CONDITION"):
            extend_filter(value)
    def test_missing_preexisting_key_blocks_changes(self):
        with self.assertRaisesRegex(RuntimeError,"SHORTCUT_FILTER_UNEXPECTED_MENU_KEYS"):
            extend_filter(self._view(list(EXPECTED_ORIGINAL_KEYS)[:4]))
    def test_correct_row_no_update(self):
        row=desired_rows(self.ids)["PROJECT_BILLING_QUOTE"]
        self.assertTrue(matches(row,row))
        self.assertFalse(matches({**row,"화면":"wrong"},row))

if __name__=="__main__":
    unittest.main()
