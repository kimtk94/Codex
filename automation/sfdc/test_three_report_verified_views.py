#!/usr/bin/env python3
import sys
import pathlib
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from three_report_verified_views import build, build_review_queues

class RelationViews(unittest.TestCase):
    def test_quote_dedup_and_unlinked_review(self):
        leads=[["SFDC Lead ID","Lead Status"],["Lead-1","Qualified"]]
        opportunities=[["Opportunity ID","Opportunity Name","Account Name","Stage","Opportunity Owner","Lead Converted ID"],
                       ["Opp-A","Test opportunity","Example Univ","Proposal","Kim","Lead-1"]]
        quotes=[["SFDC Quotation ID","Opportunity ID","Quotation Product ID","Active","Total Price USD (converted)"],
                ["Q1","Opp-A","product-1","true","1500"],
                ["Q1","Opp-A","product-2","true","1500"],
                ["Q2","Opp-missing","product-3","false","300"],
                ["Q2","Opp-missing","product-4","false","300"],
                ["Q3","","product-5","false","200"]]
        good, bad=build(leads, opportunities, quotes, "2026-10-26")
        self.assertEqual(len(good)-1,1)
        self.assertEqual(len(bad)-1,2)
        self.assertEqual(good[1][0],"Q1")
        self.assertEqual(good[1][7],"MATCHED")
        self.assertEqual(good[1][10],2)
        self.assertEqual(good[1][11],2)
        self.assertEqual(good[1][12],"1500")
        self.assertEqual(bad[1][0],"Q2")
        self.assertEqual(bad[1][1],2)
    def test_open_opportunities_dedup_and_closed_excluded(self):
        verified = [["Quotation ID","Opportunity ID","Opportunity Name","Account Name",
                     "Opportunity Stage","Opportunity Owner","Lead Converted ID","Lead Match",
                     "Lead Status","Quote Active (report only)","Quote Process Rows",
                     "Quote Product IDs","Quote Total USD (unverified)","Relation State","Checked KST"]]
        def row(qid, opp, stage, active="1"):
            return [qid,opp,"Project","University",stage,"Owner","Lead-1","MATCHED",
                    "Qualified",active,2,1,"400","VERIFIED","now"]
        verified += [row("Q1","O1","Negotiation"),row("Q2","O1","Negotiation","0"),
                     row("Q3","O2","Closed Won"),row("Q4","O3","PO Received")]
        review = [["Quotation ID","Quote Process Rows","Distinct Opportunity IDs",
                  "Opportunity ID Missing Rows","Opportunity IDs Not In Export",
                  "Reason","Review State","Checked KST"],
                  ["Q5",3,0,3,0,"MISSING_OPPORTUNITY_ID","NEEDS_REVIEW","now"]]
        queue,exceptions = build_review_queues(verified,review,"now")
        self.assertEqual(len(queue)-1,2)
        self.assertEqual(len(exceptions)-1,1)
        o1 = next(r for r in queue[1:] if r[1]=="O1")
        self.assertEqual(o1[6],2)
        self.assertEqual(o1[8],1)
        self.assertIn("비활성 Quote",o1[12])
        self.assertEqual(exceptions[1][0],"P0")
        self.assertTrue(all(r[14]=="REVIEW_ONLY_NO_NEW_ACTION" for r in queue[1:]))

    def test_inconsistent_opportunity_is_review_not_duplicate(self):
        leads=[["SFDC Lead ID"],["Lead-1"]]
        opportunities=[["Opportunity ID"],["Opp-A"],["Opp-B"]]
        quotes=[["SFDC Quotation ID","Opportunity ID"],["Q1","Opp-A"],["Q1","Opp-B"]]
        good,bad=build(leads,opportunities,quotes,"now")
        self.assertEqual(len(good),1)
        self.assertEqual(len(bad),2)
        self.assertIn("MULTIPLE",bad[1][5])

if __name__ == "__main__":
    unittest.main()
