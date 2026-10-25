import unittest
from datetime import date
from today_action_v2 import mail_rows, quote_rows, assemble


class AdaptersTests(unittest.TestCase):
    def test_mail_requires_two_days_and_no_reply(self):
        data=[
          {"Thread UID":"inbox:1","Aging Days":"0","Effective Queue":"MONITOR_0_1D"},
          {"Thread UID":"inbox:2","Aging Days":"2","Effective Queue":"REVIEW_2D"},
          {"Thread UID":"inbox:3","Aging Days":"3","Effective Queue":"REVIEW_2D","Reply Evidence":"SENT_CONFIRMED"},
          {"Thread UID":"inbox:4","Aging Days":"4","Effective Queue":"REVIEW_2D","Excluded?":"TRUE"},
        ]
        self.assertEqual([r["Record ID"] for r in mail_rows(data)],["inbox:2"])

    def test_aged_threads_and_confirmed_proxy_replies_are_not_actionable(self):
        data=[
          {"Thread UID":"inbox:old","Aging Days":"48","Effective Queue":"OVERDUE_7D"},
          {"Thread UID":"inbox:pc","Aging Days":"5","Effective Queue":"REVIEW_2D","Reply Evidence":"PC_REPLIED"},
          {"Thread UID":"inbox:ts","Aging Days":"5","Effective Queue":"REVIEW_2D","Reply Evidence":"TS_REPLIED"},
          {"Thread UID":"inbox:reviewer","Aging Days":"5","Effective Queue":"REVIEW_2D","Reviewer Mail Action":"REPLY_SENT"},
          {"Thread UID":"inbox:unclear","Aging Days":"5","Effective Queue":"REVIEW_2D","Reply Evidence":"후속조치 검토 (확정 아님)"},
        ]
        self.assertEqual([r["Record ID"] for r in mail_rows(data)],["inbox:unclear"])

    def test_invalid_and_non_action_quotes(self):
        data=[
          {"Salesforce Quote ID":"#N/A","Approval":"APPROVED","Active":"ACTIVE","Review Reason":"broken"},
          {"Salesforce Quote ID":"q1","Approval":"APPROVED","Active":"ACTIVE","Relation Status":"MATCHED"},
          {"Salesforce Quote ID":"q2","Approval":"PENDING","Active":"ACTIVE","Review Reason":"missing"},
          {"Salesforce Quote ID":"q3","Approval":"APPROVED","Active":"ACTIVE","Review Reason":"MISSING OPPO"},
        ]
        self.assertEqual([r["Record ID"] for r in quote_rows(data)],["q3"])

    def test_cross_source_rank_and_dedup(self):
        mail=[{"Thread UID":"inbox:2","Aging Days":"2","Effective Queue":"REVIEW_2D"}]*2
        quote=[{"Salesforce Quote ID":"q3","Approval":"APPROVED","Active":"ACTIVE","Review Reason":"MISSING OPPO"}]
        out,count=assemble([],[],mail,quote,date(2026,10,25))
        self.assertEqual(count,2)
        self.assertEqual([r["Rank"] for r in out],[1,2])


if __name__=="__main__":
    unittest.main()
