"""Read-only V3 goal/AST/HTTP tests. Never execute agent-authored code locally."""
import io
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from automation.goal_loop.controller import (
    Hold, acceptance_check_name, apply_proposal, load_goal, run,
    ollama_proposal, unsafe_ci_gate_failed, v3_compact_prompt,
    v3_output_json_schema,
)
from automation.goal_loop.source_quality import (
    SourceQualityError, validate_v3_source,
)


SAFE_FIXTURE = '''"""Synthetic hand-authored file for AST-only tests."""

def summarize_quotes(rows):
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    seen = set()
    totals = {}
    accepted = 0
    rejected = 0
    for row in rows:
        if not isinstance(row, dict):
            rejected += 1
            continue
        q = row.get("quote_id")
        product = row.get("product_line")
        count = row.get("sample_count")
        price = row.get("unit_price_krw")
        if (not isinstance(q, str) or not q.strip()
                or not isinstance(product, str) or not product.strip()
                or type(count) is not int or count < 1
                or type(price) is not int or price < 0):
            rejected += 1
            continue
        q = q.strip()
        if q in seen:
            rejected += 1
            continue
        seen.add(q)
        key = product.strip().upper()
        totals[key] = totals.get(key, 0) + count * price
        accepted += 1
    return {"totals_krw": dict(sorted(totals.items())),
            "accepted": accepted, "rejected": rejected}
'''


