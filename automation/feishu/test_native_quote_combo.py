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
                             {"type":"view","order":"asc"})
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
                                 "Verified Quote Value M KRW FX"})
    def test_amount_series_use_display_units_only(self):
        combos=[(name,config) for name,kind,config in BLOCKS if kind=="combo"]
        krw=next(c for name,c in combos if "(M KRW)" in name)
        usd=next(c for name,c in combos if "(K USD)" in name)
        self.assertEqual(krw["series"][1]["field_name"],
                         "Verified Quote Value M KRW FX")
        self.assertEqual(usd["series"][1]["field_name"],
                         "Verified Quote Value K USD")
        monthly=next(c for name,kind,c in BLOCKS if name.startswith("월별 Revenue"))
        self.assertEqual(monthly["series"],[
            {"field_name":"Net Revenue M KRW","rollup":"SUM"},
            {"field_name":"Net Revenue K USD","rollup":"SUM"},
        ])
        titles=[name for name,_,_ in BLOCKS if name=="월별 Revenue · VAT 제외 · M KRW (K USD)"]
        self.assertEqual(len(titles),1)
        for name,kind,c in BLOCKS:
            if kind=="statistics" and c.get("count_all"):
                self.assertEqual(c["number_format"],{"formatName":"digital","precision":0})
        self.assertFalse(any("KRW FX"==c["series"][1]["field_name"]
            for _,c in combos))
    def test_count_and_amount_are_not_mislabeled_final_revenue(self):
        texts=[x[2]["text"] for x in BLOCKS if x[1]=="text"]
        self.assertTrue(any("금액 미확인" in x for x in texts))
        self.assertTrue(any("승인 견적" in x for x in texts))
if __name__=="__main__":unittest.main()
