import unittest
from aggregate_adapter import build_aggregate

class AggregateTests(unittest.TestCase):
    def test_valid(self):
        k=[["Metric","Value","Unit"],["Invoice Revenue","1500000","KRW"]]
        s=[["Invoice Month","Service Group","Revenue KRW","Revenue K USD","Coverage","Invoice Source","Validation"],["2025-11","mRNA","1500000","1","PARTIAL_2025_BACKFILL","TAX_INVOICE","SERVICE_CLASSIFIED"]]
        data=build_aggregate(k,s,"test")
        self.assertEqual(data["revenue"]["krw"],1500000)
        self.assertEqual(data["serviceMonthly"][0]["kUsd"],1)
        self.assertIn("PARTIAL_2025_BACKFILL",data["coverage"])
    def test_requires_invoice(self):
        with self.assertRaises(ValueError):
            build_aggregate([["Metric","Value","Unit"]],[["Invoice Month","Service Group","Revenue KRW","Revenue K USD","Coverage","Invoice Source","Validation"],["2026-10","mRNA",1,1,"FULL","QUOTE","VERIFIED"]],"test")
    def test_no_data(self):
        with self.assertRaises(ValueError):
            build_aggregate([["Metric","Value","Unit"]],[["Invoice Month","Service Group","Revenue KRW","Revenue K USD","Coverage","Invoice Source","Validation"]],"test")

if __name__=="__main__":unittest.main()
