#!/usr/bin/env python3
"""No I/O; regression for one-week-shifted Quote approval counts."""
import datetime as dt
import unittest
import weekly_overview as w

class WeeklyQuoteCountTests(unittest.TestCase):
    def sample(self):
        rows=[["Approval KST","SFDC Record ID","Quotation Name"]]
        weeks=[("2026-10-09",15),("2026-10-16",12),
               ("2026-10-23",13),("2026-10-30",10)]
        for start,total in weeks:
            day=dt.date.fromisoformat(start)+dt.timedelta(days=1)
            for idx in range(total):
                sf="a0P"+f"{len(rows):012d}"
                rows.append([day.strftime("%Y-%m-%d")+" 12:30:00",
                             sf,"QID-"+day.isoformat()+"-"+str(idx)])
        return rows,dict(weeks)

    def test_fifty_approvals_map_to_correct_four_fri_thu_weeks(self):
        rows,expected=self.sample()
        by_week,created=w.approved_event_counts(rows)
        got={wk.isoformat():len(items) for wk,items in by_week.items()}
        self.assertEqual(got,expected)
        self.assertEqual({wk.isoformat():n for wk,n in created.items()},expected)
        # After published rows readback, every approval week must be exact.
        data=[["week_start","quotation_approvals"]]+[
            [week,str(count)] for week,count in expected.items()]
        self.assertEqual(w.verify_weekly_approval_readback(data,by_week),4)

    def test_one_week_shifting_must_fail_readback(self):
        rows,expected=self.sample()
        by_week,_=w.approved_event_counts(rows)
        shifted=[0,10,13,12]
        observed=[["week_start","quotation_approvals"]]+[
            [week,str(n)] for week,n in zip(sorted(expected),shifted)]
        with self.assertRaisesRegex(RuntimeError,"WEEKLY_QUOTE_APPROVAL_COUNT_READBACK_MISMATCH"):
            w.verify_weekly_approval_readback(observed,by_week)

    def test_duplicate_record_conflicting_quote_rejected(self):
        rows,_=self.sample()
        extra=list(rows[1])
        extra[2]="QID-2026-10-10-OTHER"
        rows.append(extra)
        with self.assertRaisesRegex(RuntimeError,"QUOTE_ID_APPROVAL_EVENT_CONFLICT"):
            w.approved_event_counts(rows)

    def test_missing_or_bad_approval_source_fails_closed(self):
        for rows in ([],[["approval_date","value"],["2026-10-09","1"]],
                     [["Approval KST","SFDC Record ID","Quotation Name"]]):
            with self.assertRaisesRegex(RuntimeError,"QUOTE_DEDUP_SOURCE"):
                w.approved_event_counts(rows)

    def test_friday_and_thursday_boundaries(self):
        self.assertEqual(w.week_start(dt.date(2026,10,30)),dt.date(2026,10,30))
        self.assertEqual(w.week_start(dt.date(2026,11,5)),dt.date(2026,10,30))
        self.assertEqual(w.week_start(dt.date(2026,11,6)),dt.date(2026,11,6))

if __name__=="__main__":
    unittest.main()
