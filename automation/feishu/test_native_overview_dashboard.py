#!/usr/bin/env python3
"""Offline ownership and semantic reconciliation checks; no live service calls."""
import copy
import json
import unittest
from unittest.mock import patch

import native_overview_dashboard as overview


class FakeCLI:
    def __init__(self):
        self.specs = overview.build_specs()
        self.ids = {spec["key"]: "chtTest" + str(i) for i, spec in enumerate(self.specs)}
        self.blocks = {self.ids[spec["key"]]: {
            "block_id": self.ids[spec["key"]], "name": spec["name"],
            "type": spec["type"], "data_config": copy.deepcopy(spec["data_config"]),
            "position": {"x": 0, "y": i * 6, "w": 12, "h": 6},
        } for i, spec in enumerate(self.specs)}
        self.calls = []
        self.dashboard = {"dashboard_id": overview.DASHBOARD_ID, "name": overview.TITLE}
        self.tables, self.fields = [], {}
        for i, (name, fields) in enumerate(overview.required_fields(self.specs).items()):
            ident = overview.SOURCE_TABLE_IDS[name]
            self.tables.append({"id": ident, "name": name})
            self.fields[ident] = [
                {"id": "fldTest" + str(j), "name": name, "type": kind or "text"}
                for j, (name, kind) in enumerate(fields.items())]
        self.ignore_updates = False
        self.page_size = 100
        self.break_get_id = None
        self.fail_operation = None

    @property
    def writes(self):
        return [call for call in self.calls if call[0] == "+dashboard-block-update"]

    def __call__(self, *args):
        self.calls.append(args)
        operation = args[0]
        values = dict(zip(args[1::2], args[2::2]))
        if values["--base-token"] != overview.BASE:
            raise AssertionError("another Base")
        if "--dashboard-id" in values:
            if values["--dashboard-id"] != overview.DASHBOARD_ID:
                raise AssertionError("another dashboard")
        if operation == self.fail_operation:
            raise RuntimeError("TEST_BACKEND_FAILED")
        if operation == "+dashboard-get":
            return {"dashboard": copy.deepcopy(self.dashboard)}
        if operation == "+dashboard-block-list":
            rows = list(self.blocks.values())
            start = int(values.get("--page-token", "0"))
            end = start + self.page_size
            return {"items": [{k: copy.deepcopy(v) for k, v in row.items()
                                if k != "data_config"} for row in rows[start:end]],
                    "has_more": end < len(rows), "page_token": str(end)}
        if operation == "+dashboard-block-get":
            ident = values["--block-id"]
            row = copy.deepcopy(self.blocks[ident])
            if ident == self.break_get_id:
                row["block_id"] = "chtUnexpected"
            return {"block": row}
        if operation == "+table-list":
            return {"tables": copy.deepcopy(self.tables), "total": len(self.tables)}
        if operation == "+field-list":
            fields = self.fields[values["--table-id"]]
            return {"fields": copy.deepcopy(fields), "total": len(fields)}
        if operation == "+dashboard-block-update":
            row = self.blocks[values["--block-id"]]
            if not self.ignore_updates:
                if "--name" in values:
                    row["name"] = values["--name"]
                if "--data-config" in values:
                    change = json.loads(values["--data-config"])
                    if change.get("count_all") is True:
                        row["data_config"].pop("series", None)
                    if "series" in change:
                        row["data_config"].pop("count_all", None)
                    row["data_config"].update(change)
            return {"updated": True}
        raise AssertionError("unexpected operation: " + operation)


