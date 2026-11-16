"""Synthetic only. No CRM Account/Contact/QID or original KRW prices in CI."""
import unittest
from quote_2026_historical_batch_selection import select_unattempted_2026


def ref(month, serial):
    day = f"2026-{month:02d}-05"
    return {
        "quote_id": f"QID-{day}-{100000 + serial}",
        "created_date": day,
        "approval_evidence": "APPROVED_TEXT",
    }


class WaveSelectionTests(unittest.TestCase):
    def test_previous_retry_is_not_falsely_counted_as_unattempted(self):
        rows = [ref(1, x) for x in range(10)]
        first = rows[:4]
        second = [rows[3], *rows[4:8]]  # one repeated held Quote
        verified = {x["quote_id"] for x in rows[:3]+rows[4:8]}
        result = select_unattempted_2026(rows, [first, second], verified)
        self.assertEqual(result["eligible_unique"], 10)
        self.assertEqual(result["attempted_rows"], 9)
        self.assertEqual(result["attempted_unique"], 8)
        self.assertEqual(result["duplicate_attempt_rows"], 1)
        self.assertEqual(result["verified_among_attempted"], 7)
        self.assertEqual(result["held_among_attempted"], 1)
        self.assertEqual(result["remaining_before"], 2)
        self.assertEqual(result["selected_count"], 2)
        self.assertEqual(result["selected"], rows[-2:])
        self.assertEqual(result["crm_writes"], 0)
        self.assertIs(result["price_auto_apply"], False)

    def test_full_ten_month_stratification_six_each_with_no_retries(self):
        rows = [ref(month, month*100+i) for month in range(1, 11) for i in range(8)]
        attempts = [[row for row in rows if row["created_date"].startswith(f"2026-{month:02d}")][:1]
                    for month in range(1, 11)]
        verified = {rows[0]["quote_id"], "QID-2026-11-05-199999"}
        result = select_unattempted_2026(rows, attempts, verified, per_month=6)
        self.assertEqual(result["eligible_unique"], 80)
        self.assertEqual(result["attempted_unique"], 10)
        self.assertEqual(result["verified_among_attempted"], 1)
        self.assertEqual(result["held_among_attempted"], 9)
        self.assertEqual(result["remaining_before"], 70)
        self.assertEqual(result["selected_count"], 60)
        self.assertEqual(len({x["quote_id"] for x in result["selected"]}), 60)
        self.assertEqual(result["selected_by_month"],
                         {f"2026-{month:02d}": 6 for month in range(1, 11)})

    def test_exhausted_early_months_refill_to_100_without_retries(self):
        # January is fully attempted, February has only 4 remaining,
        # the other 8 months have ample unattempted rows.
        rows = [ref(1, i) for i in range(20)]
        rows += [ref(2, 200+i) for i in range(4)]
        rows += [ref(m, m*100+i) for m in range(3, 11) for i in range(30)]
        done = {r["quote_id"] for r in rows[:20]}
        batches = [rows[:10], rows[10:20]]
        r = select_unattempted_2026(rows, batches, done, per_month=10, total_limit=100)
        self.assertEqual(r["attempted_unique"], 20)
        self.assertEqual(r["remaining_before"], 244)
        self.assertEqual(r["requested_total"], 100)
        self.assertEqual(r["selected_count"], 100)
        self.assertEqual(r["selected_by_month"].get("2026-01", 0), 0)
        self.assertEqual(r["selected_by_month"]["2026-02"], 4)
        self.assertEqual(sum(r["selected_by_month"].values()), 100)
        self.assertEqual(len({x["quote_id"] for x in r["selected"]}), 100)
        self.assertFalse(done.intersection({x["quote_id"] for x in r["selected"]}))
        self.assertEqual(r["crm_writes"], 0)

    def test_final_94_sources_from_333_unique_and_239_previous_attempts(self):
        # Mirrors the permitted *aggregate* scope, not real QIDs or prices.
        rows=[ref(month,month*1000+i)
              for month in range(1,11)
              for i in range(33 if month<10 else 36)]
        self.assertEqual(len(rows),333)
        # 240 prior manifest rows represented 239 distinct source QIDs;
        # a held Quote had been retried and must not shrink the missing set.
        unique_attempts=rows[:239]
        attempt_rows=[*unique_attempts,unique_attempts[-1]]
        batches=[attempt_rows[i:i+40] for i in range(0,len(attempt_rows),40)]
        verified={x["quote_id"] for x in unique_attempts[:236]}
        result=select_unattempted_2026(rows,batches,verified,
                                        per_month=6,total_limit=94)
        self.assertEqual(result["eligible_unique"],333)
        self.assertEqual(result["attempted_rows"],240)
        self.assertEqual(result["attempted_unique"],239)
        self.assertEqual(result["duplicate_attempt_rows"],1)
        self.assertEqual(result["verified_among_attempted"],236)
        self.assertEqual(result["held_among_attempted"],3)
        self.assertEqual(result["remaining_before"],94)
        self.assertEqual(result["selected_count"],94)
        self.assertEqual(len({r["quote_id"] for r in result["selected"]}),94)
        self.assertFalse(set(x["quote_id"] for x in result["selected"]) & set(x["quote_id"] for x in unique_attempts))
        self.assertEqual(sum(result["selected_by_month"].values()),94)
        self.assertIs(result["price_auto_apply"],False)
        self.assertEqual(result["crm_writes"],0)

    def test_requested_batch_bound_and_source_exhaustion_are_explicit(self):
        rows = [ref(2, 100+i) for i in range(3)]
        r = select_unattempted_2026(rows, [], set(), per_month=10, total_limit=100)
        self.assertEqual(r["selected_count"], 3)
        self.assertEqual(r["requested_total"], 100)
        self.assertEqual(r["eligible_unattempted_months"], {"2026-02": 3})
        for invalid in (0, -1, 251, True, 1.2, "100"):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "TOTAL_LIMIT_INVALID"):
                select_unattempted_2026(rows, [], set(), total_limit=invalid)

    def test_duplicate_eligible_qid_rejected_instead_of_silent_skip(self):
        q = ref(2, 100)
        with self.assertRaisesRegex(ValueError, "DUPLICATE_ELIGIBLE_QID"):
            select_unattempted_2026([q, q], [], set())

    def test_out_of_scope_old_attempt_or_inconsistent_date_blocks(self):
        rows = [ref(1, 1)]
        with self.assertRaisesRegex(ValueError, "ATTEMPTED_QID_OUTSIDE"):
            select_unattempted_2026(rows, [[ref(1, 2)]], set())
        with self.assertRaisesRegex(ValueError, "QUOTE_ID_DATE_MISMATCH"):
            select_unattempted_2026([{**rows[0], "created_date":"2026-02-05"}], [], set())
        with self.assertRaisesRegex(ValueError, "UNAPPROVED_REFERENCE"):
            select_unattempted_2026([{**rows[0], "approval_evidence":"PENDING"}], [], set())
        with self.assertRaisesRegex(ValueError, "PER_MONTH_INVALID"):
            select_unattempted_2026(rows, [], set(), per_month=0)

    def test_already_verified_without_recorded_attempt_is_never_selected(self):
        rows = [ref(3, i) for i in range(3)]
        result = select_unattempted_2026(rows, [], {rows[0]["quote_id"]})
        self.assertEqual(result["attempted_unique"], 0)
        self.assertEqual(result["remaining_before"], 2)
        self.assertEqual([x["quote_id"] for x in result["selected"]],
                         [rows[1]["quote_id"], rows[2]["quote_id"]])


if __name__ == "__main__":
    unittest.main()
