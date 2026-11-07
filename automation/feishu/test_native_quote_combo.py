#!/usr/bin/env python3
"""The weekly Quote surface must be a single verified four-week combo."""
import unittest
from native_dashboard_cli import (
    BLOCKS, QUOTE_CHART_NAME, LEGACY_REDUNDANT_QUOTE_WIDGETS,
    LEGACY_QUOTE_ALIASES, legacy_dashboard_block,
)

class QuoteComboTests(unittest.TestCase):
    def test_one_recent_four_week_quote_chart(self):
        combos=[(name,config) for name,kind,config in BLOCKS if kind=="combo"]
        self.assertEqual(len(combos),1)
        name,cfg=combos[0]
        self.assertEqual(name,QUOTE_CHART_NAME)
        self.assertEqual(cfg["table_name"],"Weekly Quote KPI")
        self.assertEqual(cfg["series"],[
            {"field_name":"Approved Quote Count","rollup":"SUM"},
            {"field_name":"Verified Quote Value K USD","rollup":"SUM"},
        ])
        self.assertEqual(cfg["group_by"][0]["field_name"],"Chart Week Label")
        self.assertEqual(cfg["group_by"][0]["sort"],{"type":"view","order":"asc"})
        self.assertEqual(cfg["filter"]["conditions"],[
            {"field_name":"Chart Window","operator":"is",
             "value":"RECENT_4_COMPLETED"}])
        self.assertNotIn(name,LEGACY_REDUNDANT_QUOTE_WIDGETS)

    def test_monthly_revenue_dual_currency_is_preserved(self):
        monthly=next(c for name,kind,c in BLOCKS
                     if name=="월별 Revenue · VAT 제외 · M KRW (K USD)")
        self.assertEqual(monthly["series"],[
            {"field_name":"Net Revenue M KRW","rollup":"SUM"},
            {"field_name":"Net Revenue K USD","rollup":"SUM"},
        ])
        self.assertTrue(all(
            c["number_format"]=={"formatName":"digital","precision":0}
            for name,kind,c in BLOCKS
            if kind=="statistics" and c.get("count_all")))
        self.assertEqual(len([x for x in BLOCKS if x[1]=="combo"]),1)

    def test_obsolete_blocks_only_named_and_typed(self):
        self.assertIn("KOREA · Quote Count / Value (K USD)",LEGACY_QUOTE_ALIASES)
        self.assertEqual(LEGACY_REDUNDANT_QUOTE_WIDGETS["Weekly 승인 Quote"],
                         "column")
        self.assertEqual(LEGACY_REDUNDANT_QUOTE_WIDGETS[
            "KOREA · Quote Count / Value (M KRW)"],"combo")
        items={"items":[{"name":"Weekly 승인 Quote",
                         "block_id":"chtOld","type":"column"},
                        {"name":"Monthly Revenue","block_id":"chtKeep",
                         "type":"line"}]}
        self.assertEqual(legacy_dashboard_block(items,"Weekly 승인 Quote",
                                                  "column"),"chtOld")
        self.assertIsNone(legacy_dashboard_block(items,"Unknown","combo"))
        with self.assertRaisesRegex(RuntimeError,"TYPE_MISMATCH"):
            legacy_dashboard_block(items,"Weekly 승인 Quote","combo")

if __name__=="__main__":unittest.main()
