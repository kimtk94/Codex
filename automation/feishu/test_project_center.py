"""Offline synthetic tests: project risk and native page ownership."""
import copy
import json
import unittest
import native_project_center as page
from project_center_rules import derive_signals, SIGNAL_FIELDS


def row(**overrides):
    return {"Workflow Lane": "PRODUCTION_ACTIVE", "Current Stage": "Sequencing",
            "Progress Phase": "04 시퀀싱", "SIF State": "NOT_VERIFIED", **overrides}


class RiskTests(unittest.TestCase):
    def test_explicit_stage_high(self):
        for stage in ("Abnormal", "Resending Sample", "Sample QC Failed", "Lib QC Failed"):
            self.assertEqual(derive_signals(row(**{"Current Stage": stage}))["PM Risk"], "HIGH")
        self.assertEqual(derive_signals(row(**{"Current Stage": "not abnormal"}))["PM Risk"], "MONITOR")

    def test_late_sif_not_blocker(self):
        self.assertEqual(derive_signals(row())["PM Risk"], "MONITOR")

    def test_early_sif_and_prepayment(self):
        early = row(**{"Progress Phase": "01 계약/SIF", "Current Stage": "SIF requested"})
        self.assertEqual(derive_signals(early)["PM Issue"], "SIF_EVIDENCE_REVIEW")
        early["Prepayment"] = "YES"
        self.assertEqual(derive_signals(early)["PM Risk"], "MONITOR")

    def test_blockers(self):
        for stage in ("Awaiting Feedback(Project Start)", "Awaiting Feedback(BI form)",
                      "Waiting PO/payment", "Add-seq"):
            self.assertEqual(derive_signals(row(**{"Current Stage": stage}))["PM Risk"], "MEDIUM")

    def test_unknown_not_normal(self):
        self.assertEqual(derive_signals({})["PM Risk"], "UNKNOWN")
        self.assertEqual(derive_signals(row(**{"Progress Phase": "진행 단계 미확인"}))["PM Risk"], "UNKNOWN")
        self.assertEqual(derive_signals(row(**{"Quote Match State": "MULTIPLE_QUOTE_REVIEW"}))["PM Risk"], "UNKNOWN")

    def test_partial_completion_high(self):
        self.assertEqual(derive_signals(row(**{"Completion Evidence": "PARTIAL_SUBPROJECT_COMPLETION_REVIEW"}))["PM Risk"], "HIGH")

    def test_payment_scope_and_conflict(self):
        item = row(**{"Workflow Lane": "PAYMENT_FOLLOWUP",
                      "Payment State": "SOURCE_RECEIPT_RECHECK_REQUIRED"})
        self.assertEqual(derive_signals(item)["PM Risk"], "UNKNOWN")
        item["Payment Owner Scope"] = "MY_VERIFIED"
        self.assertEqual(derive_signals(item)["PM Risk"], "HIGH")
        item["Payment State"] = "RECEIPT_NOT_VERIFIED"
        self.assertEqual(derive_signals(item)["PM Risk"], "MEDIUM")

    def test_archive_and_no_manual_writes(self):
        item = row(**{"Workflow Lane": "PAID_ARCHIVED", "관리 상태": "진행 중",
                      "관리 메모": "manual", "다음 확인일": "2026-11-25"})
        before = copy.deepcopy(item)
        values = derive_signals(item)
        self.assertEqual(values["PM Risk"], "CLOSED")
        self.assertEqual(set(values), set(SIGNAL_FIELDS))
        self.assertEqual(item, before)


class FakeCLI:
    def __init__(self):
        self.specs = page.build_specs()
        self.dashboard = None
        self.blocks = {}
        self.calls = []
        self.bad_type = False
        self.ignore_create = False
        self.preserve = {"dashboard_id": "dsh_existing", "name": "Different page"}
        self.other = []

    @property
    def writes(self):
        return [call for call in self.calls if call[0].endswith("-create")]

    def __call__(self, *args):
        self.calls.append(args)
        op = args[0]
        vals = dict(zip(args[1::2], args[2::2]))
        assert vals["--base-token"] == page.BASE
        if "--dashboard-id" in vals:
            assert self.dashboard and vals["--dashboard-id"] == self.dashboard["dashboard_id"]
        if op == "+table-list":
            return {"tables": [{"id": page.TABLE_ID, "name": page.TABLE}], "total": 1}
        if op == "+field-list":
            from native_overview_dashboard import required_fields
            fields = required_fields([x for x in self.specs if x["type"] != "text"])[page.TABLE]
            result = [{"id": "fld" + str(i), "name": n, "type": t}
                      for i, (n, t) in enumerate(fields.items())]
            if self.bad_type:
                result[0]["type"] = "number"
            return {"fields": result, "total": len(result)}
        if op == "+dashboard-list":
            return {"items": [self.preserve, *self.other] + ([self.dashboard] if self.dashboard else []),
                    "has_more": False}
        if op == "+dashboard-create":
            assert vals["--name"] == page.TITLE
            self.dashboard = {"dashboard_id": "blkNew", "name": page.TITLE}
            return {"dashboard": self.dashboard}
        if op == "+dashboard-get":
            return {"dashboard": copy.deepcopy(self.dashboard)}
        if op == "+dashboard-block-list":
            return {"items": [copy.deepcopy(x) for x in self.blocks.values()], "has_more": False}
        if op == "+dashboard-block-get":
            return {"block": copy.deepcopy(self.blocks[vals["--block-id"]])}
        if op == "+dashboard-block-create":
            bid = "cht" + str(len(self.blocks))
            if not self.ignore_create:
                self.blocks[bid] = {"block_id": bid, "name": vals["--name"], "type": vals["--type"],
                                    "data_config": json.loads(vals["--data-config"]),
                                    "position": json.loads(vals.get("--position", "{}"))}
            return {"block": {"block_id": bid, "name": vals["--name"], "type": vals["--type"]}}
        raise AssertionError("forbidden call: " + op)


