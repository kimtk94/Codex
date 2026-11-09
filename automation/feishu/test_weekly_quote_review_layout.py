#!/usr/bin/env python3
import unittest
import weekly_quote_review_layout as l

class QuoteLayoutTests(unittest.TestCase):
    def test_filters_groups_columns_sort_are_stable(self):
        self.assertEqual(l.COLUMNS[0],"Quote Name")
        self.assertEqual(l.COLUMNS[1],"합산 제외")
        self.assertIn("기관",l.COLUMNS)
        self.assertIn("참고 견적 USD",l.COLUMNS)
        self.assertNotIn("참고 금액 K USD",l.COLUMNS)
        from weekly_quote_review import VIEW_SPECS
        self.assertIn(("그래프 연동 · 최근 5주 검토","Chart Window","RECENT_4_PLUS_CURRENT"),VIEW_SPECS)
        self.assertEqual(l.group_policy("전체 Quote 목록"),
                         {"group_config":[{"field":"Week Start","desc":True}]})
        self.assertEqual(len(l.group_policy("합산 제외 · 미확인")["group_config"]),2)
        self.assertTrue(l.match_sort({"sort_config":[{"field":"fld1","desc":True}]},
                                     {"fld1":"Approval KST"}))
        self.assertTrue(l.match_group(
            {"group_config":[{"field":"fld1","desc":True}]},
            l.group_policy("전체 Quote 목록"),
            {"fld1":"Week Start"}))
        self.assertTrue(l.match_columns(
            {"visible_fields":list(l.COLUMNS)},{ }))
        self.assertFalse(l.match_columns(
            {"visible_fields":list(reversed(l.COLUMNS))},{}))

if __name__=="__main__":
    unittest.main()
