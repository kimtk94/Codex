#!/usr/bin/env python3
"""Offline event-matrix contracts for Feishu workflow concurrency."""
import ast
import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
PRODUCTION_GROUPS = {
    "qq-mail-feishu-sync.yml": "qq-feishu-mail-ingest",
    "feishu-mail-feed-periods.yml": "qq-feishu-mail-ingest",
    "feishu-quote-report-email-sync.yml": "sales-weekly-writer",
    "feishu-automation-run-history.yml": "feishu-automation-run-history",
    "feishu-lead-action-delta.yml": "isolated-lead-feishu-mail-description",
    "feishu-mail-identity-2026.yml": "qq-feishu-identity",
    "feishu-mail-link-review-2026.yml": "qq-feishu-mail-link-review",
    "feishu-native-dashboard.yml": "feishu-native-dashboard",
    "feishu-native-kpi-dashboard.yml": "feishu-native-kpi-dashboard",
    "feishu-native-sales-home.yml": "feishu-native-sales-home",
    "feishu-native-sales-trends.yml": "feishu-native-sales-trends",
    "feishu-payment-audit.yml": "feishu-payment-audit",
    "feishu-post-backfill-refresh.yml": "feishu-qq-post-backfill-refresh",
    "feishu-project-quote-operations.yml": "feishu-project-quote-operations",
    "feishu-sfdc-command-queue.yml": "feishu-sfdc-queue-bridge",
    "feishu-sfdc-operations.yml": "feishu-sfdc-operations",
    "feishu-sources-unified.yml": "feishu-sources-payment-online-monthly-unified",
    "feishu-x-project-registry.yml": "feishu-x-sam-lineage",
    "lead-outreach-chain.yml": "isolated-lead-feishu-mail-description",
    "sif-evidence-tracker.yml": "sif-evidence-tracker-feishu",
}


def read_workflow(filename):
    """Read the small YAML subset used by these policy fields, without imports."""
    result = {"jobs": {}, "concurrency": {}}
    section = None
    job = None
    for line in (WORKFLOWS / filename).read_text(encoding="utf-8").splitlines():
        if line.startswith("name:"):
            result["name"] = line.split(":", 1)[1].strip().strip("'\"")
        if line and not line.startswith((" ", "#")):
            section = line.removesuffix(":")
        if section == "concurrency":
            match = re.fullmatch(r"  ([\w-]+):\s*(.*)", line)
            if match:
                result["concurrency"][match[1]] = match[2]
        if section == "jobs":
            match = re.fullmatch(r"  ([\w-]+):", line)
            if match:
                job = result["jobs"].setdefault(match[1], {})
            match = re.fullmatch(r"    (if|needs|environment):\s*(.*)", line)
            if match and job is not None:
                job[match[1]] = match[2]
    return result


TOKEN = re.compile(r"\s*('(?:[^']|'')*'|[A-Za-z_][\w.]*|\d+|==|!=|&&|\|\||[(),!])")


def evaluate(value, context, expression=False):
    """Interpret the actual checked-in expressions; reject unsupported syntax.

    This deliberately small offline interpreter handles constants, context
    lookups, comparisons, short-circuit booleans and format(), the constructs
    used by these concurrency policies and their existing job gates.
    """
    value = value.strip()
    if value.startswith("${{") and value.endswith("}}"):
        value = value[3:-2].strip()
        expression = True
    if not expression:
        return {"true": True, "false": False}.get(value, value.strip("'\""))
    translated = []
    offset = 0
    while offset < len(value):
        token = TOKEN.match(value, offset)
        if not token:
            raise AssertionError("Unsupported workflow expression: " + value[offset:])
        item = token[1]
        offset = token.end()
        if item.startswith("'"):
            translated.append(repr(item[1:-1].replace("''", "'")))
        elif item in ("true", "false", "null"):
            translated.append({"true": "True", "false": "False", "null": "None"}[item])
        elif item in ("&&", "||", "!"):
            translated.append({"&&": "and", "||": "or", "!": "not"}[item])
        elif item == "format" or item in ("==", "!=", "(", ")", ",") or item.isdigit():
            translated.append(item)
        else:
            resolved = context
            for part in item.split("."):
                resolved = resolved.get(part) if isinstance(resolved, dict) else None
            translated.append(repr(resolved))

    def visit(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BoolOp):
            result = visit(node.values[0])
            for operand in node.values[1:]:
                if isinstance(node.op, ast.And) and not result:
                    return result
                if isinstance(node.op, ast.Or) and result:
                    return result
                result = visit(operand)
            return result
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not visit(node.operand)
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            left, right = visit(node.left), visit(node.comparators[0])
            if isinstance(left, str) and isinstance(right, str):
                left, right = left.casefold(), right.casefold()
            if isinstance(node.ops[0], ast.Eq):
                return left == right
            if isinstance(node.ops[0], ast.NotEq):
                return left != right
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "format":
            args = [visit(arg) for arg in node.args]
            return args[0].format(*args[1:])
        raise AssertionError("Unsupported workflow expression node: " + ast.dump(node))

    return visit(ast.parse(" ".join(translated), mode="eval").body)


