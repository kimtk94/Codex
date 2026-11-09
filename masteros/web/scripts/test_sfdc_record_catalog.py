import unittest
from sfdc_record_catalog import check, parse_money, parse_us_date, rec_id, find_href

class CatalogValidationTests(unittest.TestCase):
    def test_query_validation(self):
        self.assertEqual(check({"mode":"list","resource":"lead","query":"김지훈"})["resource"],"lead")
        with self.assertRaisesRegex(ValueError,"INVALID_SEARCH"):
            check({"mode":"list","resource":"lead","query":"x"*101})
        with self.assertRaisesRegex(ValueError,"INVALID_OPERATION"):
            check({"mode":"list","resource":"user","query":""})
    def test_ids(self):
        self.assertTrue(rec_id("006000000000000AAA","006"))
        self.assertFalse(rec_id("00Q000000000000AAA","006"))
        self.assertFalse(rec_id("not-id","00Q"))
    def test_link(self):
        x=find_href([{"href":"/lightning/r/Contact/003TK00001L2RfnYAF/view","text":"Kim"}],"003")
        self.assertEqual(x["id"],"003TK00001L2RfnYAF")
    def test_numeric(self):
        self.assertEqual(parse_money("KRW 8,400,000.00"),8400000)
        self.assertEqual(parse_us_date("9/29/2026"),"2026-09-29")

if __name__=="__main__":unittest.main()