class PageTests(unittest.TestCase):
    def test_project_only_and_owner_scoped(self):
        for s in page.build_specs():
            if s["type"] == "text":
                continue
            c = s["data_config"]
            self.assertEqual(c["table_name"], page.TABLE)
            f = {x["field_name"]: x.get("value") for x in c["filter"]["conditions"]}
            if f["Workflow Lane"] != "PRODUCTION_ACTIVE":
                self.assertEqual(f["Payment Owner Scope"], "MY_VERIFIED")
            else:
                self.assertNotIn("Payment Owner Scope", f)
            self.assertNotEqual(s["type"], "ranking")

    def test_current_and_carryover_are_disjoint_and_archive_is_historical(self):
        specs = {s["name"]:s for s in page.build_specs()}
        def filters(name):
            return specs[name]["data_config"]["filter"]["conditions"]
        for name in ("보드상 진행 중", "자동 위험 HIGH", "내 담당 결제 확인",
                     "현재 입력 연결 검토", "현재 입력 상태 근거", "내 담당 미수금 (M KRW)"):
            self.assertIn(page.cond(page.COVERAGE, page.CURRENT), filters(name))
        for name in ("진행 이전 원본 보존", "내 담당 결제 이전 원본 보존"):
            self.assertIn(page.cond(page.COVERAGE, page.CARRYOVER), filters(name))
        self.assertFalse(any(c["field_name"]==page.COVERAGE
                             for c in filters("내 담당 입금 검증 보관 기록")))
        self.assertIn(page.cond(page.COVERAGE, operator="isEmpty"), filters("진행 기록 미분류"))

    def test_text_guidance_uses_only_supported_markdown(self):
        note = page.navigation_note()
        self.assertNotIn("](", note)
        self.assertIn("01 오늘 확인", note)
        self.assertIn("04 위험 검토", note)

    def test_conflicting_dashboard_identifiers_fail(self):
        with self.assertRaisesRegex(RuntimeError, "DASHBOARD_ID_CONFLICT"):
            page.dashboard_identity({"id": "one", "dashboard_id": "two"})

    def test_plan_read_only(self):
        cli = FakeCLI()
        result = page.reconcile("plan", runner=cli)
        self.assertEqual(result["missing"], len(cli.specs))
        self.assertEqual(cli.writes, [])

    def test_create_verify_idempotent(self):
        cli = FakeCLI()
        result = page.reconcile("apply", runner=cli)
        self.assertEqual(result["writes"], 1 + len(cli.specs))
        self.assertFalse(result["layout_review"])
        self.assertEqual(cli.preserve["name"], "Different page")
        self.assertEqual(page.reconcile("verify", runner=cli)["writes"], 0)
        writes_before = len(cli.writes)
        self.assertEqual(page.reconcile("apply", "blkNew", cli)["writes"], 0)
        self.assertEqual(len(cli.writes), writes_before)

    def test_unreviewed_existing_id_rejected(self):
        cli = FakeCLI()
        cli.dashboard = {"dashboard_id": "blkNew", "name": page.TITLE}
        with self.assertRaisesRegex(RuntimeError, "REVIEW_EXISTING_ID"):
            page.reconcile("apply", runner=cli)
        self.assertEqual(cli.writes, [])

    def test_duplicate_title_and_schema_drift_stop_writes(self):
        cli = FakeCLI()
        cli.dashboard = {"dashboard_id": "blkNew", "name": page.TITLE}
        cli.other = [{"dashboard_id": "blkDuplicate", "name": page.TITLE}]
        with self.assertRaisesRegex(RuntimeError, "DUPLICATE_TITLE"):
            page.reconcile("apply", runner=cli)
        self.assertEqual(cli.writes, [])
        cli = FakeCLI()
        cli.bad_type = True
        with self.assertRaisesRegex(RuntimeError, "SOURCE_FIELD_TYPE"):
            page.reconcile("apply", runner=cli)
        self.assertEqual(cli.writes, [])

    def test_apply_does_not_modify_drift_or_user_blocks(self):
        cli = FakeCLI()
        page.reconcile("apply", runner=cli)
        cli.blocks["chtUser"] = {"block_id": "chtUser", "name": "User note", "type": "text"}
        self.assertEqual(page.reconcile("apply", "blkNew", cli)["writes"], 0)
        cli.blocks["cht1"]["data_config"]["filter"]["conditions"][0]["value"] = "PAID_ARCHIVED"
        before = len(cli.writes)
        with self.assertRaisesRegex(RuntimeError, "CONFIG_REVIEW"):
            page.reconcile("apply", "blkNew", cli)
        self.assertEqual(len(cli.writes), before)
        self.assertIn("chtUser", cli.blocks)

    def test_missing_creation_readback_fails(self):
        cli = FakeCLI()
        cli.ignore_create = True
        with self.assertRaisesRegex(RuntimeError, "READBACK_FAILED"):
            page.reconcile("apply", runner=cli)
        self.assertEqual(len(cli.writes), 2)  # page and only the first block

    def test_recovery_preserves_layout(self):
        cli = FakeCLI()
        page.reconcile("apply", runner=cli)
        old = copy.deepcopy(cli.blocks["cht0"])
        cli.blocks.pop("cht" + str(len(cli.specs) - 1))
        result = page.reconcile("apply", "blkNew", cli)
        self.assertEqual(result["writes"], 1)
        self.assertEqual(cli.blocks["cht0"], old)
        self.assertNotIn("--position", cli.writes[-1])


if __name__ == "__main__":
    unittest.main()
