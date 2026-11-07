#!/usr/bin/env python3
"""Exactly one native Quote chart: count and source-verified K USD, four weeks."""
import unittest
from native_dashboard_cli import (
    BLOCKS, QUOTE_CHART_NAME, QUOTE_COMBO_ALIASES,
    LEGACY_QUOTE_REMOVALS, legacy_dashboard_block
)

class QuoteComboTests(unittest.TestCase):
    def test_one_combo_for_last_four_completed_weeks(self):
        combos=[(name,conf) for name,typ,conf in BLOCKS if typ=="combo"]
        self.assertEqual(len(combos),1)
        name,config=combos[0]
        self.assertEqual(name,QUOTE_CHART_NAME)
        self.assertEqual(config["table_name"],"Weekly Quote KPI")
        self.assertEqual(config["group_by"],[{
            "field_name":"Chart Week Label",
            "mode":"integrated",
            "sort":{"type":"group","order":"asc"},
        }])
        self.assertEqual(config["filter"],{"conjunction":"and","conditions":[{
            "field_name":"Chart Window","operator":"is",
            "value":"RECENT_4_COMPLETED",
        }]})
        self.assertEqual(config["series"],[
            {"field_name":"Approved Quote Count","rollup":"SUM"},
            {"field_name":"Verified Quote Value K USD","rollup":"SUM"},
        ])
    def test_no_duplicate_weekly_count_or_krw_quote_chart(self):
        blocknames={n for n,_,_ in BLOCKS}
        self.assertNotIn("Weekly 승인 Quote",blocknames)
        self.assertNotIn("KOREA · Quote Count / Value (M KRW)",blocknames)
        self.assertNotIn("Quote 금액 검증 기준",blocknames)
        self.assertTrue({"Weekly 승인 Quote","KOREA · Quote Count / Value (M KRW)",
                         "Quote 금액 검증 기준"}.issubset({
                             name for name,kind in LEGACY_QUOTE_REMOVALS}))
        self.assertIn("KOREA · Quote Count / Value (K USD)",QUOTE_COMBO_ALIASES)
        self.assertEqual(len([x for x in BLOCKS if x[1]=="column" and
                              x[2].get("table_name")=="Weekly Quote KPI"]),0)
        monthly=next(c for name,kind,c in BLOCKS if name.startswith("월별 Revenue"))
        self.assertEqual(monthly["series"][0]["field_name"],"Net Revenue M KRW")
    def test_count_cards_still_render_integer(self):
        for name,kind,config in BLOCKS:
            if kind=="statistics" and config.get("count_all"):
                self.assertEqual(config["number_format"],
                    {"formatName":"digital","precision":0},name)
    def test_deletion_only_verifiable_named_dashboard_blocks(self):
        cases={"items":[
          {"name":"Weekly 승인 Quote","type":"column","block_id":"chtOldCount"},
          {"name":"KOREA · Quote Count / Value (M KRW)",
           "type":"combo","block_id":"chtOldKrw"},
          {"name":QUOTE_CHART_NAME,"type":"combo","block_id":"chtKeep"},
          {"name":"Monthly Revenue","type":"line","block_id":"chtRevenue"},
        ]}
        self.assertEqual(legacy_dashboard_block(cases,"Weekly 승인 Quote",
                         "column"),"chtOldCount")
        self.assertEqual(legacy_dashboard_block(cases,QUOTE_CHART_NAME,
                         "combo"),"chtKeep")
        with self.assertRaisesRegex(RuntimeError,"TYPE_MISMATCH"):
            legacy_dashboard_block(cases,"Monthly Revenue","combo")
if __name__=="__main__":unittest.main()
