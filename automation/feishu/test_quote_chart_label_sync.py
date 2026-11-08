#!/usr/bin/env python3
"""Regression tests for strict Feishu label-only metadata writes."""
import copy
import datetime as dt
import unittest
from unittest import mock

import quote_chart_label_sync as q
from qq_mail_ingest import SafeError


def fixture():
    first=dt.date(2025,1,3)
    rows=[]
    for i in range(95):
        week=(first+dt.timedelta(weeks=i)).isoformat()
        rows.append({"record_id":"rec"+str(i),
                     "fields":{
                         "Source Key":"QUOTE:"+week,
                         "Week Start":week,
                         "Week Status":"FRI_THU_IN_PROGRESS" if i==94
                                       else "FRI_THU_CSS_EXISTING",
                         "Chart Window":"RECENT_4_PLUS_CURRENT" if i>=90
                                         else "HISTORY",
                         "Chart Week Label":"OLD_LABEL",
                         "Approved Quote Count":None if i<10 else i,
                         "Calculated Quote Value K USD":3.41*i,
                         "Quote Amount Exception Count":0 if i>=10 else None,
                         "Customer Source Data":"KEEP_INTACT"}})
    return rows


class LabelSyncTests(unittest.TestCase):
    def test_friday_week_label_is_chronological_even_over_new_year(self):
        self.assertEqual(q.week_display_label("2026-12-25"),"Dec W4")
        self.assertEqual(q.week_display_label("2027-01-01"),"Jan W1")
        self.assertEqual(q.week_display_label("2026-11-06"),"Nov W2")
        self.assertEqual(q.week_display_label("2026-11-05"),"")

    def test_all_95_historical_rows_and_missing_counts_preserved(self):
        rows=fixture()
        index=q.parse_rows(rows)
        labels=q.desired_labels(index)
        self.assertEqual(len(labels),95)
        ordered=[labels["QUOTE:"+
                       (dt.date(2025,1,3)+dt.timedelta(weeks=i)).isoformat()]
                 for i in range(95)]
        self.assertEqual(ordered,sorted(ordered))
        self.assertTrue(ordered[-1].endswith("진행 중"))
        self.assertEqual(sum(x["fields"]["Approved Quote Count"] is None
                             for x in rows),10)

    def test_plan_does_not_write(self):
        rows=fixture()
        with mock.patch.object(q,"list_all",return_value=rows) as read,\
             mock.patch.object(q,"api") as api:
            changed=q.sync_labels("token","/table","plan")
        self.assertEqual(changed,95)
        api.assert_not_called()
        read.assert_called_once()

    def test_apply_updates_only_label_and_verifies_every_week(self):
        before=fixture()
        after=copy.deepcopy(before)
        desired=q.desired_labels(q.parse_rows(before))
        for row in after:
            row["fields"]["Chart Week Label"]=desired[row["fields"]["Source Key"]]
        sent=[]
        def write(verb,path,token,data,action):
            self.assertEqual(verb,"POST")
            self.assertTrue(path.endswith("/records/batch_update"))
            self.assertEqual(action,"quote_label_batch_update")
            for item in data["records"]:
                self.assertEqual(set(item["fields"]),{"Chart Week Label"})
                sent.append(item)
            return {"records":[{"record_id":x["record_id"]} for x in data["records"]]}
        with mock.patch.object(q,"list_all",side_effect=[before,after]),\
             mock.patch.object(q,"api",side_effect=write):
            changed=q.sync_labels("token","/table","apply")
        self.assertEqual(changed,95)
        self.assertEqual(len(sent),95)
        for old,new in zip(before,after):
            self.assertEqual(q.numerical_evidence(old["fields"]),
                             q.numerical_evidence(new["fields"]))

    def test_readback_detects_numeric_field_change(self):
        before=fixture()
        after=copy.deepcopy(before)
        desired=q.desired_labels(q.parse_rows(before))
        for row in after:
            row["fields"]["Chart Week Label"]=desired[row["fields"]["Source Key"]]
        after[-1]["fields"]["Approved Quote Count"]=999
        with mock.patch.object(q,"list_all",side_effect=[before,after]),\
             mock.patch.object(q,"api",
                               side_effect=lambda verb,path,token,data,action:{
                                   "records":data["records"]}):
            with self.assertRaisesRegex(SafeError,"NON_LABEL_FIELD_CHANGED"):
                q.sync_labels("token","/table","apply")

    def test_duplicate_keys_and_insufficient_historical_coverage_fail_closed(self):
        rows=fixture()
        with self.assertRaisesRegex(SafeError,"DUPLICATE"):
            q.parse_rows(rows+[copy.deepcopy(rows[0])])
        with mock.patch.object(q,"list_all",return_value=rows[:60]),\
             mock.patch.object(q,"api") as api:
            with self.assertRaisesRegex(SafeError,"HISTORICAL_COVERAGE"):
                q.sync_labels("token","/table","apply")
        api.assert_not_called()

    def test_unchanged_is_still_verified_without_writes(self):
        records=fixture()
        desired=q.desired_labels(q.parse_rows(records))
        for row in records:
            row["fields"]["Chart Week Label"]=desired[row["fields"]["Source Key"]]
        with mock.patch.object(q,"list_all",side_effect=[records,copy.deepcopy(records)]),\
             mock.patch.object(q,"api") as api:
            result=q.sync_labels("token","/table","apply")
        self.assertEqual(result,0)
        api.assert_not_called()


if __name__=="__main__":
    unittest.main()
