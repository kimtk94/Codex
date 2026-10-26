import unittest
from catalog_reuse import dedupe, search, make_draft
class CatalogTests(unittest.TestCase):
    def test_dedup_and_reuse(self):
        rows=[{"Opportunity ID":"Opp-1","Account Name":"Yonsei University","Main Contact":"Prof Kim","Opportunity Name":"mRNA-Seq","Account ID":"001","Main Contact CMS ID":"CP1"},
              {"Opportunity ID":"Opp-1","Account Name":"duplicate"},
              {"Opportunity ID":"Opp-2","Account Name":"Ewha University","Opportunity Name":"WGS"}]
        self.assertEqual(len(dedupe(rows)),2)
        match=search(rows,account="Yonsei",service="mRNA")[0]
        self.assertEqual(match["opportunity_id"],"Opp-1")
        draft=make_draft(match)
        self.assertEqual(draft["Amount"],"")
        self.assertFalse(draft["salesforce_save_performed"])
    def test_empty_query(self):
        self.assertEqual(search([{"Opportunity ID":"a"}],account="Yonsei"),[])
if __name__=="__main__":
    unittest.main()
