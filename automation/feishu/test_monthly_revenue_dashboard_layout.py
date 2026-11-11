#!/usr/bin/env python3
import unittest
from unittest import mock
import monthly_revenue_dashboard_layout as s

def payload(positions=None):
    return {"items":[{"name":n,"block_id":"cht"+str(i)+"123",
                      "type":["line","ranking","text"][i],
                      "position":(positions or s.POSITIONS)[n]}
                     for i,n in enumerate(s.ORDER)]}

class TestMonthlyRevenueLayout(unittest.TestCase):
    def test_monthly_list_is_under_real_chart(self):
        s.validate()
        self.assertEqual(s.ORDER,(s.CHART,s.MONTHLY_LIST_NAME,s.NOTE))
        self.assertLess(s.POSITIONS[s.CHART]["y"],s.POSITIONS[s.MONTHLY_LIST_NAME]["y"])
        self.assertLess(s.POSITIONS[s.MONTHLY_LIST_NAME]["y"],s.POSITIONS[s.NOTE]["y"])
    def test_idempotent(self):
        with mock.patch.object(s,"cli",return_value=payload()) as fn:
            s.apply("blkMonthly","apply")
            self.assertEqual(fn.call_count,1)
    def test_reposition_only_and_readback(self):
        old={n:{"x":i*4,"y":0,"w":4,"h":9} for i,n in enumerate(s.ORDER)}
        with mock.patch.object(s,"cli",side_effect=[payload(old)]+[{}]*6+[payload()]) as fn:
            s.apply("blkMonthly","apply")
            self.assertEqual(len([x for x in fn.call_args_list
                                  if x.args[0]=="+dashboard-block-update"]),6)
    def test_wrong_ranking_type_blocks(self):
        data=payload()
        data["items"][1]["type"]="text"
        with self.assertRaisesRegex(RuntimeError,"TYPE_MISMATCH"):
            s.inspect(data)
    def test_overlap_is_rejected(self):
        invalid={k:dict(v) for k,v in s.POSITIONS.items()}
        invalid[s.MONTHLY_LIST_NAME]["y"]=0
        with self.assertRaisesRegex(RuntimeError,"OVERLAP"):
            s.validate(invalid)
if __name__=="__main__":
    unittest.main()