class V3QualityContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.goal = {
            "version": 1, "goal_id": "pilot-quote-summary-v3",
            "document": "docs/automation/goal-loop-pilot-v3.md",
            "repo": "kimtk94/Codex", "base_branch": "main",
            "allowed_files": ["automation/goal_loop/pilot_quote_summary_v3.py"],
            "verify": [["python", "-m", "unittest",
                        "automation.goal_loop.pilot_acceptance_v3", "-v"]],
            "required_checks": ["goal-loop-controller-tests",
                                "pilot-acceptance-v3", "main-write-guard"],
            "max_iterations": 2, "max_minutes": 35,
            "model": "qwen25coder3b-16k",
        }
        for path, content in (
            (self.goal["document"], "# Synthetic V3 — no private data\n"),
            (self.goal["allowed_files"][0],
             "def summarize_quotes(rows):\n    return {'totals_krw': {}, 'accepted': 0, 'rejected': 0}\n"),
            ("automation/goal_loop/pilot_acceptance_v3.py", "# read-only fixture\n"),
        ):
            dest = self.root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        self.config = self.root / "v3.json"
        self.save(self.goal)

    def save(self, goal):
        self.config.write_text(json.dumps(goal), encoding="utf-8")

    def loaded(self):
        return load_goal(self.root, "v3.json")

    def test_independent_goal_requires_exact_v3_gate(self):
        goal = self.loaded()
        self.assertEqual(acceptance_check_name(goal), "pilot-acceptance-v3")
        self.assertFalse(unsafe_ci_gate_failed(goal, [
            {"name": "pilot-acceptance-v3", "app_slug": "github-actions",
             "conclusion": "failure"}
        ]))
        self.assertTrue(unsafe_ci_gate_failed(goal, [
            {"name": "main-write-guard", "app_slug": "github-actions",
             "conclusion": "failure"}
        ]))

    def test_v3_goal_binding_cannot_weaken_scope(self):
        variations = (
            {"document": "docs/automation/goal-loop-pilot-v2.md"},
            {"allowed_files": ["automation/goal_loop/pilot_target_v2.py"]},
            {"allowed_files": ["automation/goal_loop/pilot_acceptance_v3.py"]},
            {"verify": [["python", "-m", "unittest",
                         "automation.goal_loop.pilot_acceptance_v2", "-v"]]},
            {"required_checks": ["goal-loop-controller-tests",
                                 "pilot-acceptance-v2", "main-write-guard"]},
            {"max_iterations": 3},
            {"max_minutes": 50},
        )
        for variation in variations:
            with self.subTest(variation=variation):
                self.save({**self.goal, **variation})
                with self.assertRaises(Hold):
                    self.loaded()
        self.save(self.goal)

    def test_static_fixture_is_valid_without_running_any_code(self):
        report = validate_v3_source(SAFE_FIXTURE)
        self.assertTrue(report["module_level_safe"])
        self.assertEqual(report["function"], "summarize_quotes")

    def test_v3_rejects_untrusted_module_side_effects(self):
        samples = (
            SAFE_FIXTURE + "\nassert True\n",
            "import os\n" + SAFE_FIXTURE,
            "open('private', 'w')\n" + SAFE_FIXTURE,
            "RESULT = summarize_quotes([])\n" + SAFE_FIXTURE,
            SAFE_FIXTURE + "\nclass Test: pass\n",
            SAFE_FIXTURE + "\ndef helper(): pass\n",
        )
        for sample in samples:
            with self.subTest(sample=sample[-60:]), self.assertRaises(SourceQualityError):
                validate_v3_source(sample)

    def test_v3_rejects_dynamic_execution_imports_and_bad_signature(self):
        for source in (
            "def summarize_quotes(rows):\n    import os\n    return {}\n",
            "def summarize_quotes(rows):\n    return eval('1')\n",
            "def summarize_quotes(rows):\n    open('secret', 'w')\n    return {}\n",
            "def summarize_quotes(rows):\n    def inner(): return 1\n    return {}\n",
            "def summarize_quotes(rows, optional=0):\n    return {}\n",
            "def summarize_quotes(rows):\n    pass\n",
        ):
            with self.subTest(source=source), self.assertRaises(SourceQualityError):
                validate_v3_source(source)

    def test_invalid_source_rejected_before_any_file_write(self):
        goal = self.loaded()
        path = goal["allowed_files"][0]
        target = self.root / path
        old = target.read_text(encoding="utf-8")
        with self.assertRaisesRegex(Hold, "MODEL_V3_SOURCE_QUALITY"):
            apply_proposal(self.root, goal, {
                "path": path, "content": SAFE_FIXTURE + "\nassert True\n",
            })
        self.assertEqual(target.read_text(encoding="utf-8"), old)

    def test_valid_source_passes_static_gate_without_execution(self):
        goal = self.loaded()
        path = goal["allowed_files"][0]
        self.assertEqual(apply_proposal(self.root, goal, {
            "path": path, "content": SAFE_FIXTURE,
        }), path)
        self.assertEqual((self.root / path).read_text(encoding="utf-8"),
                         SAFE_FIXTURE)

    def test_v3_prompt_is_compact_and_excludes_untrusted_ci_logs(self):
        goal = self.loaded()
        path = goal["allowed_files"][0]
        previous = {"verdict": "FAIL", "checks": [{
            "name": "pilot-acceptance-v3", "conclusion": "failure",
            "untrusted_log_excerpt": "SECRET_LOG_MUST_NOT_LEAK",
        }]}
        msg = v3_compact_prompt(self.root, goal, {
            "previous_checks": previous,
            "failures": [{"untrusted_log_excerpt": "SECRET_LOG_MUST_NOT_LEAK"}],
        }, {path: "def summarize_quotes(rows):\n    return {}\n"})
        self.assertLess(len(msg), 5000)
        self.assertIn("unit_price_krw", msg)
        self.assertIn("sample_count", msg)
        self.assertIn("VAT EXCLUDED", msg)
        self.assertNotIn("SECRET_LOG_MUST_NOT_LEAK", msg)

    def test_v3_failed_pr_feedback_is_specific_and_does_not_leak_raw_logs(self):
        """Real Qwen PR #1025 failure patterns become compact instructions."""
        goal = self.loaded()
        path = goal["allowed_files"][0]
        failed_source = (
            "def summarize_quotes(rows):\n"
            "    accepted = 0\n"
            "    for row in rows:\n"
            "        quote_id = row['quote_id'].strip()\n"
            "        if not isinstance(row['sample_count'], int):\n"
            "            continue\n"
            "    return {'totals_krw': {}, 'accepted': accepted, 'rejected': 0}\n"
        )
        feedback = {
            "no_change_count": 1,
            "previous_checks": {
                "verdict": "FAIL",
                "checks": [{"name": "pilot-acceptance-v3",
                            "conclusion": "failure",
                            "untrusted_log_excerpt": "UNTRUSTED_LOG_SECRET_SENTINEL"}],
            },
            "failures": [{"untrusted_log_excerpt": "UNTRUSTED_LOG_SECRET_SENTINEL"}],
        }
        prompt = v3_compact_prompt(self.root, goal, feedback, {path: failed_source})
        self.assertLess(len(prompt), 5000)
        for expected in (
            "Increment accepted", "BEFORE calling strip", "type(sample_count) is int",
            "wrongly accepts bool", "dict(sorted(totals.items()))",
            "edge_case_output", "no_change_count", "different and improved",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, prompt)
        self.assertNotIn("UNTRUSTED_LOG_SECRET_SENTINEL", prompt)
        self.assertIn('"no_change_count":1', prompt)
        self.assertIn('"accepted":1,"rejected":3', prompt)

    def test_v3_no_change_without_ci_failure_still_supplies_repair_guidance(self):
        goal = self.loaded()
        path = goal["allowed_files"][0]
        prompt = v3_compact_prompt(self.root, goal, {
            "no_change_count": 2, "previous_checks": {"verdict": "TIMEOUT"},
        }, {path: "def summarize_quotes(rows):\n    return {}\n"})
        self.assertIn("Increment accepted", prompt)
        self.assertIn('"no_change_count":2', prompt)

    def test_v3_enforces_exact_ollama_schema_without_executing_model_code(self):
        schema = v3_output_json_schema()
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["required"], ["path", "content"])
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["properties"]), {"path", "content"})
        self.assertEqual(schema["properties"]["path"]["enum"],
                         ["automation/goal_loop/pilot_quote_summary_v3.py"])
        self.assertEqual(schema["properties"]["content"]["type"], "string")

    def test_v3_schema_error_retry_consumes_budget_without_git_push(self):
        goal = self.loaded()
        actions = []
        def fake_cmd(args, *unused, **kwargs):
            actions.append(args[:])
            if args[:4] == ["git", "remote", "get-url", "origin"]:
                return {"ok": True, "code": 0,
                        "output": "https://github.com/kimtk94/Codex.git\n"}
            return {"ok": True, "code": 0, "output": ""}
        with patch("pathlib.Path.home", return_value=self.root), \
             patch("automation.goal_loop.controller.shutil.which",
                   return_value="git"), \
             patch("automation.goal_loop.controller.require_local_model"), \
             patch("automation.goal_loop.controller.run_cmd",
                   side_effect=fake_cmd), \
             patch("automation.goal_loop.controller.ollama_proposal",
                   return_value={"code": "not-allowed", "explanation": "wrong"}) as model:
            result = run(self.root, goal)
        self.assertEqual(result["state"], "MODEL_FORMAT_HOLD")
        self.assertEqual(len(result["evidence"]["iterations"]), 2)
        self.assertTrue(all(item.get("format_rejected")
                            for item in result["evidence"]["iterations"]))
        self.assertTrue(all(item["reason"] == "MODEL_OUTPUT_SCHEMA"
                            for item in result["evidence"]["iterations"]))
        self.assertEqual(model.call_count, 2)
        self.assertFalse(any(cmd[:2] == ["git", "push"] for cmd in actions))
        self.assertFalse(any(cmd[:3] == ["gh", "pr", "create"] for cmd in actions))

    def test_v3_invalid_json_retry_remains_bounded(self):
        goal = self.loaded()
        def fake_cmd(args, *unused, **kwargs):
            if args[:4] == ["git", "remote", "get-url", "origin"]:
                return {"ok": True, "code": 0,
                        "output": "https://github.com/kimtk94/Codex.git\n"}
            return {"ok": True, "code": 0, "output": ""}
        with patch("pathlib.Path.home", return_value=self.root), \
             patch("automation.goal_loop.controller.shutil.which",
                   return_value="git"), \
             patch("automation.goal_loop.controller.require_local_model"), \
             patch("automation.goal_loop.controller.run_cmd",
                   side_effect=fake_cmd), \
             patch("automation.goal_loop.controller.ollama_proposal",
                   side_effect=Hold("MODEL_INVALID_JSON")):
            result = run(self.root, goal)
        self.assertEqual(result["state"], "MODEL_FORMAT_HOLD")
        self.assertEqual(result["evidence"]["last_format_rejection"],
                         "MODEL_INVALID_JSON")
        self.assertEqual(len(result["evidence"]["iterations"]), 2)

    def test_v3_explicit_last_format_rejection_is_in_prompt_without_raw_output(self):
        goal = self.loaded()
        path = goal["allowed_files"][0]
        prompt = v3_compact_prompt(self.root, goal, {
            "last_format_rejection": "MODEL_OUTPUT_SCHEMA",
            "previous_checks": {"verdict": "FAIL"},
        }, {path: "def summarize_quotes(rows):\n    return {}\n"})
        self.assertIn('"last_format_rejection":"MODEL_OUTPUT_SCHEMA"', prompt)
        self.assertIn("EXACTLY TWO fields", prompt)
        self.assertIn("BOTH string values", prompt)
        self.assertNotIn("some raw malicious generated code", prompt)

    def test_v3_model_request_limited_to_4096_context_1024_generated_tokens(self):
        goal = self.loaded()
        reply = {"message": {"content": json.dumps({
            "path": goal["allowed_files"][0], "content": SAFE_FIXTURE,
        })}, "eval_count": 250, "prompt_eval_count": 400}
        with patch("automation.goal_loop.controller.select_local_model",
                   return_value="qwen25coder3b-16k"), \
             patch("automation.goal_loop.controller.urllib.request.urlopen",
                   return_value=io.BytesIO(json.dumps(reply).encode())) as url:
            proposal = ollama_proposal(self.root, goal, {
                "previous_checks": {"verdict": "FAIL"}
            })
        self.assertEqual(proposal["content"], SAFE_FIXTURE)
        body = json.loads(url.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(body["options"]["num_ctx"], 4096)
        self.assertEqual(body["options"]["num_predict"], 1024)
        self.assertEqual(body["format"], v3_output_json_schema())
        self.assertEqual(body["keep_alive"], "5m")
        self.assertLess(len(body["messages"][1]["content"]), 5000)
        self.assertEqual(url.call_args.kwargs["timeout"], 200)


if __name__ == "__main__":
    unittest.main()
