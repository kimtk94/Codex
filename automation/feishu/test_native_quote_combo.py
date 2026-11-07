#!/usr/bin/env python3
"""One Feishu Quote visual: count and verified K USD, latest four weeks."""
import unittest
from native_dashboard_cli import BLOCKS,LEGACY_QUOTE_DUPLICATES,LEGACY_COMBO_NAMES

class QuoteComboTests(unittest.TestCase):
    def test_exactly_one_kusd_combo_with_count_and_value(self):
        visual=[(name,typ,config) for name,typ,config in BLOCKS
                if "Quote" in name and typ in {"column","combo"}]
        self.assertEqual(len(visual),1)
        name,typ,config=visual[0]
        self.assertEqual(name,"KOREA · Quote Count / Value (K USD)")
        self.assertEqual(typ,"combo")
        self.assertEqual(config["table_name"],"Weekly Quote KPI")
        self.assertEqual(config["group_by"],[{
            "field_name":"Chart Week Label",
            "mode":"integrated",
            "sort":{"type":"group","order":"asc"},
        }])
        self.assertEqual(config["filter"],{
            "conjunction":"and",
            "conditions":[{"field_name":"Chart Window","operator":"is",
                           "value":"RECENT_4_COMPLETED"}],
        })
        self.assertEqual(config["series"],[
            {"field_name":"Approved Quote Count","rollup":"SUM"},
            {"field_name":"Verified Quote Value K USD","rollup":"SUM"},
        ])

    def test_old_weekly_and_krw_visuals_are_deletion_targets_not_sources(self):
        self.assertEqual(LEGACY_QUOTE_DUPLICATES["Weekly 승인 Quote"],"column")
        self.assertEqual(LEGACY_QUOTE_DUPLICATES[
            "KOREA · Quote Count / Value (M KRW)"],"combo")
        self.assertEqual(LEGACY_COMBO_NAMES[
            "KOREA · Quote Count / Value (K USD)"],
            "Weekly Quote · 건수 + 검증금액 K USD")
        self.assertNotIn("KOREA · Quote Count / Value (K USD)",
                         LEGACY_QUOTE_DUPLICATES)

    def test_numeric_and_revenue_conventions_remain_intact(self):
        monthly=next(c for name,kind,c in BLOCKS if name.startswith("월별 Revenue"))
        self.assertEqual(monthly["series"][0]["field_name"],"Net Revenue M KRW")
        for name,kind,c in BLOCKS:
            if kind=="statistics" and c.get("count_all"):
                self.assertEqual(c["number_format"],
                                 {"formatName":"digital","precision":0})

    def test_note_explains_source_restrictions_and_dates(self):
        note=next(c["text"] for n,k,c in BLOCKS if n=="Quote 금액 검증 기준")
        self.assertIn("MM/DD",note)
        self.assertIn("진행 중인 주는 제외",note)
        self.assertIn("SFDC Quote ID",note)
        self.assertIn("미확인 금액",note)
        self.assertIn("K USD",note)
if __name__=="__main__":unittest.main()
