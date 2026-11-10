#!/usr/bin/env python3
"""Offline tests: no QQ credentials or CRM writes."""
import datetime as dt
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import css_mail_local as m

NOW=dt.datetime(2026,11,10,9,tzinfo=dt.timezone.utc)
OWNER="taehoon.kim@novogene.com"
Q_HEAD=["Priority","Waiting Days","Last Customer Mail (KST)","Customer Email",
"Subject / Thread","Project IDs","Reply Evidence","Suggested Action",
"Assessment","Thread Identity","Mail UID","Last Possible Outbound (KST)",
"To","Cc","Canonical Ingest Key","Source Fetched (UTC)",
"Checked (UTC)","Source Coverage","Manual Decision Source"]+m.EDIT_HEAD
L_HEAD=["Lead ID","Institution","Lead Name","Lead Email","Lead Created",
"Lead Status","Lead Owner","Personal Mail Evidence","Sent After Lead Count",
"First Sent After Lead (KST)","Last Sent After Lead (KST)","Sent Ever Count",
"First Sent Ever (KST)","Last Sent Ever (KST)","Direct To Count","CC Copy Count",
"Latest Message-ID Evidence","Latest QQ Source Checked (KST)",
"Lead Source Checked (KST)","Suggested Review","Snapshot (KST)"]


def mail(key="INBOX|177|901",to="other@novogene.com",cc=OWNER):
    return ["P0","7","2026-11-03 13:00","person@uni.ac.kr",
            "mRNA service","","NO_REPLY_EVIDENCE","","CANDIDATE_NOT_CONFIRMED",
            "<thread@uni.ac.kr>","inbox:901","",to,cc,key,
            "2026-11-09T15:00:00+00:00","2026-11-10T08:00:00+00:00",
            "STAGING_METADATA_PARTIAL_HISTORY","","CC_ONLY","","","","REVIEW"]


def sheet_data(mailrows=None,dec=None,rules=None):
    return ([Q_HEAD]+(mailrows if mailrows is not None else [mail()]),
            [m.MAIL_DECISION_HEAD]+(dec or []),
            [m.RULE_HEAD]+(rules or []),
            [["Metric","Value","Explanation"],["Snapshot UTC","2026-11-10T08:30:00+00:00",""]],
            [L_HEAD,["Lead-1","University","Researcher","person@uni.ac.kr",
                "11/10/2026","Open","Owner","NO_PERSONAL_OUTBOUND_EVIDENCE",
                "0","","","0","","","0","0","","2026-11-10T08:30:00+09:00",
                "2026-11-10 08:30 KST","","2026-11-10T17:00:00+09:00"]])

class LocalConsoleTests(unittest.TestCase):
    def test_mail_and_lead_snapshot(self):
        payload=m.snapshot(*sheet_data(),OWNER,NOW)
        self.assertEqual(payload["mailCount"],1)
        self.assertEqual(payload["leadCount"],1)
        self.assertEqual(payload["mail"][0]["role"],"CC_ONLY")
        self.assertEqual(payload["mailSourceStatus"],"FRESH")

    def test_to_addressee_prevents_cc_rule(self):
        direct=mail(to=OWNER,cc="shared@novogene.com")
        cc=mail(key="INBOX|177|902")
        rule=["TRUE","SENDER_ADDRESS","person@uni.ac.kr","OWNER_CC_ONLY","SKIP","","",""]
        payload=m.snapshot(*sheet_data([direct,cc],rules=[rule]),OWNER,NOW)
        self.assertEqual(payload["mailCount"],1)
        self.assertEqual(payload["mail"][0]["role"],"TO")
        self.assertEqual(payload["skipped"]["cc_sender"],1)

    def test_active_manual_skip_and_restore_visibility(self):
        decision=["TRUE","SKIP_MAIL","INBOX|177|901","inbox:901","person@uni.ac.kr",
                  "mRNA service","","2026-11-10T09:00:00+00:00"]
        result=m.snapshot(*sheet_data(dec=[decision]),OWNER,NOW)
        self.assertEqual(result["mailCount"],0)
        self.assertEqual(len(result["skippedMails"]),1)

    def test_unknown_action_rejected(self):
        with self.assertRaises(ValueError):
            m.validate_request({"mode":"decision","action":"DELETE_MAIL"})

    def test_missing_credentials_not_silently_fresh(self):
        bad=sheet_data()
        bad[3][1][1]="2026-10-01T00:00:00+00:00"
        result=m.snapshot(*bad,OWNER,NOW)
        self.assertEqual(result["mailSourceStatus"],"STALE")

    def test_restore_requires_no_current_queue_entry(self):
        with patch.object(m,"load",return_value=sheet_data(mailrows=[],dec=[
            ["TRUE","SKIP_MAIL","INBOX|177|901","inbox:901","person@uni.ac.kr",
             "mRNA service","","2026-11-10T09:00:00+00:00"]
        ])),patch.object(m,"fetch",return_value=[["TRUE","SKIP_MAIL","INBOX|177|901"]]),\
        patch.object(m,"update_cell") as update:
            result=m.apply_action(object(),{"action":"RESTORE_MAIL","key":"INBOX|177|901"},OWNER)
        self.assertEqual(result["result"],"MAIL_RESTORED")
        update.assert_called_once()

    def test_stale_mail_prevents_post(self):
        data=sheet_data()
        data[3][1][1]="2026-10-01T00:00:00+00:00"
        with patch.object(m,"load",return_value=data):
            with self.assertRaisesRegex(ValueError,"MAIL_SNAPSHOT_STALE"):
                m.apply_action(object(),{"action":"SKIP_MAIL","key":"INBOX|177|901"},OWNER)

if __name__=="__main__":
    unittest.main()
