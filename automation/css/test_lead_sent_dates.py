#!/usr/bin/env python3
"""No-credential SFDC Lead sent-dates snapshot contract."""
import datetime as dt
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import lead_sent_dates as timeline
import lead_my_sent_refresh as source

NOW=dt.datetime(2026,11,10,18,tzinfo=source.KST)
EMAIL="contact@lab.org"
HEAD=["SFDC Lead ID","Email","Created Date","Lead Owner",
      "Company / Account","First Name","Last Name","Lead Status"]
RAW=[HEAD]+[
    ["Lead-"+str(i), EMAIL if i==0 else "other"+str(i)+"@lab.org",
     "2026-11-01","Kim","University","Name","Example","OPEN"] for i in range(451)
]

def sent(day, *, to=None, cc=None, mid="x"):
    return {"at":dt.datetime(2026,11,day,15,tzinfo=source.KST),
            "to":set(to or []),"cc":set(cc or []),"mid":mid,
            "source":"QQ CSS Git Ingest"}

class TimelineTests(unittest.TestCase):
    def test_first_and_last_exact_dates_and_direct_cc_counts(self):
        messages=[
            sent(2,to=[EMAIL],mid="a"),
            sent(5,cc=[EMAIL],mid="b"),
            sent(8,to=[EMAIL],mid="c"),
        ]
        with patch.object(source,"parse_messages",return_value=({EMAIL:messages},NOW)):
            matrix,stats,_=timeline.build_rows(RAW,[],[],[],[],NOW,"2026-11-10")
        row=next(x for x in matrix[1:] if x[0]=="Lead-0")
        self.assertEqual(row[7],"SENT_AFTER_LEAD_CONFIRMED")
        self.assertEqual(row[8],3)
        self.assertEqual(row[9],"2026-11-02T15:00:00+09:00")
        self.assertEqual(row[10],"2026-11-08T15:00:00+09:00")
        self.assertEqual((row[14],row[15]),(2,1))
        self.assertEqual(stats["NO_PERSONAL_OUTBOUND_EVIDENCE"],450)
        self.assertEqual(len(matrix)-1,451)

    def test_before_created_not_qualified_as_after(self):
        with patch.object(source,"parse_messages",return_value=(
            {EMAIL:[sent(1,to=[EMAIL])]},NOW
        )):
            matrix,_,_=timeline.build_rows(RAW,[],[],[],[],NOW)
        row=next(x for x in matrix[1:] if x[0]=="Lead-0")
        # Created at 2026-11-01 00:00; same day sent after creation.
        self.assertEqual(row[7],"SENT_AFTER_LEAD_CONFIRMED")

    def test_missing_email_stays_unknown(self):
        copy=[list(x) for x in RAW]
        copy[1][1]=""
        with patch.object(source,"parse_messages",return_value=({},NOW)):
            matrix,stats,_=timeline.build_rows(copy,[],[],[],[],NOW)
        row=next(x for x in matrix[1:] if x[0]=="Lead-0")
        self.assertEqual(row[7],"LEAD_EMAIL_MISSING")
        self.assertEqual(stats["LEAD_EMAIL_MISSING"],1)

    def test_prior_only_is_not_post_lead(self):
        old=sent(1,to=[EMAIL])
        copy=[list(x) for x in RAW]
        copy[1][2]="2026-11-09"
        with patch.object(source,"parse_messages",return_value=({EMAIL:[old]},NOW)):
            matrix,_,_=timeline.build_rows(copy,[],[],[],[],NOW)
        row=next(x for x in matrix[1:] if x[0]=="Lead-0")
        self.assertEqual(row[7],"SENT_BEFORE_LEAD_ONLY")
        self.assertEqual(row[8],0)
        self.assertEqual(row[11],1)

    def test_duplicate_lead_id_fails_closed(self):
        copy=[list(x) for x in RAW]
        copy[2][0]="Lead-0"
        with patch.object(source,"parse_messages",return_value=({},NOW)):
            with self.assertRaises(RuntimeError):
                timeline.build_rows(copy,[],[],[],[],NOW)

if __name__=="__main__":
    unittest.main()
