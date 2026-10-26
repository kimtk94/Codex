#!/usr/bin/env python3
import pathlib
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from three_report_mail_evidence import addresses, build, latest_events

class MailEvidenceTests(unittest.TestCase):
    def test_exact_addresses_direction_and_not_resolution(self):
        contacts={"customer@example.org", "other@example.org"}
        mail=[
            ["2026-10-20T10:00:00+09:00","Sender","taehoon.kim@novogene.com",
             "Customer <customer@example.org>","",""],
            ["2026-10-21T10:00:00+09:00","Customer","customer@example.org",
             "taehoon.kim@novogene.com","",""],
            ["2026-10-22T10:00:00+09:00","PC","masiyuan8900@novogene.com",
             "customer@example.org","",""],
            ["2026-10-23T10:00:00+09:00","Internal","another@novogene.com",
             "customer@example.org","",""],
            ["2026-10-24T10:00:00+09:00","Other","other2@example.org",
             "taehoon.kim@novogene.com","",""]
        ]
        found=latest_events(mail,contacts)
        self.assertEqual(found["customer@example.org"]["out"],2)
        self.assertEqual(found["customer@example.org"]["in"],1)
        self.assertEqual(found["other@example.org"]["out"],0)
    def test_queue_contact_evidence_is_review_only(self):
        queue=[["Opportunity ID","Institution","Stage","Owner","Quote IDs"],
               ["O1","Sample Univ","Quotation Issued","Kim","Q1 | Q2"],
               ["O2","Sample Univ","Negotiation","Kim","Q3"]]
        quotes=[["SFDC Quotation ID","Email"],["Q1","customer@example.org"],
                ["Q2","customer@example.org"],["Q3",""]]
        mail=[["2026-10-20T10:00:00+09:00","Kim",
               "taehoon.kim@novogene.com","customer@example.org",""]]
        result=build(queue,quotes,mail,"now")
        self.assertEqual(len(result)-1,2)
        self.assertEqual(result[1][6],1)
        self.assertEqual(result[1][11],"OUTBOUND_FOUND_REVIEW")
        self.assertEqual(result[2][11],"NO_QUOTE_CUSTOMER_EMAIL")
        self.assertEqual(result[1][10],"NOT_VERIFIED")
    def test_multiple_recipients_no_auto_close(self):
        queue=[["Opportunity ID","Institution","Stage","Owner","Quote IDs"],
               ["O1","Univ","Negotiation","Kim","Q1 | Q2"]]
        quotes=[["SFDC Quotation ID","Email"],["Q1","a@example.org"],
                ["Q2","b@example.org"]]
        result=build(queue,quotes,[],"now")
        self.assertEqual(result[1][5],"MULTIPLE")
        self.assertEqual(result[1][11],"MULTIPLE_CUSTOMER_EMAILS_REVIEW")

if __name__=="__main__":
    unittest.main()
