"""Google Sheets ownership / stale-write / unknown-response synthetic regression."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from g12_sheet_ownership_gate import (
    SYS_TAB, CONTROL_TAB, BoundaryViolation, WritePlan, SyntheticSheet,
    reconcile_unknown_response, unsafe_full_row_rewrite_demo,
)
from g16_synthetic_pipeline import IsolationError

def plan(record_id="TEST-R1", row=2, **overrides):
    fields = {"stage": "SYN-SIF", "attention": "No", "latest_uid": "SYN-1"}
    fields.update(overrides.pop("values", {}))
    return WritePlan(overrides.pop("sheet_id", "TEST-SHEET"),
                     overrides.pop("tab", SYS_TAB),
                     overrides.pop("operation", "update_existing_cells"),
                     record_id, row, fields)

def controls():
    return {"hold": False, "skip": False, "restore": False,
            "prepayment": True, "notes": ""}

class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"G16_SYNTHETIC_ONLY": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.sheet = SyntheticSheet()
        self.sheet.register_fixture("TEST-R1", 2, controls())

    def test_001_system_fields_only(self):
        self.sheet.publish(plan())
        self.assertEqual(self.sheet.system["TEST-R1"]["attention"], "No")
        self.assertEqual(self.sheet.writes, 1)

    def test_002_control_values_never_mutated(self):
        original = dict(self.sheet.controls["TEST-R1"])
        self.sheet.publish(plan())
        self.assertEqual(self.sheet.controls["TEST-R1"], original)
        self.assertEqual(self.sheet.control_writes_by_system, 0)

    def test_003_human_hold_edited_between_plan_and_write_preserved(self):
        to_write = plan()
        self.sheet.user_edit("TEST-R1", "hold", True)
        self.sheet.publish(to_write)
        self.assertTrue(self.sheet.controls["TEST-R1"]["hold"])

    def test_004_human_skip_restored_between_plan_and_write_preserved(self):
        to_write = plan()
        self.sheet.user_edit("TEST-R1", "skip", True)
        self.sheet.user_edit("TEST-R1", "restore", True)
        self.sheet.publish(to_write)
        self.assertTrue(self.sheet.controls["TEST-R1"]["skip"])
        self.assertTrue(self.sheet.controls["TEST-R1"]["restore"])

    def test_005_negative_control_stale_full_row_loses_manual_edit(self):
        old = controls()
        live = controls()
        live["hold"] = True
        bad = unsafe_full_row_rewrite_demo(old, live, plan().values)
        self.assertFalse(bad["hold"])  # demonstrates the unsafe behavior
        self.assertTrue(live["hold"])  # live user edit had been True

    def test_006_success_readback_matches_observed_state(self):
        p = plan()
        self.sheet.publish(p)
        observed = reconcile_unknown_response(self.sheet, p)
        self.assertEqual(observed.outcome, "CURRENT_STATE_MATCHES")

    def test_007_before_write_failure_remains_unknown(self):
        p = plan()
        self.sheet.fail_before = True
        with self.assertRaisesRegex(RuntimeError, "BEFORE_APPLY"):
            self.sheet.publish(p)
        self.assertEqual(reconcile_unknown_response(self.sheet, p).outcome,
                         "UNKNOWN_OR_ROW_MOVED")

    def test_008_response_lost_after_write_matches_observation(self):
        p = plan()
        self.sheet.fail_after = True
        with self.assertRaisesRegex(RuntimeError, "RESPONSE_LOST"):
            self.sheet.publish(p)
        self.assertEqual(reconcile_unknown_response(self.sheet, p).outcome,
                         "CURRENT_STATE_MATCHES")
        self.assertEqual(self.sheet.writes, 1)

    def test_009_external_revision_after_lost_response_requires_review(self):
        p = plan()
        self.sheet.fail_after = True
        with self.assertRaisesRegex(RuntimeError, "RESPONSE_LOST"):
            self.sheet.publish(p)
        # Different synthetic actor updates only its owned projection field.
        self.sheet.system["TEST-R1"]["attention"] = "Yes"
        self.assertEqual(reconcile_unknown_response(self.sheet, p).outcome,
                         "CONFLICT_NEEDS_REVIEW")

    def test_010_moved_row_rejected_before_write(self):
        p = plan()
        self.sheet.user_reorder_row("TEST-R1", 11)
        with self.assertRaisesRegex(BoundaryViolation, "row identity moved"):
            self.sheet.publish(p)
        self.assertEqual(self.sheet.writes, 0)

    def test_011_moved_row_unknown_after_failure(self):
        p = plan()
        self.sheet.publish(p)
        self.sheet.user_reorder_row("TEST-R1", 11)
        self.assertEqual(reconcile_unknown_response(self.sheet, p).outcome,
                         "UNKNOWN_OR_ROW_MOVED")

    def test_012_unknown_record_no_auto_append(self):
        with self.assertRaisesRegex(BoundaryViolation, "unknown stable ID"):
            self.sheet.publish(plan("TEST-R2", 3))

    def test_013_unsafe_structural_methods_denied(self):
        for op in ("insert_row", "delete_rows", "clear_all", "sort",
                   "batch_update_all", "append_row", "merge_cells"):
            with self.subTest(op=op), self.assertRaises(BoundaryViolation):
                self.sheet.publish(plan(operation=op))

    def test_014_user_control_sheet_write_denied(self):
        with self.assertRaises(BoundaryViolation):
            self.sheet.publish(plan(tab=CONTROL_TAB))

    def test_015_real_sheet_id_write_denied(self):
        with self.assertRaises(BoundaryViolation):
            self.sheet.publish(plan(sheet_id="actual-production-sheet"))

    def test_016_output_attempt_to_set_manual_control_denied(self):
        with self.assertRaises(BoundaryViolation):
            self.sheet.publish(plan(values={"hold": True}))

    def test_017_incomplete_output_denied(self):
        p = plan()
        object.__setattr__(p, "values", {"attention": "No"})
        with self.assertRaises(BoundaryViolation):
            self.sheet.publish(p)

    def test_018_duplicate_row_and_key_denied(self):
        with self.assertRaises(BoundaryViolation):
            self.sheet.register_fixture("TEST-R2", 2, controls())
        with self.assertRaises(BoundaryViolation):
            self.sheet.register_fixture("TEST-R1", 3, controls())

    def test_019_invalid_record_id_denied(self):
        with self.assertRaises(BoundaryViolation):
            self.sheet.publish(plan("AMEA2026100001"))

    def test_020_invalid_output_values_denied(self):
        with self.assertRaises(BoundaryViolation):
            self.sheet.publish(plan(values={"stage": "SIF real"}))
        with self.assertRaises(BoundaryViolation):
            self.sheet.publish(plan(values={"latest_uid": "inbox:123"}))

    def test_021_readback_observation_is_not_acknowledgment(self):
        p = plan()
        self.sheet.publish(p)
        result = reconcile_unknown_response(self.sheet, p)
        self.assertEqual(result.outcome, "CURRENT_STATE_MATCHES")
        self.assertNotEqual(result.outcome, "EXACTLY_ONCE_CONFIRMED")

    def test_022_environment_guard(self):
        p = plan()
        with patch.dict(os.environ, {"G16_SYNTHETIC_ONLY": "0"}):
            with self.assertRaises(IsolationError):
                self.sheet.publish(p)

    def test_023_no_system_edit_of_prepayment_flag(self):
        p = plan()
        self.sheet.user_edit("TEST-R1", "prepayment", False)
        self.sheet.publish(p)
        self.assertFalse(self.sheet.controls["TEST-R1"]["prepayment"])

    def test_024_stale_row_range_refused_even_if_data_matches(self):
        p = plan(row=7)
        with self.assertRaises(BoundaryViolation):
            self.sheet.publish(p)
        self.assertEqual(self.sheet.writes, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
