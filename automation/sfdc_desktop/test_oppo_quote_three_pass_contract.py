import unittest

from oppo_quote_three_pass_contract import (
    ValidationHold, compare_three_snapshots,
    compare_three_dryrun_forms, summary,
)


def form(kind, required):
    return {
        "record_type": kind,
        "save_clicked": False,
        "save_and_new_clicked": False,
        "convert_clicked": False,
        "checks": {key: True for key in required},
    }


OPPO_FIELDS = ("source_name_prefilled", "account_prefilled", "contact_prefilled",
               "close_date_copied", "sample_qty_copied",
               "original_name_unchanged", "draft_name_not_saved")
QUOTE_FIELDS = ("record_type_research_amea", "parent_opportunity_prefilled",
                "quote_name_written", "source_quote_name_unchanged",
                "draft_quote_not_saved")


class ThreePassNoSaveTests(unittest.TestCase):
    def test_three_identical_snapshots(self):
        base = {"id1": {"name": "A", "status": "New"},
                "id2": {"name": "B", "status": "New"}}
        result = compare_three_snapshots(base, [base.copy() for _ in range(3)])
        self.assertEqual([x["status"] for x in result], ["PASS"] * 3)

    def test_changed_row_holds(self):
        base = {"id1": {"status": "New"}}
        result = compare_three_snapshots(
            base, [base, {"id1": {"status": "Converted"}}, base])
        self.assertEqual([x["status"] for x in result], ["PASS", "HOLD", "PASS"])

    def test_missing_id_holds(self):
        result = compare_three_snapshots(
            {"id1": [1], "id2": [2]}, [{"id1": [1]}] * 3)
        self.assertTrue(all(x["missing_count"] == 1 for x in result))

    def test_extra_id_holds(self):
        result = compare_three_snapshots({"id1": [1]}, [
            {"id1": [1], "id2": [2]}] * 3)
        self.assertTrue(all(x["extra_count"] == 1 for x in result))

    def test_selected_stable_columns(self):
        base = {"id1": {"name": "A", "viewed_at": "t1"}}
        variants = [{"id1": {"name": "A", "viewed_at": "t2"}}] * 3
        result = compare_three_snapshots(base, variants, stable_columns=("name",))
        self.assertTrue(all(x["status"] == "PASS" for x in result))

    def test_wrong_round_count_holds(self):
        with self.assertRaises(ValidationHold):
            compare_three_snapshots({"id1": [1]}, [{"id1": [1]}] * 2)

    def test_empty_baseline_holds(self):
        with self.assertRaises(ValidationHold):
            compare_three_snapshots({}, [{}, {}, {}])

    def test_three_opportunity_forms_pass(self):
        result = compare_three_dryrun_forms(
            [form("Opportunity", OPPO_FIELDS) for _ in range(3)],
            record_type="Opportunity", required_checks=OPPO_FIELDS)
        self.assertEqual([x["status"] for x in result], ["PASS"] * 3)

    def test_three_quote_forms_pass(self):
        result = compare_three_dryrun_forms(
            [form("Quotation", QUOTE_FIELDS) for _ in range(3)],
            record_type="Quotation", required_checks=QUOTE_FIELDS)
        self.assertEqual([x["status"] for x in result], ["PASS"] * 3)

    def test_quote_parent_missing_holds_only_affected_round(self):
        rows = [form("Quotation", QUOTE_FIELDS) for _ in range(3)]
        rows[1]["checks"]["parent_opportunity_prefilled"] = False
        result = compare_three_dryrun_forms(
            rows, record_type="Quotation", required_checks=QUOTE_FIELDS)
        self.assertEqual([x["status"] for x in result], ["PASS", "HOLD", "PASS"])

    def test_reject_save_flag(self):
        rows = [form("Quotation", QUOTE_FIELDS) for _ in range(3)]
        rows[2]["save_clicked"] = True
        with self.assertRaises(ValidationHold):
            compare_three_dryrun_forms(
                rows, record_type="Quotation", required_checks=QUOTE_FIELDS)

    def test_reject_save_and_new(self):
        rows = [form("Opportunity", OPPO_FIELDS) for _ in range(3)]
        rows[0]["save_and_new_clicked"] = True
        with self.assertRaises(ValidationHold):
            compare_three_dryrun_forms(
                rows, record_type="Opportunity", required_checks=OPPO_FIELDS)

    def test_reject_convert(self):
        rows = [form("Quotation", QUOTE_FIELDS) for _ in range(3)]
        rows[0]["convert_clicked"] = True
        with self.assertRaises(ValidationHold):
            compare_three_dryrun_forms(
                rows, record_type="Quotation", required_checks=QUOTE_FIELDS)

    def test_reject_wrong_record_type(self):
        with self.assertRaises(ValidationHold):
            compare_three_dryrun_forms(
                [form("Opportunity", OPPO_FIELDS)] * 3,
                record_type="Quotation", required_checks=QUOTE_FIELDS)

    def test_reject_missing_comparison_field(self):
        rows = [form("Quotation", QUOTE_FIELDS) for _ in range(3)]
        del rows[0]["checks"]["quote_name_written"]
        result = compare_three_dryrun_forms(
            rows, record_type="Quotation", required_checks=QUOTE_FIELDS)
        self.assertEqual(result[0]["status"], "HOLD")

    def test_all_pass_requires_all_three_categories(self):
        passed = [{"status": "PASS"}] * 3
        held = [{"status": "PASS"}, {"status": "HOLD"}, {"status": "PASS"}]
        self.assertTrue(summary(passed, passed, passed)["all_pass"])
        self.assertFalse(summary(passed, passed, held)["all_pass"])


if __name__ == "__main__":
    unittest.main()
