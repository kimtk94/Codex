import unittest
from datetime import date
from nba_refresh_pool import build_candidates


def personal_leads():
    rows=[]
    for i in range(450):
        rows.append({"Lead ID":f"Lead-{i}","Created Date":"2026-10-25",
                     "Email":f"lead{i}@example.com","My Mail Status":"SENT_AFTER_LEAD_CONFIRMED",
                     "Description Class":"PRESENT","Description":"RNA-seq quote request",
                     "Lead Status":"New","Opportunity ID":"",
                     "Institution":"University","Customer":"Researcher"})
    rows[1]["My Mail Status"]="NO_PERSONAL_OUTBOUND_EVIDENCE"
    rows[2]["My Mail Status"]="SENT_BEFORE_LEAD_ONLY"
    rows[2]["Description"]=""
    rows[2]["Description Class"]="MISSING"
    rows[3]["My Mail Status"]="NO_PERSONAL_OUTBOUND_EVIDENCE"
    rows[3]["Lead Status"]="Qualified"
    return rows


class PoolRefreshTests(unittest.TestCase):
    TODAY=date(2026,10,26)

    def test_source_identity_dedup_and_suppression(self):
        css=[{"Priority":"P0","Source":"CSS","Record ID":"ACT-1",
              "Original Status":"미검토","Issue / Type":"QC"},
             {"Priority":"P1","Source":"CSS","Record ID":"ACT-1",
              "Original Status":"미검토","Issue / Type":"QC"},
             {"Priority":"P0","Source":"CSS","Record ID":"ACT-2",
              "Original Status":"DONE"}]
        mail=[{"Thread UID":"inbox:1","Aging Days":"3",
               "Effective Queue":"REVIEW_2D","Sender Email":"researcher@example.com"},
              {"Thread UID":"inbox:2","Aging Days":"0","Effective Queue":"MONITOR_0_1D"}]
        rows=build_candidates(css,personal_leads(),mail,self.TODAY)
        self.assertEqual({r[4] for r in rows},{"ACT-1","Lead-1","Lead-2","inbox:1"})
        self.assertEqual(sorted(r[0] for r in rows),[1,2,3,4])
        self.assertTrue(all(len(r)==14 for r in rows))

    def test_confirmed_personal_sent_lead_excluded(self):
        rows=build_candidates([],personal_leads(),[],self.TODAY)
        self.assertEqual({r[4] for r in rows},{"Lead-1","Lead-2"})
        self.assertTrue(all(r[11]!="NEEDS_MAIL_VERIFICATION" for r in rows))

    def test_prior_only_cannot_be_marked_first_contact(self):
        rows=build_candidates([],personal_leads(),[],self.TODAY)
        record=next(r for r in rows if r[4]=="Lead-2")
        self.assertEqual(record[11],"SENT_BEFORE_LEAD_ONLY")

    def test_guard_exists_for_sent_lead_reentry(self):
        from pathlib import Path
        source = Path("nba_refresh_pool.py").read_text(encoding="utf-8")
        self.assertIn("Confirmed-sent Leads leaked into NBA candidates",source)

    def test_empty_source_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"incomplete"):
            build_candidates([],[],[],self.TODAY)


if __name__=="__main__":
    unittest.main()
