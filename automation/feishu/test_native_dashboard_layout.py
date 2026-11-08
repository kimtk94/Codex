#!/usr/bin/env python3
"""Dashboard ordering is deterministic and never touches Base customer records."""
import unittest
from unittest import mock
import native_dashboard_cli as m

class LayoutTests(unittest.TestCase):
    def _items(self):
        return {"items":[{"name":name,
                          "type":kind,
                          "block_id":"cht"+str(i+101),
                          "position":dict(m.BLOCK_POSITIONS[name])}
                         for i,(name,kind,_) in enumerate(m.BLOCKS)]}

    def test_every_block_is_in_the_grid_without_overlap(self):
        self.assertTrue(m.validate_dashboard_layout())
        self.assertEqual(len(m.BLOCK_POSITIONS),len(m.BLOCKS))
        used=set()
        for item in m.BLOCK_POSITIONS.values():
            for x in range(item["x"],item["x"]+item["w"]):
                for y in range(item["y"],item["y"]+item["h"]):
                    self.assertNotIn((x,y),used)
                    used.add((x,y))

    def test_provenance_before_project_then_quote_then_revenue(self):
        names=sorted(m.BLOCK_POSITIONS,
                     key=lambda name:(m.BLOCK_POSITIONS[name]["y"],
                                      m.BLOCK_POSITIONS[name]["x"]))
        self.assertEqual(names[0],"운영 안내")
        self.assertLess(names.index("전체 프로젝트"),names.index("프로젝트 공정별 현황"))
        self.assertLess(names.index("프로젝트 공정별 현황"),names.index(m.QUOTE_CHART_NAME))
        self.assertLess(names.index(m.QUOTE_CHART_NAME),
                        names.index("월별 Revenue · VAT 제외 · M KRW (K USD)"))

    def test_exact_existing_layout_makes_no_mutating_calls(self):
        with mock.patch.object(m,"cli") as call:
            m.apply_dashboard_layout("blkTest",self._items())
        call.assert_not_called()

    def test_missing_block_fails_closed_before_reposition(self):
        data=self._items()
        data["items"].pop()
        with mock.patch.object(m,"cli") as call:
            with self.assertRaisesRegex(RuntimeError,"BLOCKS_MISSING"):
                m.apply_dashboard_layout("blkTest",data)
        call.assert_not_called()

    def test_reposition_moves_known_blocks_only_no_deletions(self):
        data=self._items()
        data["items"][0]["position"]["y"]=50
        with mock.patch.object(m,"cli",return_value=self._items()) as call:
            m.apply_dashboard_layout("blkTest",data)
        self.assertEqual(call.call_count,2*len(m.BLOCKS)+1)
        calls=[p.args for p in call.call_args_list]
        self.assertTrue(all(p[0] in {"+dashboard-block-update",
                                     "+dashboard-block-list"} for p in calls))
        self.assertNotIn("+dashboard-block-delete",str(calls))
        self.assertNotIn("+record-update",str(calls))

    def test_duplicate_and_overlap_are_rejected(self):
        positions={name:dict(pos) for name,pos in m.BLOCK_POSITIONS.items()}
        positions["SIF 상태"]=dict(positions["프로젝트 공정별 현황"])
        with self.assertRaisesRegex(RuntimeError,"OVERLAP"):
            m.validate_dashboard_layout(positions=positions)

if __name__=="__main__":
    unittest.main()
