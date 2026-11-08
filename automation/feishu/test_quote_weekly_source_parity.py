#!/usr/bin/env python3
"""Offline evidence-only Quote count regression suite."""
import unittest
from quote_weekly_source_parity import audit, HEAD_WEEK, HEAD_APPROVAL

def week(start,end,count):
    return [start,end,"FRI_THU_CSS_EXISTING","0","0","0",count,"0"]
def approval(week,number):
    return ["2026-10-31 10:00:00","AMEA2026103101",
            "QID-2026-10-31-000001",number,"APPROVED_TEXT",
            week+" ~ 2026-11-05"]

class WeeklyCoverageTests(unittest.TestCase):
    def setup_rows(self):
        weekly=[HEAD_WEEK,week("2026-10-30","2026-11-05","2"),
                week("2026-10-23","2026-10-29","")]
        approved=[HEAD_APPROVAL,approval("2026-10-30","a0P-1"),
                  approval("2026-10-30","a0P-2"),
                  approval("2026-10-30","a0P-2")]
        return weekly,approved

    def test_exact_evidence_and_unknown_not_zero(self):
        weekly,approved=self.setup_rows()
        result=audit(weekly,approved)
        self.assertEqual(result["weekly_source_rows"],2)
        self.assertEqual(result["verified_weeks"],1)
        self.assertEqual(result["coverage_gaps"],1)
        self.assertEqual(result["source_conflicts"],0)
        self.assertEqual(result["source_approved_sum"],2)
        self.assertEqual(result["immutable_approval_sum"],2)
        self.assertEqual(result["gap_weeks"],["2026-10-23"])
        unknown=next(x for x in result["weeks"]
                     if x["week_start"]=="2026-10-23")
        self.assertIsNone(unknown["source_approved_count"])
        self.assertTrue(result["zero_is_not_imputed"])

    def test_zero_must_be_explicit_in_source(self):
        weekly,approved=self.setup_rows()
        weekly[2][6]="0"
        result=audit(weekly,approved)
        self.assertEqual(result["verified_weeks"],2)
        self.assertEqual(result["coverage_gaps"],0)

    def test_count_disagreement_is_conflict(self):
        weekly,approved=self.setup_rows()
        weekly[1][6]="1"
        result=audit(weekly,approved)
        self.assertEqual(result["source_conflicts"],1)
        self.assertEqual(result["weeks"][0]["status"],"WEEKLY_COUNT_SOURCE_CONFLICT")

    def test_missing_count_with_positive_evidence_is_not_zero(self):
        weekly,approved=self.setup_rows()
        approved.append(["2026-10-24","AMEA2026102401","QID","a0P-3",
                         "APPROVED_TEXT","2026-10-23 ~ 2026-10-29"])
        result=audit(weekly,approved)
        self.assertEqual(result["source_conflicts"],1)
        self.assertEqual(result["weeks"][1]["status"],
                         "MISSING_COUNT_WITH_APPROVAL_EVIDENCE")
        self.assertIsNone(result["weeks"][1]["source_approved_count"])

    def test_duplicate_week_fails(self):
        weekly,approved=self.setup_rows()
        weekly.append(weekly[1][:])
        with self.assertRaisesRegex(RuntimeError,"DUPLICATE_WEEKLY_SOURCE_WEEK"):
            audit(weekly,approved)

    def test_approval_outside_week_fails(self):
        weekly,approved=self.setup_rows()
        approved[1][5]="2026-10-29 ~ 2026-11-05"
        with self.assertRaisesRegex(RuntimeError,"APPROVAL_WEEK_RANGE_NOT_FRIDAY_THURSDAY"):
            audit(weekly,approved)

if __name__=="__main__":
    unittest.main()
