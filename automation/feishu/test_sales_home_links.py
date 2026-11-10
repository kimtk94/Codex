#!/usr/bin/env python3
"""Synthetic-only tests: never contact Feishu and never use real credentials."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sales_home_links import (
    TARGETS, url, plan, validate_current_link, link_url, require_success, extract_token
)

def record(key, href="", record_id=None):
    return {
        "record_id": record_id or "rec_" + key,
        "fields": {
            "Menu Key": key,
            "바로가기": {"text": "열기", "link": href} if href else None,
            "화면": "07 · 내 X 하위 프로젝트" if key == "X_MY_PROJECTS" else "Other",
            "데이터 상태": "DASHBOARD_NOT_VERIFIED",
        },
    }

class SalesHomeSafety(unittest.TestCase):
    def test_exact_known_urls(self):
        self.assertEqual(url("blkzYT2OAVQssL3Y"),
            "https://ocnz4cb25scn.feishu.cn/base/IpMkbUD0vaFqtYs93a3csXtdn1b?table=blkzYT2OAVQssL3Y")

    def test_three_exact_keys_only_and_no_status_write(self):
        records = [record(k) for k in TARGETS] + [record("SIF_EVIDENCE")]
        changes = plan(records)
        self.assertEqual(set(changes), set(TARGETS))
        self.assertTrue(all("데이터 상태" not in item["fields"] for item in changes.values()))
        self.assertEqual(changes["X_MY_PROJECTS"]["fields"]["화면"],
                         "07 · 프로젝트 운영 대시보드")
        self.assertEqual(changes["WEEKLY_TREND"]["fields"]["바로가기"]["text"], "열기")

    def test_second_run_idempotent(self):
        rows = []
        for key, (block, label) in TARGETS.items():
            row = record(key, url(block))
            if label is not None:
                row["fields"]["화면"] = label
            rows.append(row)
        self.assertTrue(all(not r["fields"] for r in plan(rows).values()))

    def test_missing_key_blocks_all_writes(self):
        with self.assertRaisesRegex(RuntimeError, "MISSING_HOME_MENU_KEY"):
            plan([record("WEEKLY_TREND"), record("X_MY_PROJECTS")])

    def test_duplicate_key_blocks_all_writes(self):
        with self.assertRaisesRegex(RuntimeError, "DUPLICATE_MENU_KEY"):
            plan([record(k) for k in TARGETS] + [record("WEEKLY_TREND", record_id="rec_duplicate")])

    def test_external_url_not_overwritten(self):
        with self.assertRaisesRegex(RuntimeError, "EXISTING_LINK_NOT_SAME_BASE"):
            plan([record("WEEKLY_TREND", "https://example.com/unexpected")] +
                 [record("MONTHLY_TREND"), record("X_MY_PROJECTS")])

    def test_other_feishu_base_not_overwritten(self):
        with self.assertRaisesRegex(RuntimeError, "EXISTING_LINK_NOT_SAME_BASE"):
            validate_current_link({"text":"열기","link":
                "https://ocnz4cb25scn.feishu.cn/base/ANOTHER_BASE?table=aaa"})

    def test_same_base_existing_link_can_be_replaced(self):
        row = record("X_MY_PROJECTS", url("tblOldProjectRegistry"))
        p = plan([record("WEEKLY_TREND"), record("MONTHLY_TREND"), row])
        self.assertEqual(link_url(p["X_MY_PROJECTS"]["fields"]["바로가기"]),
                         url("blkzYT2OAVQssL3Y"))

    def test_v3_token_at_top_level(self):
        self.assertEqual(extract_token({"code": 0, "tenant_access_token": "example"}), "example")

    def test_token_missing_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "FEISHU_TOKEN_UNAVAILABLE"):
            extract_token({"code": 0, "data": {}})

    def test_error_code_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "AUTH_API_ERROR_999"):
            require_success({"code": 999}, "AUTH")

if __name__ == "__main__":
    unittest.main()
