#!/usr/bin/env python3
"""Official Feishu Combo chart must carry both count and valued Quote series."""
import unittest
from native_dashboard_cli import BLOCKS
class QuoteComboTests(unittest.TestCase):
    def test_both_native_combos_use_verified_kusd_and_krw(self):
        combos=[(name,config) for name,typ,config in BLOCKS if typ=="combo"]
        self.assertEqual(len(combos),2)
        for name,config in combos:
            self.assertEqual(config["table_name"],"Weekly Quote KPI")
            self.assertEqual(config["group_by"][0]["field_name"],"Chart Week Label")
            self.assertEqual(config["group_by"][0]["sort"],
                             {"type":"view","order":"desc"})
            self.assertEqual(config["filter"],
                {"conjunction":"and","conditions":[
                    {"field_name":"Chart Window","operator":"is",
                     "value":"RECENT_4_COMPLETED"}]})
            self.assertTrue(name.startswith("KOREA · Quote Count / Value"))
            self.assertEqual(config["series"][0],
                {"field_name":"Approved Quote Count","rollup":"SUM"})
            self.assertEqual(len(config["series"]),2)
            self.assertEqual(config["series"][1]["rollup"],"SUM")
            self.assertTrue("Quote" in name)
        fields={config["series"][1]["field_name"] for _,config in combos}
        self.assertEqual(fields,{"Verified Quote Value K USD",
                                 "Verified Quote Value KRW FX"})
    def test_count_and_amount_are_not_mislabeled_final_revenue(self):
        texts=[x[2]["text"] for x in BLOCKS if x[1]=="text"]
        self.assertTrue(any("금액 미확인" in x for x in texts))
        self.assertTrue(any("승인 견적" in x for x in texts))
if __name__=="__main__":unittest.main()
