"""Offline checks for evidence-limited CSS body cache health publication."""
import datetime as dt
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

src=types.ModuleType("incremental_sync")
src.KST=dt.timezone(dt.timedelta(hours=9))
sys.modules["incremental_sync"]=src
spec=importlib.util.spec_from_file_location(
    "web_body_health",Path(__file__).with_name("web_body_health.py"))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class HealthTests(unittest.TestCase):
    def sheet(self, ids=None, statuses=None):
        ids=ids if ids is not None else [
            ["Mail UID"],["inbox:1"],["inbox:2"],["sent:3"],["inbox:4"]]
        statuses=statuses if statuses is not None else [
            ["Classification"],["WEB_REVIEW_CACHE"],["BODY_EMPTY_MIME"],
            ["WEB_REVIEW_CACHE"],["HEADER_ONLY_BODY_PENDING"]]
        def reading(_session,tab,area):
            if tab!=m.CACHE:raise AssertionError(tab)
            if area=="A1:A1000":return ids
            if area=="V1:V1000":return statuses
            raise AssertionError(area)
        with patch.object(m,"read",side_effect=reading):
            return m.cached_summary(object())

    def test_counts_distinguish_valid_mime_empty_and_header_only(self):
        total,states=self.sheet()
        self.assertEqual(total,4)
        self.assertEqual(states["WEB_REVIEW_CACHE"],2)
        self.assertEqual(states["BODY_EMPTY_MIME"],1)
        self.assertEqual(states["HEADER_ONLY_BODY_PENDING"],1)

    def test_unknown_status_cannot_be_published_as_pass(self):
        with self.assertRaisesRegex(RuntimeError,"UNKNOWN_STATUS"):
            self.sheet(statuses=[
                ["Classification"],["WEB_REVIEW_CACHE"],["WRONG"],
                ["WEB_REVIEW_CACHE"],["HEADER_ONLY_BODY_PENDING"]])

    def test_duplicate_uid_is_blocked(self):
        with self.assertRaisesRegex(RuntimeError,"UID_DUPLICATE"):
            self.sheet(ids=[
                ["Mail UID"],["inbox:1"],["inbox:2"],["inbox:1"],["inbox:4"]])

    def test_success_is_not_misreported_as_full_backfill(self):
        total,states=self.sheet()
        row=m.health_record("success",total,states,"2026-10-30 18:00:00 KST")
        self.assertEqual(row[2],"BACKFILL_ACTIVE")
        self.assertIn("backfill=INCOMPLETE",row[3])
        self.assertIn("original_no_text=1",row[3])
        failure=m.health_record("failure",total,states,"2026-10-30 18:01:00 KST")
        self.assertEqual(failure[2],"FAIL_BODY_WORKFLOW")

    def test_update_existing_health_row_does_not_change_other_rows(self):
        original=[
            m.HEADER[:],
            ["CSS Mail","2026-10-30 17:00:00 KST","PASS","source healthy"],
            ["CSS Mail Body","2026-10-30 17:00:00 KST","BACKFILL_ACTIVE","older"],
            ["Revenue Lifecycle","2026-10-30 17:00:00 KST","FAIL","source pending"]]
        before=[row[:] for row in original]
        record=m.health_record("success",4,self.sheet()[1],
                               "2026-10-30 18:00:00 KST")

        def api(_s,method,url,**args):
            if method!="PUT" or "A3%3AD3" not in url:
                raise AssertionError((method,url))
            original[2]=args["json"]["values"][0]
            return {}
        with patch.object(m,"read",return_value=original), \
             patch.object(src,"api",side_effect=api,create=True):
            m.publish(object(),record)
        self.assertEqual(original[2],record)
        self.assertEqual(original[1],before[1])
        self.assertEqual(original[3],before[3])

    def test_github_job_publishes_health_after_body_action(self):
        yaml=(Path(__file__).resolve().parents[2]/
              ".github/workflows/css-web-body-sync.yml").read_text()
        self.assertIn("CSS_BODY_STEP_OUTCOME: "+"$"+"{{ steps.body.outcome }}",yaml)
        self.assertIn("if: always()",yaml)
        self.assertIn("id: body",yaml)


if __name__=="__main__":
    unittest.main()
