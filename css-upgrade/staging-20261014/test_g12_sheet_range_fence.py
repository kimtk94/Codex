"""Offline G12 live-schema cell ownership tests; never call Google Sheets."""
import unittest

from g12_sheet_range_fence import (
    SHEETS, WriteDenied, WriteIntent, column_number, parse_bounded_a1,
    validate_intent,
)


def intent(sheet_id=1618938211, sheet_name="CSS Contract-SIF Tracker",
           op="values.update", a1="E2:E20", mask="userEnteredValue"):
    return WriteIntent(sheet_id, sheet_name, op, a1, mask)


class WriterFenceTests(unittest.TestCase):
    def blocked(self, obj):
        with self.assertRaises(WriteDenied):
            validate_intent(obj)

    def test_verified_live_schema_mapping(self):
        self.assertEqual(len(SHEETS), 4)
        self.assertEqual(SHEETS[1618938211].control_columns, frozenset({0, 1, 2}))
        self.assertEqual(SHEETS[692581491].control_columns, frozenset({0, 2, 3}))
        self.assertEqual(SHEETS[948865119].key_columns, frozenset({4}))

    def test_prevent_sif_skip_prepayment_skip_reason(self):
        for a1 in ("A2:A3", "B2", "C7", "A2:AL900", "$B$2:$B$20"):
            with self.subTest(a1=a1):
                self.blocked(intent(a1=a1))

    def test_allow_unrelated_field_only(self):
        result = validate_intent(intent(a1="D2:D40"))
        self.assertEqual(result["status"], "SCOPED_NON_CONTROL_VALUE_WRITE")
        self.assertEqual(result["rows"], 39)
        self.assertFalse(result["row_identity_or_concurrency_proven"])
        self.assertFalse(result["live_sheet_write_performed"])

    def test_refuse_identity_field_update_even_if_not_manual_flag(self):
        self.blocked(intent(a1="AD2:AD40"))
        self.blocked(intent(a1="AH2:AH40"))

    def test_other_three_live_tabs(self):
        cases = [
            (948865119, "CSS Project Dashboard", "A2:B19", True),
            (948865119, "CSS Project Dashboard", "C2:D19", False),
            (948865119, "CSS Project Dashboard", "E2", True),
            (692581491, "CSS Contract-SIF Skipped", "A2", True),
            (692581491, "CSS Contract-SIF Skipped", "C2:D10", True),
            (692581491, "CSS Contract-SIF Skipped", "E2:E9", False),
            (692581491, "CSS Contract-SIF Skipped", "N2", True),
            (1445506838, "CSS Manual Exclusions", "A2", True),
            (1445506838, "CSS Manual Exclusions", "B2", True),
            (1445506838, "CSS Manual Exclusions", "C2", False),
        ]
        for sid, name, a1, should_block in cases:
            with self.subTest(name=name, a1=a1):
                request = intent(sid, name, a1=a1)
                if should_block:
                    self.blocked(request)
                else:
                    self.assertEqual(validate_intent(request)["status"],
                                     "SCOPED_NON_CONTROL_VALUE_WRITE")

    def test_unknown_title_id_and_bool(self):
        self.blocked(intent(100, "Other"))
        self.blocked(intent(True, "CSS Contract-SIF Tracker"))
        self.blocked(intent(sheet_name="Other"))
        self.blocked(intent(948865119, "CSS Contract-SIF Tracker"))

    def test_structural_and_unsafe_ops_are_blocked_even_on_safe_column(self):
        for operation in (
            "batch_clear", "clear", "sort", "resize", "set_with_dataframe",
            "updateCells.all", "values.batchUpdate", "append_rows", "batch_update",
        ):
            with self.subTest(op=operation):
                self.blocked(intent(op=operation))

    def test_whitelist_field_mask_only(self):
        self.blocked(intent(op="updateCells.userEnteredValue", mask="*"))
        self.assertEqual(
            validate_intent(intent(op="updateCells.userEnteredValue"))["status"],
            "SCOPED_NON_CONTROL_VALUE_WRITE",
        )

    def test_unbounded_and_malformed_ranges_fail_closed(self):
        for a1 in ("A:A", "A1:", "A1:B", "A0:A1", "C30:B2",
                   "C10:C8", "C1:C10", "C2:ZZ", "Sheet1!D2",
                   "'CSS Contract-SIF Tracker'!D2", "a2", "", "C 2"):
            with self.subTest(a1=a1):
                self.blocked(intent(a1=a1))

    def test_a1_conversion(self):
        self.assertEqual(column_number("A"), 0)
        self.assertEqual(column_number("Z"), 25)
        self.assertEqual(column_number("AA"), 26)
        self.assertEqual(column_number("AL"), 37)
        self.assertEqual(parse_bounded_a1("$D$2:$D$15"), (1, 15, 3, 4))

    def test_no_call_with_side_effects(self):
        value = validate_intent(intent(a1="F5:F9"))
        self.assertEqual(set(value), {
            "status", "sheet_id", "operation", "rows", "columns",
            "controls_protected_by_this_intent", "live_sheet_write_performed",
            "row_identity_or_concurrency_proven",
        })


if __name__ == "__main__":
    unittest.main()
