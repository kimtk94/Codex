"""Synthetic regressions for restart-safe private Contact verification batches."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import resume_contact_alias_verification_private as batch


def row(n):
    return {"contact_id":f"003{n:012d}AAA", "opportunity_id":f"006{n:012d}AAA"}


class ResumeReviewTests(unittest.TestCase):
    def test_offset_does_not_revisit_first_reviewed_contacts(self):
        items = [row(i) for i in range(20)]
        got = batch.select_new_candidates(items, set(), set(), 10, 5)
        self.assertEqual([r["contact_id"] for r in got], [row(i)["contact_id"] for i in range(10,15)])

    def test_existing_verified_skipped(self):
        items = [row(i) for i in range(12)]
        got = batch.select_new_candidates(items, {row(10)["contact_id"]}, set(), 10, 3)
        self.assertEqual([r["contact_id"] for r in got], [row(11)["contact_id"]])

    def test_previous_hold_skipped_until_explicit_retry(self):
        items=[row(0),row(1),row(2)]
        key=row(1)["contact_id"]
        first=batch.select_new_candidates(items, set(), {key}, 0, 3)
        self.assertEqual([x["contact_id"] for x in first],[row(0)["contact_id"],row(2)["contact_id"]])
        retry=batch.select_new_candidates(items, set(), {key}, 0, 3, retry_holds=True)
        self.assertEqual(len(retry),3)

    def test_repeated_runs_deterministic(self):
        items=[row(i) for i in range(15)]
        results=[batch.select_new_candidates(items, set(), set(), 10, 5) for _ in range(3)]
        self.assertEqual(results[0],results[1])
        self.assertEqual(results[1],results[2])

    def test_no_extra_rows_for_large_limit(self):
        self.assertEqual(len(batch.select_new_candidates([row(0)],set(),set(),0,10)),1)

    def test_invalid_payload(self):
        with self.assertRaises(ValueError):
            batch.select_new_candidates({},set(),set(),0,1)

    def test_private_json_atomic_write(self):
        with tempfile.TemporaryDirectory() as d:
            destination=Path(d)/"private.json"
            batch.private_json_write(destination, [{"status":"PASS","save_clicked":False}])
            result=json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(result[0]["status"],"PASS")
            self.assertFalse((destination.parent/(destination.name+".writing")).exists())
            batch.private_json_write(destination, [{"status":"HOLD","save_clicked":False}])
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8"))[0]["status"],"HOLD")


if __name__ == "__main__":
    unittest.main()
