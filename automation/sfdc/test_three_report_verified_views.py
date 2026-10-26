#!/usr/bin/env python3
import sys
import pathlib
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from three_report_verified_views import build

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
