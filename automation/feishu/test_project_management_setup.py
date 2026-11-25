#!/usr/bin/env python3
"""Synthetic metadata tests; no authentication, records or live APIs."""
import copy
import os
import pathlib
import unittest
import urllib.parse
from unittest.mock import patch

import project_management_setup as pm


def manual_fields():
    return [dict(copy.deepcopy(spec), field_id="fldManual" + str(index))
            for index, spec in enumerate(pm.MANUAL_FIELDS)]


def management_views():
    return [{"view_id": pm.VIEW_IDS[name], "view_name": name,
             "view_type": kind, "property": {"custom_ui_setting": "preserve"}}
            for name, kind in pm.VIEW_TYPES.items()]


class FakeMetadata:
    def __init__(self, fields=None, views=None):
        self.tables = [{"table_id": pm.TABLE_ID, "name": pm.TABLE_NAME}]
        self.fields = [{"field_id": "fldSource", "field_name": "Source Key", "type": 1}]
        self.fields += copy.deepcopy(manual_fields() if fields is None else fields)
        self.views = [{"view_id": "vew9v3YnBX", "view_name": "진행 중 프로젝트", "view_type": "grid",
                       "property": {"filter_info": {"conjunction": "and", "conditions": []}}}]
        self.views += copy.deepcopy(management_views() if views is None else views)
        self.records = [{"record_id": "recFixture", "fields": {
            "Source Key": "SOURCE:fixture", "관리 담당": [{"id": "ouFixture"}],
            "관리 메모": "Preserve this manual note", "다음 확인일": 1795478400000,
            "Payment Owner Scope": "MY_VERIFIED", "Current Stage": "SOURCE_STAGE"}}]
        self.calls = []
        self.field_reads = 0
        self.before_fields_read = None
        self.after_create = None
        self.omit_created_field = False

    def __call__(self, method, path, token, data=None, action=None):
        self.calls.append((method, path, copy.deepcopy(data)))
        route = urllib.parse.urlsplit(path).path
        if method == "GET":
            if route == pm.ROOT + "/tables":
                items = self.tables
            elif route == pm.TABLE_PATH + "/fields":
                self.field_reads += 1
                if self.before_fields_read:
                    self.before_fields_read(self)
                items = self.fields
            elif route == pm.TABLE_PATH + "/views":
                items = self.views
            elif route.startswith(pm.TABLE_PATH + "/views/"):
                identity = route.rsplit("/", 1)[-1]
                item = next(item for item in self.views if item["view_id"] == identity)
                detail = copy.deepcopy(item)
                detail["view_type"] = pm.VIEW_TYPES[detail["view_name"]]
                return {"view": detail}
            else:
                raise AssertionError("Unexpected metadata read: " + route)
            return {"items": copy.deepcopy(items), "has_more": False}
        if method == "POST" and route == pm.TABLE_PATH + "/fields":
            self.assert_no_existing_name(data["field_name"])
            field = dict(copy.deepcopy(data), field_id="fldCreated" + str(len(self.fields)))
            if not self.omit_created_field:
                self.fields.append(field)
            if self.after_create:
                self.after_create(self)
            return {"field": copy.deepcopy(field)}
        raise AssertionError("Unexpected mutation: " + method + " " + route)

    def assert_no_existing_name(self, name):
        if any(item["field_name"] == name for item in self.fields):
            raise AssertionError("Duplicate field create")

    def client(self):
        return pm.MetadataClient("fixture-token", request=self)

    def writes(self):
        return [call for call in self.calls if call[0] != "GET"]