class OverviewSpecTests(unittest.TestCase):
    def test_sources_are_independent_copies_of_verified_builders(self):
        before_project = copy.deepcopy(overview.PROJECT_BLOCKS)
        before_payment = copy.deepcopy(overview.PAYMENT_BLOCKS)
        first, second = overview.build_specs(), overview.build_specs()
        self.assertEqual(len(first), 6)
        self.assertNotIn("text", {spec["type"] for spec in first})
        for spec in first:
            spec["data_config"]["filter"] = {"conditions": []}
        self.assertEqual(overview.PROJECT_BLOCKS, before_project)
        self.assertEqual(overview.PAYMENT_BLOCKS, before_payment)
        self.assertEqual(overview.build_specs(), second)

    def test_project_and_payment_lanes_are_separate(self):
        specs = {row["key"]: row for row in overview.build_specs()}
        for key in ("project_phase", "project_sif"):
            config = specs[key]["data_config"]
            self.assertTrue(config["count_all"])
            self.assertEqual(config["filter"], {"conjunction": "and", "conditions": [
                {"field_name": "Workflow Lane", "operator": "is", "value": "PRODUCTION_ACTIVE"}]})
        for key in ("payment_state", "payment_balance"):
            config = specs[key]["data_config"]
            self.assertEqual(config["table_name"], "Project Progress Board")
            conditions = {row["field_name"]: row["value"]
                          for row in config["filter"]["conditions"]}
            self.assertEqual(conditions, {"Workflow Lane": "PAYMENT_FOLLOWUP",
                                          "Payment Owner Scope": "MY_VERIFIED"})
        self.assertEqual(specs["payment_balance"]["data_config"]["series"], [
            {"field_name": "Outstanding Balance M KRW", "rollup": "SUM"}])

    def test_live_quote_preserves_checkbox_and_original_currencies(self):
        specs = {row["key"]: row for row in overview.build_specs()}
        quote = specs["weekly_quote"]["data_config"]
        self.assertEqual(quote["table_name"], "Weekly Quote Review")
        self.assertIn({"field_name": "합산 제외", "operator": "is", "value": False},
                      quote["filter"]["conditions"])
        self.assertEqual({row["field_name"] for row in quote["series"]},
                         {"실시간 집계용 건수", "참고 금액 K USD"})
        monthly = specs["monthly_revenue"]["data_config"]
        self.assertEqual(monthly["table_name"], "Monthly Tax Invoice")
        self.assertEqual({row["field_name"] for row in monthly["series"]},
                         {"Net Revenue M KRW", "Net Revenue K USD"})

    def test_overview_balance_groups_by_state_without_changing_detail_builder(self):
        source = next(config for name, kind, config in overview.PAYMENT_BLOCKS
                      if name == "결제 대기 프로젝트 미수금 (M KRW)")
        expected = copy.deepcopy(source)
        expected["group_by"] = [{"field_name": "Payment State", "mode": "integrated",
                                 "sort": {"type": "value", "order": "desc"}}]
        actual = next(spec["data_config"] for spec in overview.build_specs()
                      if spec["key"] == "payment_balance")
        self.assertEqual(actual, expected)
        self.assertEqual(source["group_by"][0]["field_name"], "Project Display Name")

    def test_filter_condition_order_does_not_cause_writes(self):
        config = next(spec["data_config"] for spec in overview.build_specs()
                      if spec["key"] == "payment_state")
        current = copy.deepcopy(config)
        current["filter"]["conditions"].reverse()
        current["colors"] = ["blue", "orange"]
        self.assertEqual(overview.config_patch(current, config), {})

    def test_checkbox_false_is_not_numeric_zero(self):
        config = next(spec["data_config"] for spec in overview.build_specs()
                      if spec["key"] == "weekly_quote")
        current = copy.deepcopy(config)
        next(row for row in current["filter"]["conditions"]
             if row["field_name"] == "합산 제외")["value"] = 0
        self.assertEqual(set(overview.config_patch(current, config)), {"filter"})

    def test_unfiltered_monthly_detects_ui_scope(self):
        config = next(spec["data_config"] for spec in overview.build_specs()
                      if spec["key"] == "monthly_revenue")
        current = copy.deepcopy(config)
        current.pop("filter")
        self.assertEqual(overview.config_patch(current, config), {})
        current["filter"] = {"conjunction": "and", "conditions": [
            {"field_name": "Month", "operator": "is", "value": "2026-10"}]}
        self.assertEqual(overview.config_patch(current, config), {
            "filter": {"conjunction": "and", "conditions": []}})

    def test_count_and_amount_family_switch_is_not_assumed_supported(self):
        for key in ("project_phase", "weekly_quote"):
            expected = next(spec["data_config"] for spec in overview.build_specs()
                            if spec["key"] == key)
            current = copy.deepcopy(expected)
            if expected.get("count_all"):
                current.pop("count_all")
                current["series"] = [{"field_name": "Other", "rollup": "SUM"}]
            else:
                current.pop("series")
                current["count_all"] = True
            with self.assertRaisesRegex(RuntimeError, "AGGREGATION_FAMILY_CHANGED"):
                overview.config_patch(current, expected)


class OverviewReconcileTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeCLI()

    def run_mode(self, mode):
        return overview.reconcile(mode, self.backend)

    def test_matching_apply_makes_no_writes(self):
        before = copy.deepcopy(self.backend.blocks)
        result = self.run_mode("apply")
        self.assertEqual(result["writes"], 0)
        self.assertEqual(before, self.backend.blocks)
        self.assertEqual(self.backend.writes, [])

    def test_plan_reports_drift_and_verify_fails_without_writes(self):
        self.backend.blocks[self.backend.ids["payment_state"]]["data_config"]["filter"] = {}
        self.assertEqual(self.run_mode("plan")["drift"], 1)
        with self.assertRaisesRegex(RuntimeError, "CONFIG_DRIFT_1"):
            self.run_mode("verify")
        self.assertEqual(self.backend.writes, [])

    def test_patch_only_changed_filter_preserves_ids_positions_and_unknown_blocks(self):
        ident = self.backend.ids["payment_state"]
        self.backend.blocks[ident]["data_config"]["filter"] = {}
        self.backend.blocks[ident]["data_config"]["colors"] = ["green"]
        custom = {"block_id": "chtPersonal", "name": "개인 메모", "type": "text",
                  "data_config": {"text": "keep"}, "position": {"x": 0, "y": 99, "w": 12, "h": 2}}
        self.backend.blocks[custom["block_id"]] = copy.deepcopy(custom)
        initial_positions = {key: row["position"] for key, row in self.backend.blocks.items()}
        result = self.run_mode("apply")
        self.assertEqual(result["writes"], 1)
        call = self.backend.writes[0]
        change = json.loads(call[call.index("--data-config") + 1])
        self.assertEqual(set(change), {"filter"})
        self.assertNotIn("--position", call)
        self.assertNotIn("--name", call)
        self.assertEqual(self.backend.blocks["chtPersonal"], custom)
        self.assertEqual(self.backend.blocks[ident]["data_config"]["colors"], ["green"])
        self.assertEqual({key: row["position"] for key, row in self.backend.blocks.items()}, initial_positions)
        self.assertEqual(self.run_mode("apply")["writes"], 0)

    def test_renamed_block_fails_without_recreation(self):
        ident = self.backend.ids["project_phase"]
        self.backend.blocks[ident]["name"] = "프로젝트 공정별 현황"
        with self.assertRaisesRegex(RuntimeError, "MANAGED_BLOCK_MISSING"):
            self.run_mode("apply")
        self.assertEqual(self.backend.writes, [])
        self.assertEqual(len(self.backend.blocks), 6)

    def test_duplicate_title_does_not_create_a_block(self):
        ident = self.backend.ids["project_phase"]
        self.backend.blocks["chtReplacement"] = copy.deepcopy(self.backend.blocks[ident])
        self.backend.blocks["chtReplacement"]["block_id"] = "chtReplacement"
        with self.assertRaisesRegex(RuntimeError, "DUPLICATE_NAMED_BLOCK"):
            self.run_mode("apply")
        self.assertEqual(self.backend.writes, [])

    def test_missing_reviewed_block_fails_without_recreation(self):
        del self.backend.blocks[self.backend.ids["weekly_quote"]]
        with self.assertRaisesRegex(RuntimeError, "MANAGED_BLOCK_MISSING"):
            self.run_mode("apply")
        self.assertEqual(self.backend.writes, [])

    def test_type_mismatch_fails_before_any_write(self):
        self.backend.blocks[self.backend.ids["project_phase"]]["data_config"]["filter"] = {}
        self.backend.blocks[self.backend.ids["weekly_quote"]]["type"] = "column"
        with self.assertRaisesRegex(RuntimeError, "TYPE_MISMATCH"):
            self.run_mode("apply")
        self.assertEqual(self.backend.writes, [])

    def test_wrong_dashboard_title_or_id_fails_closed(self):
        for key in ("name", "dashboard_id"):
            with self.subTest(key=key):
                self.backend = FakeCLI()
                self.backend.dashboard[key] = "Other"
                with self.assertRaisesRegex(RuntimeError, "ID_OR_TITLE_MISMATCH"):
                    self.run_mode("apply")
                self.assertEqual(self.backend.writes, [])

    def test_block_get_identity_mismatch_fails_before_changes(self):
        self.backend.blocks[self.backend.ids["project_phase"]]["data_config"]["filter"] = {}
        self.backend.break_get_id = self.backend.ids["monthly_revenue"]
        with self.assertRaisesRegex(RuntimeError, "BLOCK_ID_MISMATCH"):
            self.run_mode("apply")
        self.assertEqual(self.backend.writes, [])

    def test_unreadable_config_fails_before_any_write(self):
        self.backend.blocks[self.backend.ids["monthly_revenue"]]["data_config"] = None
        with self.assertRaisesRegex(RuntimeError, "CONFIG_UNREADABLE"):
            self.run_mode("apply")
        self.assertEqual(self.backend.writes, [])

    def test_schema_missing_and_wrong_numeric_type_fail_closed(self):
        table = next(ident for ident, fields in self.backend.fields.items()
                     if any(row["name"] == "Outstanding Balance M KRW" for row in fields))
        field = next(row for row in self.backend.fields[table]
                     if row["name"] == "Outstanding Balance M KRW")
        field["type"] = "text"
        with self.assertRaisesRegex(RuntimeError, "FIELD_TYPE_MISMATCH"):
            self.run_mode("apply")
        self.backend.fields[table].remove(field)
        with self.assertRaisesRegex(RuntimeError, "FIELD_MISSING_OR_DUPLICATE"):
            self.run_mode("apply")
        self.assertEqual(self.backend.writes, [])

    def test_same_table_name_on_replaced_id_fails_closed(self):
        self.backend.tables[0]["id"] = "tblReplacement"
        with self.assertRaisesRegex(RuntimeError, "TABLE_ID_MISMATCH"):
            self.run_mode("apply")
        self.assertEqual(self.backend.writes, [])

    def test_total_detects_truncated_catalog_without_has_more(self):
        for operation in ("+table-list", "+field-list"):
            with self.subTest(operation=operation):
                def truncated_backend(*args):
                    result = self.backend(*args)
                    if args[0] == operation:
                        result["total"] += 1
                    return result
                with self.assertRaisesRegex(RuntimeError, "SOURCE_(CATALOG|SCHEMA)_INCOMPLETE"):
                    overview.reconcile("apply", truncated_backend)
                self.assertEqual(self.backend.writes, [])

    def test_failed_backend_read_and_failed_readback_are_not_success(self):
        self.backend.fail_operation = "+field-list"
        with self.assertRaisesRegex(RuntimeError, "BACKEND_FAILED"):
            self.run_mode("apply")
        self.assertEqual(self.backend.writes, [])
        self.backend.fail_operation = None
        self.backend.blocks[self.backend.ids["payment_state"]]["data_config"]["filter"] = {}
        self.backend.ignore_updates = True
        with self.assertRaisesRegex(RuntimeError, "READBACK_MISMATCH"):
            self.run_mode("apply")

    def test_pagination_checks_all_existing_blocks(self):
        self.backend.page_size = 2
        self.assertEqual(self.run_mode("verify")["blocks"], 6)
        self.assertEqual(sum(call[0] == "+dashboard-block-list" for call in self.backend.calls), 3)

    def test_project_balance_copy_is_patched_only_to_state_grouping(self):
        ident = self.backend.ids["payment_balance"]
        source = next(config for name, kind, config in overview.PAYMENT_BLOCKS
                      if name == "결제 대기 프로젝트 미수금 (M KRW)")
        self.backend.blocks[ident]["data_config"] = copy.deepcopy(source)
        before = copy.deepcopy(self.backend.blocks[ident])
        self.assertEqual(self.run_mode("apply")["writes"], 1)
        call = self.backend.writes[0]
        change = json.loads(call[call.index("--data-config") + 1])
        self.assertEqual(set(change), {"group_by"})
        after = self.backend.blocks[ident]
        self.assertEqual(after["data_config"]["filter"], before["data_config"]["filter"])
        self.assertEqual(after["data_config"]["series"], before["data_config"]["series"])
        self.assertEqual(after["block_id"], before["block_id"])
        self.assertEqual(after["position"], before["position"])
        self.assertEqual(self.run_mode("apply")["writes"], 0)

    def test_invalid_pagination_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "MISSING_PAGE_TOKEN"):
            overview.complete_page({"has_more": True})
        with self.assertRaisesRegex(RuntimeError, "AMBIGUOUS_PAGINATION"):
            overview.complete_page({"has_more": False, "nested": {"has_more": True}})
        self.assertEqual(self.backend.writes, [])

    def test_wrong_chart_source_fails_before_any_write(self):
        self.backend.blocks[self.backend.ids["project_phase"]]["data_config"]["filter"] = {}
        self.backend.blocks[self.backend.ids["weekly_quote"]]["data_config"]["table_name"] = "Weekly Quote KPI"
        with self.assertRaisesRegex(RuntimeError, "BLOCK_SOURCE_CHANGED"):
            self.run_mode("apply")
        self.assertEqual(self.backend.writes, [])

    def test_plan_inventory_contains_only_reviewed_metadata(self):
        result = self.run_mode("plan")
        self.assertEqual(len(result["inventory"]), 6)
        for row in result["inventory"]:
            self.assertEqual(set(row), {"name", "block_id", "type", "source_table_id"})
            self.assertIn(row["block_id"], self.backend.blocks)

    def test_ui_rich_text_unknown_name_type_and_id_are_preserved_without_get(self):
        note = {"block_id": "opaqueNoteId", "type": "RICH_TEXT",
                "data_config": {"rich_text": "운영 지표 확인 안내\n" + overview.NOTE},
                "position": {"x": 0, "y": 0, "w": 12, "h": 3}}
        self.backend.blocks[note["block_id"]] = copy.deepcopy(note)
        self.backend.blocks[self.backend.ids["payment_state"]]["data_config"]["filter"] = {}
        self.assertEqual(self.run_mode("apply")["writes"], 1)
        self.assertEqual(self.backend.blocks[note["block_id"]], note)
        for call in self.backend.calls:
            if "--block-id" in call:
                self.assertNotEqual(call[call.index("--block-id") + 1], note["block_id"])

    def test_disappearing_unknown_ui_block_fails_inventory_readback(self):
        note = {"block_id": "opaqueNoteId", "type": "RICH_TEXT", "name": "Text"}
        self.backend.blocks[note["block_id"]] = note
        list_reads = 0
        def changing_backend(*args):
            nonlocal list_reads
            if args[0] == "+dashboard-block-list":
                list_reads += 1
                if list_reads == 2:
                    self.backend.blocks.pop(note["block_id"])
            return self.backend(*args)
        with self.assertRaisesRegex(RuntimeError, "EXISTING_BLOCK_DISAPPEARED"):
            overview.reconcile("apply", changing_backend)

    def test_block_replacement_during_apply_fails_final_identity_readback(self):
        list_reads = 0
        def changing_backend(*args):
            nonlocal list_reads
            if args[0] == "+dashboard-block-list":
                list_reads += 1
                if list_reads == 2:
                    ident = self.backend.ids["project_phase"]
                    row = self.backend.blocks.pop(ident)
                    row["block_id"] = "chtConcurrentReplacement"
                    self.backend.blocks[row["block_id"]] = row
            return self.backend(*args)
        with self.assertRaisesRegex(RuntimeError, "BLOCK_ID_CHANGED_DURING_APPLY"):
            overview.reconcile("apply", changing_backend)
        self.assertEqual(self.backend.writes, [])

    def test_base_guard_and_bad_mode_do_not_call_live_cli(self):
        with patch.dict(overview.os.environ, {"FEISHU_BASE_APP_TOKEN": "other"}), \
             patch.object(overview, "reconcile") as mocked:
            with self.assertRaisesRegex(RuntimeError, "REFUSE_OTHER_BASE"):
                overview.main()
            mocked.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, "BAD_MODE"):
            self.run_mode("unknown")
        self.assertEqual(self.backend.calls, [])


if __name__ == "__main__":
    unittest.main()
