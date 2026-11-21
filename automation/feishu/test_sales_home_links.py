#!/usr/bin/env python3
"""Synthetic-only tests: never contact Feishu and never use real credentials."""
import sys
import unittest
import urllib.error
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sales_home_links import (
    TARGETS, LINK_LABELS, EXPECTED_STATUS, url, plan, validate_current_link,
    link_url, require_success, extract_token, pages, safe_page_get,
    READ_MAX_RETRIES
)

def record(key, href="", record_id=None):
    return {
        "record_id": record_id or "rec_" + key,
        "fields": {
            "Menu Key": key,
            "바로가기": {"text": "열기", "link": href} if href else None,
            "바로가기 URL": href,
            "화면": "07 · 내 X 하위 프로젝트" if key == "X_MY_PROJECTS" else "Other",
            "데이터 상태": "DASHBOARD_NOT_VERIFIED",
        },
    }

class SalesHomeSafety(unittest.TestCase):
    def test_one_page_timeout_is_retried_with_same_cursor_no_duplicate(self):
        seen = []
        def get(method, path, token=None):
            self.assertEqual(method, "GET")
            seen.append(path)
            if len(seen) == 1:
                return {"code": 0, "data": {
                    "has_more": True, "page_token": "cursor-one",
                    "items": [{"record_id": "rec1"}]}}
            if len(seen) == 2:
                raise TimeoutError("synthetic timeout, no credentials")
            return {"code": 0, "data": {
                "has_more": False, "items": [{"record_id": "rec2"}]}}
        with mock.patch("sales_home_links.request", side_effect=get), \
             mock.patch("sales_home_links.time.sleep") as sleep:
            got = list(pages("/dummy/tables/id/records", "synthetic-token"))
        self.assertEqual([r["record_id"] for r in got], ["rec1", "rec2"])
        self.assertEqual(seen[1], seen[2])
        self.assertIn("page_token=cursor-one", seen[2])
        sleep.assert_called_once()

    def test_transient_http_503_read_is_retried(self):
        err = urllib.error.HTTPError(
            "https://open.feishu.cn", 503, "synthetic", None, None)
        with mock.patch("sales_home_links.request", side_effect=[
                err, {"code": 0, "data": {"has_more": False, "items": []}}]) as req, \
             mock.patch("sales_home_links.time.sleep") as sleeper:
            self.assertEqual(list(pages("/dummy", "token")), [])
        self.assertEqual(req.call_count, 2)
        sleeper.assert_called_once()

    def test_http_400_read_is_not_retried(self):
        err = urllib.error.HTTPError(
            "https://open.feishu.cn", 400, "bad request", None, None)
        with mock.patch("sales_home_links.request", side_effect=err) as req, \
             mock.patch("sales_home_links.time.sleep") as sleeper:
            with self.assertRaises(urllib.error.HTTPError):
                list(pages("/dummy", "token"))
        req.assert_called_once()
        sleeper.assert_not_called()

    def test_read_transient_exhaustion_fails_closed_without_values(self):
        with mock.patch("sales_home_links.request",
                        side_effect=TimeoutError("SECRET_RAW_URL")) as req, \
             mock.patch("sales_home_links.time.sleep") as sleeper:
            with self.assertRaisesRegex(
                    RuntimeError, "FEISHU_READ_PAGE_TRANSIENT_EXHAUSTED") as ctx:
                safe_page_get("/dummy", "synthetic-token")
        self.assertNotIn("SECRET_RAW_URL", str(ctx.exception))
        self.assertEqual(req.call_count, READ_MAX_RETRIES + 1)
        self.assertEqual(sleeper.call_count, READ_MAX_RETRIES)

    def test_transient_transport_retries_are_get_only(self):
        with mock.patch("sales_home_links.request", return_value={
                "code": 0, "data": {"items": [], "has_more": False}}) as req:
            list(pages("/dummy", "token"))
        self.assertEqual(req.call_args.args[0], "GET")

    def test_exact_known_urls(self):
        self.assertEqual(url("blkzYT2OAVQssL3Y"),
            "https://ocnz4cb25scn.feishu.cn/base/IpMkbUD0vaFqtYs93a3csXtdn1b?table=blkzYT2OAVQssL3Y")

    def test_three_exact_keys_only_with_verified_dashboard_status(self):
        records = [record(k) for k in TARGETS] + [record("SIF_EVIDENCE")]
        changes = plan(records)
        self.assertEqual(set(changes), set(TARGETS))
        self.assertTrue(all(item["fields"]["데이터 상태"]==EXPECTED_STATUS for item in changes.values()))
        self.assertEqual(changes["X_MY_PROJECTS"]["fields"]["화면"],
                         "07 · 프로젝트 운영 대시보드")
        self.assertEqual(changes["WEEKLY_TREND"]["fields"]["바로가기"]["text"], LINK_LABELS["WEEKLY_TREND"])

    def test_second_run_idempotent(self):
        rows = []
        for key, (block, label) in TARGETS.items():
            row = record(key, url(block))
            row["fields"]["바로가기"] = {"text": LINK_LABELS[key], "link": url(block)}
            row["fields"]["데이터 상태"] = EXPECTED_STATUS
            if label is not None:
                row["fields"]["화면"] = label
            rows.append(row)
        self.assertTrue(all(not r["fields"] for r in plan(rows).values()))

    def test_title_link_corrects_only_text_when_url_matches(self):
        rows=[]
        for key,(block,label) in TARGETS.items():
            x=record(key,url(block))
            x["fields"]["데이터 상태"]=EXPECTED_STATUS
            if label is not None:x["fields"]["화면"]=label
            rows.append(x)
        changes=plan(rows)
        self.assertTrue(all(set(change["fields"])=={"바로가기"} for change in changes.values()))
        self.assertEqual(changes["MONTHLY_TREND"]["fields"]["바로가기"]["text"],
                         LINK_LABELS["MONTHLY_TREND"])

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
