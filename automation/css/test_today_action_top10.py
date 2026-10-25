import unittest
from datetime import date
from today_action_top10 import build


class TodayActionTests(unittest.TestCase):
    TODAY=date(2026,10,25)

    def test_done_and_contacted_are_suppressed(self):
        css=[{"Record ID":"ACT-1","Original Status":"DONE","Priority":"P0"},
             {"Record ID":"ACT-2","Original Status":"미검토","Priority":"P0",
              "Freshness":"VERIFY_CURRENT_RESOLUTION"}]
        leads=[{"Lead ID":"Lead-1","Sent Mail Count":"2","Description Class":"DESCRIPTION_PRESENT"},
               {"Lead ID":"Lead-2","Decision Effective":"DONE"},
               {"Lead ID":"Lead-3","Description Class":"DESCRIPTION_PRESENT",
                "Description Intent":"SERVICE_INQUIRY","Due Date":"2026-10-20"}]
        result,total=build(css,leads,self.TODAY)
        self.assertEqual(total,2)
        self.assertEqual({x["Record ID"] for x in result},{"ACT-2","Lead-3"})
        self.assertEqual(result[0]["Verification"],"VERIFY_CURRENT_RESOLUTION")

    def test_source_specific_duplicate_reduction(self):
        css=[{"Record ID":"ACT-1","Source":"CSS","Priority":"P0"},
             {"Record ID":"ACT-1","Source":"CSS","Priority":"P1"},
             {"Record ID":"ACT-1","Source":"SFDC","Priority":"P2"}]
        _,count=build(css,[],self.TODAY)
        self.assertEqual(count,2)

    def test_top_limit_and_stability(self):
        css=[{"Record ID":f"ACT-{i}","Priority":"P0"} for i in range(5)]
        result,total=build(css,[],self.TODAY,limit=3)
        self.assertEqual((total,len(result)),(5,3))
        self.assertEqual([r["Rank"] for r in result],[1,2,3])


if __name__=="__main__":
    unittest.main()
