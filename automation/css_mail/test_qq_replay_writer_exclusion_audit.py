"""Synthetic-only workflow writer scope checks; no API calls or credentials."""
import json
import unittest
from automation.css_mail.qq_replay_writer_exclusion_audit import (
    assess, LEGACY_WRITER, SAFE_WRITER, MAIN_WORKFLOW, TARGET
)


def baseline():
    main = ("name: QQ Backfill\non: workflow_dispatch\njobs:\n"
            "  offline-tests:\n    runs-on: ubuntu-latest\n"
            "  safe-preview:\n    env:\n"
            "      BACKFILL_WRITE_MODE: 'PREVIEW'\n"
            "    run: python3 -m py_compile " + SAFE_WRITER)
    year2025 = ("name: QQ 2025\njobs:\n  backfill:\n"
                "    env:\n      BACKFILL_YEAR: '2025'\n"
                "    run: python3 " + LEGACY_WRITER)
    scripts = {SAFE_WRITER: (
                   'def guard_2026_stage_apply(mode,year,tab):\n'
                   '    if mode=="APPLY" and year==2026:\n'
                   '        raise RuntimeError("QQ_2026_APPLY_HARD_HOLD_WRITER_EXCLUSION_UNVERIFIED")\n'
                   'guard_2026_stage_apply(mode,requested_year,TAB)\n'
                   'def google_sheet_scopes(mode):\n'
                   '    return ["https://www.googleapis.com/auth/spreadsheets.readonly"]\n'
                   'scopes=google_sheet_scopes(mode)\n'
                   'if mode == "APPLY": raise RuntimeError("GATE")'),
               LEGACY_WRITER:(
                    'def guard_legacy_2026_target(year,tab):\n'
                    '    raise RuntimeError("QQ_LEGACY_2026_APPLY_HARD_HOLD_UNVERIFIED_WRITER")\n'
                    'guard_legacy_2026_target(requested_year,TAB)\n'
                    'def main(): pass')}
    return {MAIN_WORKFLOW: main, "qq-2025-invoice-backfill.yml": year2025}, scripts


class WriterBoundaryTests(unittest.TestCase):
    def test_safe_known_workflows_still_hold_unproven_exclusion(self):
        workflows, scripts = baseline()
        r = assess(workflows, scripts)
        self.assertEqual(r["blocking_rule_count"], 0)
        self.assertEqual(r["bounded_2025_legacy_entries"], 1)
        self.assertEqual(r["writer_exclusion_verified"], 0)
        self.assertEqual(r["atomic_cas_verified"], 0)
        self.assertEqual(r["status"], "HOLD")
        self.assertNotIn(TARGET, json.dumps(r))
    def test_source_guard_removed_is_detected(self):
        workflows,scripts=baseline()
        scripts[SAFE_WRITER]=scripts[SAFE_WRITER].replace(
            "guard_2026_stage_apply(mode,requested_year,TAB)",
            "pass  # guard bypassed")
        result=assess(workflows,scripts)
        self.assertIn("2026_SOURCE_HARD_HOLD_MISSING",result["blocking_rule_codes"])
        self.assertEqual(result["writer_exclusion_verified"],0)

    def test_preview_writable_scope_or_missing_binding_is_blocked(self):
        workflows,scripts=baseline()
        scripts[SAFE_WRITER]=scripts[SAFE_WRITER].replace(
            "scopes=google_sheet_scopes(mode)",
            'scopes=["https://www.googleapis.com/auth/spreadsheets"]')
        report=assess(workflows,scripts)
        self.assertIn("PREVIEW_READONLY_OAUTH_SCOPE_MISSING",
                      report["blocking_rule_codes"])
        self.assertEqual(report["stage_writes"],0)

    def test_legacy_hard_hold_removed_is_detected(self):
        workflows,scripts=baseline()
        scripts[LEGACY_WRITER]=scripts[LEGACY_WRITER].replace(
            "guard_legacy_2026_target(requested_year,TAB)","pass")
        result=assess(workflows,scripts)
        self.assertIn("LEGACY_2026_SOURCE_HARD_HOLD_MISSING",
                      result["blocking_rule_codes"])

    def test_2026_apply_job_is_detected(self):
        workflows, scripts = baseline()
        workflows[MAIN_WORKFLOW] += (
            "\n  backfill:\n      BACKFILL_WRITE_MODE: 'APPLY'")
        r=assess(workflows, scripts)
        self.assertIn("APPLY_WORKFLOW_ENABLED",r["blocking_rule_codes"])
    def test_secondary_stage_reference_blocks(self):
        workflows, scripts = baseline()
        workflows["other.yml"] = "BACKFILL_TAB: '" + TARGET + "'"
        r=assess(workflows, scripts)
        self.assertEqual(r["independent_2026_stage_references"],1)
        self.assertIn("INDEPENDENT_2026_STAGE_REFERENCE",r["blocking_rule_codes"])
    def test_legacy_without_fixed_year_is_unbounded(self):
        workflows, scripts = baseline()
        workflows["unknown.yml"] = "run: python3 " + LEGACY_WRITER
        r=assess(workflows, scripts)
        self.assertEqual(r["unbounded_legacy_entries"],1)
        self.assertIn("LEGACY_WRITER_NOT_YEAR_PINNED",r["blocking_rule_codes"])
    def test_missing_explicit_preview_is_fatal(self):
        workflows, scripts = baseline()
        workflows[MAIN_WORKFLOW] = workflows[MAIN_WORKFLOW].replace(
            "'PREVIEW'", "'APPLY'")
        r=assess(workflows, scripts)
        self.assertIn("PREVIEW_NOT_PINNED",r["blocking_rule_codes"])
    def test_missing_sources_or_workflow_fail_closed(self):
        workflows, scripts = baseline()
        with self.assertRaisesRegex(ValueError,"REPLAY_2026_WORKFLOW_MISSING"):
            assess({}, scripts)
        with self.assertRaisesRegex(ValueError,"REPLAY_BACKFILL_WRITER_SOURCE_MISSING"):
            assess(workflows, {})
    def test_unknown_future_writers_cannot_be_authorized(self):
        workflows, scripts = baseline()
        workflows["unknown-script.yml"] = "run: python3 dynamic_entrypoint.py"
        r=assess(workflows,scripts)
        self.assertEqual(r["writer_exclusion_verified"],0)
        self.assertEqual(r["cross_workflow_lock_verified"],0)
        self.assertEqual(r["approval_authenticated"],0)
        self.assertEqual(r["stage_writes"],0)


if __name__ == "__main__":
    unittest.main()