def context(name, event, pr=None):
    return {
        "github": {
            "workflow": name,
            "event_name": event,
            "run_id": 1,
            "sha": "old-test-commit",
            "repository": "kimtk94/Codex",
            "event": {
                "pull_request": {"number": pr} if pr is not None else None,
                "workflow_run": {"conclusion": "success", "head_branch": "main"},
                "head_commit": {"message": "deploy-feishu-lead-delta"},
            },
        },
        "inputs": {"apply": True, "apply_staging": True},
        "vars": {"FEISHU_SFDC_BRIDGE_ENABLED": "true", "JIIN_CRM_READY": "true"},
        "needs": {},
    }


class WorkflowPRConcurrencyTests(unittest.TestCase):
    def test_production_event_groups_and_cancellation_are_preserved(self):
        for filename, expected_group in PRODUCTION_GROUPS.items():
            workflow = read_workflow(filename)
            for event in ("schedule", "push", "workflow_dispatch", "workflow_run"):
                with self.subTest(workflow=filename, event=event):
                    ctx = context(workflow["name"], event)
                    self.assertEqual(evaluate(workflow["concurrency"]["group"], ctx), expected_group)
                    self.assertIs(evaluate(workflow["concurrency"]["cancel-in-progress"], ctx), False)
                    self.assertNotIn("queue", workflow["concurrency"])

    def test_pr_groups_cannot_replace_production_or_other_workflow_prs(self):
        production_groups = {value.casefold() for value in PRODUCTION_GROUPS.values()}
        seen = set()
        for filename in PRODUCTION_GROUPS:
            workflow = read_workflow(filename)
            for pr in (825, 1043):
                with self.subTest(workflow=filename, pr=pr):
                    ctx = context(workflow["name"], "pull_request", pr)
                    group = evaluate(workflow["concurrency"]["group"], ctx).casefold()
                    self.assertNotIn(group, production_groups)
                    self.assertNotIn(group, seen)
                    newer = context(workflow["name"], "pull_request", pr)
                    newer["github"].update(run_id=2, sha="new-test-commit")
                    self.assertEqual(group, evaluate(workflow["concurrency"]["group"], newer).casefold())
                    self.assertIs(evaluate(workflow["concurrency"]["cancel-in-progress"], ctx), True)
                    seen.add(group)

    def test_pr_live_jobs_remain_skipped_even_with_permissive_inputs(self):
        for filename in PRODUCTION_GROUPS:
            workflow = read_workflow(filename)
            ctx = context(workflow["name"], "pull_request", 825)
            live_jobs = 0
            pending = dict(workflow["jobs"])
            while pending:
                progressed = False
                for job_name, job in list(pending.items()):
                    dependencies = job.get("needs", "").strip("[]").replace(" ", "").split(",")
                    dependencies = [name for name in dependencies if name]
                    if not all(name in ctx["needs"] for name in dependencies):
                        continue
                    upstream_success = all(ctx["needs"][name]["result"] == "success" for name in dependencies)
                    enabled = upstream_success and bool(evaluate(job.get("if", "true"), ctx, expression=True))
                    ctx["needs"][job_name] = {"result": "success" if enabled else "skipped"}
                    if "environment" in job:
                        live_jobs += 1
                        with self.subTest(workflow=filename, job=job_name):
                            self.assertFalse(enabled, "PR must not enter an authenticated live job")
                    del pending[job_name]
                    progressed = True
                self.assertTrue(progressed, "Unresolved job dependencies: " + filename)
            self.assertGreater(live_jobs, 0, filename)

    def test_expression_interpreter_checks_short_circuit_and_github_case_rules(self):
        ctx = context("A workflow", "PULL_REQUEST", 17)
        self.assertEqual(evaluate("${{ github.event_name == 'pull_request' && format('{0}-{1}', github.workflow, github.event.pull_request.number) || 'production' }}", ctx), "A workflow-17")
        self.assertEqual(evaluate("${{ false && format(null) || 'production' }}", ctx), "production")
        with self.assertRaises(AssertionError):
            evaluate("${{ unsupported() }}", ctx)


if __name__ == "__main__":
    unittest.main()