class ProjectManagementSetupTests(unittest.TestCase):
    def test_default_plan_reports_missing_fields_without_writes(self):
        fake = FakeMetadata(fields=[], views=[])
        result = pm.setup(fake.client())
        self.assertEqual(result["planned_field_creates"], list(pm.FIELD_SPECS))
        self.assertEqual(result["created_fields"], [])
        self.assertEqual(result["view_presence_status"], "UI_SETUP_REQUIRED")
        self.assertEqual(result["missing_ui_views"], list(pm.VIEW_TYPES))
        self.assertEqual(fake.writes(), [])

    def test_apply_only_adds_five_exact_manual_fields_without_defaults(self):
        fake = FakeMetadata(fields=[])
        old_records, old_views = copy.deepcopy(fake.records), copy.deepcopy(fake.views)
        result = pm.setup(fake.client(), "apply")
        self.assertEqual([call[2] for call in fake.writes()], list(pm.MANUAL_FIELDS))
        self.assertEqual(len(result["created_fields"]), 5)
        self.assertEqual(result["field_type_status"], "READY")
        self.assertEqual(result["field_configuration_review"], [])
        self.assertEqual(fake.records, old_records)
        self.assertEqual(fake.views, old_views)
        self.assertFalse(pm.FIELD_SPECS["관리 담당"]["property"]["multiple"])
        self.assertFalse(pm.FIELD_SPECS["다음 확인일"]["property"]["auto_fill"])
        self.assertTrue(all("default_value" not in item for item in pm.MANUAL_FIELDS))
        self.assertTrue(all("/records" not in call[1] for call in fake.calls))

    def test_apply_is_idempotent_and_preserves_existing_custom_settings(self):
        fake = FakeMetadata()
        fake.fields[1]["property"]["extra_ui_setting"] = "preserve"
        old = copy.deepcopy((fake.fields, fake.views, fake.records))
        first = pm.setup(fake.client(), "apply")
        second = pm.setup(fake.client(), "apply")
        self.assertEqual(first["created_fields"], [])
        self.assertEqual(second["created_fields"], [])
        self.assertEqual(fake.writes(), [])
        self.assertEqual((fake.fields, fake.views, fake.records), old)

    def test_existing_type_mismatch_blocks_all_creates(self):
        fake = FakeMetadata(fields=[{"field_id": "fldWrong", "field_name": "관리 담당", "type": 1}])
        with self.assertRaisesRegex(pm.SafeError, "FIELD_TYPE_MISMATCH"):
            pm.setup(fake.client(), "apply")
        self.assertEqual(fake.writes(), [])

    def test_existing_settings_are_reported_for_ui_review_not_rewritten(self):
        fake = FakeMetadata()
        fake.fields[1]["property"]["multiple"] = True
        fake.fields[2]["property"]["options"] = [{"name": "custom"}]
        result = pm.setup(fake.client(), "apply")
        self.assertEqual({item["field"] for item in result["field_configuration_review"]}, {"관리 담당", "관리 우선순위"})
        self.assertEqual(fake.writes(), [])

    def test_additional_select_options_are_preserved_but_flagged_for_ui_review(self):
        fake = FakeMetadata()
        fake.fields[2]["property"]["options"].append({"name": "User extra option"})
        result = pm.setup(fake.client(), "apply")
        self.assertEqual(result["field_configuration_review"], [
            {"field": "관리 우선순위", "setting": "options", "status": "UI_REVIEW_REQUIRED"}])
        self.assertEqual(fake.fields[2]["property"]["options"][-1]["name"], "User extra option")
        self.assertEqual(fake.writes(), [])

    def test_wrong_or_duplicate_table_name_or_id_never_creates(self):
        cases = [
            [{"name": pm.TABLE_NAME, "table_id": "tblDifferent"}],
            [{"name": "Renamed", "table_id": pm.TABLE_ID}],
            [{"name": pm.TABLE_NAME, "table_id": pm.TABLE_ID}] * 2,
            [{"name": pm.TABLE_NAME, "table_id": pm.TABLE_ID}, {"name": pm.TABLE_NAME, "table_id": "tblDuplicate"}],
        ]
        for tables in cases:
            with self.subTest(tables=tables):
                fake = FakeMetadata(fields=[])
                fake.tables = tables
                with self.assertRaisesRegex(pm.SafeError, "TABLE_"):
                    pm.setup(fake.client(), "apply")
                self.assertEqual(fake.writes(), [])

    def test_duplicate_manual_field_blocks_all_writes(self):
        fake = FakeMetadata()
        fake.fields.append(copy.deepcopy(fake.fields[1]))
        with self.assertRaisesRegex(pm.SafeError, "FIELD_NOT_UNIQUE"):
            pm.setup(fake.client(), "apply")
        self.assertEqual(fake.writes(), [])

    def test_concurrent_ui_field_create_is_reused(self):
        fake = FakeMetadata(fields=manual_fields()[1:])
        def add_between_reads(current):
            if current.field_reads == 2:
                current.fields.append(manual_fields()[0])
        fake.before_fields_read = add_between_reads
        result = pm.setup(fake.client(), "apply")
        self.assertEqual(result["created_fields"], [])
        self.assertEqual(fake.writes(), [])

    def test_create_requires_independent_metadata_readback(self):
        fake = FakeMetadata(fields=manual_fields()[1:])
        fake.omit_created_field = True
        with self.assertRaisesRegex(pm.SafeError, "CREATE_READBACK_MISSING"):
            pm.setup(fake.client(), "apply")
        self.assertEqual(len(fake.writes()), 1)

    def test_existing_field_identity_change_is_detected(self):
        fake = FakeMetadata(fields=manual_fields()[1:])
        fake.after_create = lambda current: current.fields[0].update(field_id="fldReplaced")
        with self.assertRaisesRegex(pm.SafeError, "EXISTING_FIELD_IDENTITY_CHANGED"):
            pm.setup(fake.client(), "apply")

    def test_existing_view_identity_change_is_detected(self):
        fake = FakeMetadata(fields=manual_fields()[1:])
        fake.after_create = lambda current: current.views[0].update(view_name="Changed externally")
        with self.assertRaisesRegex(pm.SafeError, "EXISTING_VIEW_IDENTITY_CHANGED"):
            pm.setup(fake.client(), "apply")

    def test_view_presence_does_not_claim_kanban_or_calendar_configuration(self):
        fake = FakeMetadata()
        result = pm.setup(fake.client())
        self.assertEqual(result["view_presence_status"], "PRESENT")
        self.assertEqual(result["view_layout_status"], "UI_MANAGED_NOT_VERIFIED")
        self.assertEqual(result["view_writes"], 0)
        self.assertEqual(result["record_reads"], 0)
        self.assertEqual(result["record_writes"], 0)

    def test_missing_view_type_is_read_individually_without_mutation(self):
        fake = FakeMetadata()
        fake.views[1].pop("view_type")
        result = pm.setup(fake.client())
        self.assertEqual(result["views"]["00 관리 작업대"]["view_type"], "grid")
        self.assertTrue(any(call[1].endswith("/views/" + pm.VIEW_IDS["00 관리 작업대"]) for call in fake.calls))
        self.assertEqual(fake.writes(), [])

    def test_calendar_type_discrepancy_is_reported_only_in_readonly_plan(self):
        for reported in ("unknown", "grid", "not_support"):
            with self.subTest(reported=reported):
                fake = FakeMetadata()
                calendar = fake.views[-1]
                calendar["view_type"] = reported
                old = copy.deepcopy((fake.fields, fake.views, fake.records))
                result = pm.setup(fake.client(), "plan")
                self.assertEqual(result["view_presence_status"], "PRESENT")
                self.assertEqual(result["view_type_status"], "UI_REVIEW_REQUIRED")
                self.assertEqual(result["view_type_review"], ["03 확인 일정"])
                self.assertEqual(result["views"]["03 확인 일정"], {
                    "view_id": pm.VIEW_IDS["03 확인 일정"], "view_type": reported,
                    "expected_view_type": "calendar", "type_status": "UI_REVIEW_REQUIRED"})
                self.assertEqual(result["view_layout_status"], "UI_MANAGED_NOT_VERIFIED")
                self.assertEqual(fake.writes(), [])
                self.assertEqual((fake.fields, fake.views, fake.records), old)

    def test_calendar_type_discrepancy_still_blocks_apply_before_field_create(self):
        fake = FakeMetadata(fields=[])
        fake.views[-1]["view_type"] = "unknown"
        with self.assertRaisesRegex(pm.SafeError, "VIEW_TYPE_MISMATCH"):
            pm.setup(fake.client(), "apply")
        self.assertEqual(fake.writes(), [])

    def test_calendar_identity_drift_still_blocks_plan(self):
        for change in ({"view_id": "vewReplacement"}, {"view_name": "Renamed calendar"}):
            with self.subTest(change=change):
                fake = FakeMetadata()
                fake.views[-1].update(change)
                fake.views[-1]["view_type"] = "unknown"
                with self.assertRaisesRegex(pm.SafeError, "VIEW_ID(_NAME)?_MISMATCH"):
                    pm.setup(fake.client(), "plan")
                self.assertEqual(fake.writes(), [])

    def test_non_calendar_type_mismatch_still_blocks_plan(self):
        fake = FakeMetadata()
        fake.views[1]["view_type"] = "kanban"
        with self.assertRaisesRegex(pm.SafeError, "VIEW_TYPE_MISMATCH"):
            pm.setup(fake.client(), "plan")
        self.assertEqual(fake.writes(), [])

    def test_unrecognized_calendar_type_is_not_logged_raw(self):
        fake = FakeMetadata()
        fake.views[-1]["view_type"] = "unrecognized metadata with spaces"
        result = pm.setup(fake.client())
        self.assertEqual(result["views"]["03 확인 일정"]["view_type"], "UNRECOGNIZED")
        self.assertEqual(result["view_type_status"], "UI_REVIEW_REQUIRED")
        self.assertEqual(fake.writes(), [])

    def test_replaced_or_renamed_reviewed_view_blocks_all_creates(self):
        for change in ({"view_id": "vewReplacement"}, {"view_name": "Renamed workbench"}):
            with self.subTest(change=change):
                fake = FakeMetadata(fields=[])
                fake.views[1].update(change)
                with self.assertRaisesRegex(pm.SafeError, "VIEW_ID(_NAME)?_MISMATCH"):
                    pm.setup(fake.client(), "apply")
                self.assertEqual(fake.writes(), [])

    def test_wrong_or_duplicate_management_views_block_creates(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate):
                fake = FakeMetadata(fields=[])
                if duplicate:
                    fake.views.append(copy.deepcopy(fake.views[1]))
                else:
                    fake.views[1]["view_type"] = "calendar"
                with self.assertRaisesRegex(pm.SafeError, "VIEW_(NOT_UNIQUE|TYPE_MISMATCH)"):
                    pm.setup(fake.client(), "apply")
                self.assertEqual(fake.writes(), [])

    def test_transport_rejects_record_access_and_unapproved_mutations(self):
        fake = FakeMetadata()
        client = fake.client()
        attempts = [
            ("GET", pm.TABLE_PATH + "/records", None),
            ("POST", pm.TABLE_PATH + "/records/batch_update", {"records": []}),
            ("PATCH", pm.TABLE_PATH + "/views/vewFixture", {}),
            ("DELETE", pm.TABLE_PATH + "/fields/fldFixture", None),
            ("PUT", pm.TABLE_PATH + "/fields/fldFixture", {}),
            ("POST", pm.TABLE_PATH + "/fields", {"field_name": "Source Key", "type": 1}),
            ("POST", pm.TABLE_PATH + "/fields", {"field_name": "관리 담당", "type": 11}),
            ("POST", pm.TABLE_PATH + "/fields?unsafe=1", pm.MANUAL_FIELDS[0]),
            ("GET", "https://example.invalid/metadata", None),
        ]
        for method, path, payload in attempts:
            with self.subTest(method=method, path=path):
                with self.assertRaises(pm.SafeError):
                    client.call(method, path, payload)
        self.assertEqual(fake.calls, [])

    def test_invalid_mode_and_root_are_rejected_before_transport(self):
        fake = FakeMetadata()
        with self.assertRaisesRegex(pm.SafeError, "INVALID_MODE"):
            pm.setup(fake.client(), "sync")
        with self.assertRaisesRegex(pm.SafeError, "UNKNOWN_BASE"):
            pm.MetadataClient("fixture", pm.ROOT + "-other", fake)
        self.assertEqual(fake.calls, [])

    def test_wrong_base_blocks_authentication(self):
        with patch.dict(os.environ, {"FEISHU_BASE_APP_TOKEN": "wrong"}), patch.object(pm, "auth") as authenticate:
            with self.assertRaisesRegex(pm.SafeError, "UNKNOWN_BASE"):
                pm.main([])
            authenticate.assert_not_called()

    def test_pagination_preserves_all_metadata_and_rejects_repeated_cursor(self):
        pages = iter([
            {"items": [{"name": "Other", "table_id": "tblOther"}], "has_more": True, "page_token": "next"},
            {"items": [{"name": pm.TABLE_NAME, "table_id": pm.TABLE_ID}], "has_more": False},
        ])
        client = pm.MetadataClient("fixture", request=lambda *args, **kwargs: next(pages))
        pm.resolve_table(client.listing("tables"))
        repeating = pm.MetadataClient("fixture", request=lambda *args, **kwargs: {"items": [], "has_more": True, "page_token": "same"})
        with self.assertRaisesRegex(pm.SafeError, "BAD_PAGINATION"):
            repeating.listing("tables")

    def test_workflow_exposes_only_explicit_manual_live_execution(self):
        root = pathlib.Path(__file__).resolve().parents[2]
        text = (root / ".github/workflows/feishu-project-management-setup.yml").read_text()
        header = text.split("permissions:", 1)[0]
        self.assertIn("  pull_request:", header)
        self.assertIn("  workflow_dispatch:", header)
        self.assertIn("default: plan", header)
        for event in ("schedule", "push", "workflow_run"):
            self.assertNotIn("  " + event + ":", header)
        self.assertIn("if: ${{ github.ref == 'refs/heads/main' && github.event_name == 'workflow_dispatch' && needs.offline.result == 'success' }}", text)
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", text)
        self.assertIn('project_management_setup.py --mode "$SETUP_MODE"', text)


if __name__ == "__main__":
    unittest.main()
