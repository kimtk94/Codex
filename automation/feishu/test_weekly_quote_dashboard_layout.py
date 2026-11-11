#!/usr/bin/env python3
"""Synthetic-only tests for Feishu Weekly Quote dashboard layout."""
import unittest
from unittest import mock
import weekly_quote_dashboard_layout as s

def sample(pos=None):
    return {"items":[{"name":name,"type":"combo" if i==0 else "text",
                      "block_id":"cht"+str(i)+"98765",
                      "position":(pos or s.POSITIONS)[name]}
                     for i,name in enumerate(s.ORDER)]

class TestWeeklyQuoteLayout(unittest.TestCase):
    def test_graph_then_table_then_notes_full_width(self):
        self.assertTrue(s.valid_layout())
        self.assertEqual(s.ORDER,(s.CHART_NAME,s.BLOCK_NAME,s.NOTE_NAME))
        self.assertEqual([(s.POSITIONS[n]["x"],s.POSITIONS[n]["w"]) for n in s.ORDER],[(0,12)]*3)
        self.assertLess(s.POSITIONS[s.CHART_NAME]["y"],s.POSITIONS[s.BLOCK_NAME]["y"])
        self.assertLess(s.POSITIONS[s.BLOCK_NAME]["y"],s.POSITIONS[s.NOTE_NAME]["y"])
    def test_existing_layout_no_write(self):
        with mock.patch.object(s,"cli",return_value=sample()) as cli:
            self.assertEqual(s.apply_layout("blkDemo"),0)
            self.assertEqual(cli.call_count,1)
    def test_stacked_layout_write_and_readback(self):
        old={k:{"x":i*4,"y":0,"w":4,"h":8} for i,k in enumerate(s.ORDER)}
        with mock.patch.object(s,"cli",side_effect=[sample(old),sample()]) as cli:
            self.assertEqual(s.apply_layout("blkDemo"),3)
            updates=[x for x in cli.call_args_list if x.args[0]=="+dashboard-block-update"]
            self.assertEqual(len(updates),6)
            self.assertEqual(cli.call_count,8)
    def test_duplicate_or_extra_blocks_refused(self):
        rows=sample()["items"]
        with self.assertRaisesRegex(RuntimeError,"DUPLICATE"):
            s.inspect({"items":rows+[rows[0]]})
        with self.assertRaisesRegex(RuntimeError,"UNEXPECTED_WIDGET_SET"):
            s.inspect({"items":rows+[{"name":"Unrelated","block_id":"chtMisc001"}]})
    def test_overlap_refused(self):
        invalid={k:dict(v) for k,v in s.POSITIONS.items()}
        invalid[s.BLOCK_NAME]["y"]=0
        with self.assertRaisesRegex(RuntimeError,"OVERLAP"):
            s.valid_layout(invalid)

if __name__=="__main__":
    unittest.main()
