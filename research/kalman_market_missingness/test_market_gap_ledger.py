import unittest
from datetime import date, timedelta

from test_data_catalog import plan
from market_gap_ledger import build_ledger


def inputs():
    p = plan()
    overview = {"asof_date": "2026-11-20", "source_claimed_asof": "2026-10-30",
                "integrity_failures": [], "market_assets": 19,
                "market_expected_row_gaps": 285}
    summary, events = [], []
    for row in p["market_queue"]:
        key = row["indicator"]
        summary.append({"layer": "MARKET", "indicator": key, "schedule": row["frequency"],
                        "first_date": "2026-01-02", "last_date": row["source_last"],
                        "asof_date": "2026-11-20", "missing_expected_records": "15.0"})
        for i in range(15):
            events.append({"layer": "MARKET", "status": "GAP", "indicator": key,
                           "date": (date(2026, 11, 1)+timedelta(days=i)).isoformat()})
    return overview, summary, events, p


class GapLedgerTests(unittest.TestCase):
    def test_all_tail_and_approval_zero(self):
        a,b,c,p = inputs()
        r = build_ledger(a,b,c,p)["totals"]
        self.assertEqual((r["historical_gaps"],r["tail_gaps"]), (0,285))
        self.assertEqual((r["same_basis_unapproved_candidates"],r["source_refetch_rows"]), (135,150))
        self.assertEqual(r["approved_rows"],0)

    def test_basis_mismatch_preserved(self):
        a,b,c,p = inputs()
        row = next(r for r in p["market_queue"] if r["candidate_tail_rows"])
        row["adjustment_flag_matches"] = False
        row["reuse_status"] = "PRICE_ADJUSTMENT_BASIS_MISMATCH_HOLD"
        r = build_ledger(a,b,c,p)["totals"]
        self.assertEqual(r["basis_mismatch_candidates"],15)
        self.assertEqual(r["same_basis_unapproved_candidates"],120)

    def test_historical_gap_not_tail_candidate(self):
        a,b,c,p = inputs()
        key = b[0]["indicator"]
        b[0]["missing_expected_records"] = "16"
        a["market_expected_row_gaps"] += 1
        c.append({"layer":"MARKET","status":"GAP","indicator":key,"date":"2026-09-01"})
        r = build_ledger(a,b,c,p)["totals"]
        self.assertEqual((r["historical_gaps"],r["tail_gaps"]), (1,285))

    def test_newer_audit_than_reference(self):
        a,b,c,p = inputs()
        a["asof_date"] = "2026-11-23"
        for row in b:
            row["asof_date"] = a["asof_date"]
        b[0]["missing_expected_records"] = "16"
        a["market_expected_row_gaps"] += 1
        c.append({"layer":"MARKET","status":"GAP","indicator":b[0]["indicator"],"date":"2026-11-23"})
        r = build_ledger(a,b,c,p)["totals"]
        self.assertEqual(r["unreconciled_tail_rows"],1)

    def test_duplicate_and_wrong_total_rejected(self):
        a,b,c,p = inputs()
        with self.assertRaisesRegex(ValueError,"GAP_IDENTITY"):
            build_ledger(a,b,c+c[:1],p)
        a["market_expected_row_gaps"] += 1
        with self.assertRaisesRegex(ValueError,"TOTAL_GAP_COUNT"):
            build_ledger(a,b,c,p)

    def test_mismatched_reference_count_is_unreconciled(self):
        a,b,c,p = inputs()
        c.pop(0)
        b[0]["missing_expected_records"] = "14"
        a["market_expected_row_gaps"] -= 1
        r = build_ledger(a,b,c,p)
        self.assertEqual(r["totals"]["unreconciled_tail_rows"],14)
        self.assertFalse(next(x for x in r["assets"] if x["indicator"] == b[0]["indicator"])["plan_reconciled"])
