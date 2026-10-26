import unittest
from datetime import date
from nba_refresh_pool import build_candidates


class PoolRefreshTests(unittest.TestCase):
    TODAY=date(2026,10,26)

    def test_source_identity_dedup_and_suppression(self):
        css=[{"Priority":"P0","Source":"CSS","Record ID":"ACT-1",
              "Original Status":"미검토","Issue / Type":"QC"},
             {"Priority":"P1","Source":"CSS","Record ID":"ACT-1",
              "Original Status":"미검토","Issue / Type":"QC"},
             {"Priority":"P0","Source":"CSS","Record ID":"ACT-2",
              "Original Status":"DONE"}]
        leads=[{"Lead ID":"Lead-1","Description Class":"DESCRIPTION_PRESENT",
                "Description Intent":"SERVICE_INQUIRY","Due Date":"2026-10-25"},
               {"Lead ID":"Lead-2","Sent Mail Count":"2"}]
        mail=[{"Thread UID":"inbox:1","Aging Days":"3",
               "Effective Queue":"REVIEW_2D","Sender Email":"researcher@example.com"},
              {"Thread UID":"inbox:2","Aging Days":"0","Effective Queue":"MONITOR_0_1D"}]
        rows=build_candidates(css,leads,mail,self.TODAY)
        self.assertEqual({r[4] for r in rows},{"ACT-1","Lead-1","inbox:1"})
        self.assertEqual(sorted(r[0] for r in rows),[1,2,3])
        self.assertTrue(all(len(r)==14 for r in rows))

    def test_confirmed_sent_lead_excluded(self):
        lead = {'Lead ID':'L-1','Sent Mail Status':'SENT_CONFIRMED','Sent Mail Count':'1'}
        self.assertEqual(build_candidates([], [lead], [], self.TODAY), [])

    def test_guard_exists_for_sent_lead_reentry(self):
        from pathlib import Path
        source = Path("nba_refresh_pool.py").read_text(encoding="utf-8")
        self.assertIn("Confirmed-sent Leads leaked into NBA candidates", source)

    def test_no_items(self):
        self.assertEqual(build_candidates([],[],[],self.TODAY),[])


if __name__=="__main__":
    unittest.main()
