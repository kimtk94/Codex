"""G12 scoped *real-function handoff* test, synthetic data only.

Run by g16_private_sif_bwrap.sh inside private rootless Bubblewrap.
Extracts the actual patched Prepayment branch and real Action/Review generator
bodies. Does NOT import/execute CSS main(), the Collector, or external clients.
This is a scoped handoff test, NOT full-engine integration.
"""
from __future__ import annotations

import argparse
import ast
import tempfile
from pathlib import Path

import pandas as pd

import large_sif_workflow_regression as sif
import real_action_review_generator_regression as action

CHECKS = []
GENERIC = {"SIF 제출 요청", "SIF 수정", "프로젝트 조치", "장기 정체"}


def check(ok, label):
    if not ok:
        raise AssertionError("G12_HANDOFF_FAILED_" + label)
    CHECKS.append(label)
    print("G12_HANDOFF_PASS", label, flush=True)


def main_branch(candidate: str):
    tree = ast.parse(candidate)
    mains = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name == "main"]
    check(len(mains) == 1, "ONE_MAIN_DEFINITION")
    branches = [
        node for node in ast.walk(mains[0])
        if isinstance(node, ast.If) and isinstance(node.test, ast.BoolOp)
        and any(isinstance(t, ast.Name) and t.id == "prepayment_project_ids"
                for t in ast.walk(node.test))
        and any(isinstance(t, ast.Name) and t.id == "prepayment_mask"
                for t in ast.walk(node))
    ]
    check(len(branches) == 1, "EXACT_PREPAYMENT_BRANCH")
    return branches[0]


def action_fixture(board: pd.DataFrame):
    frame = board.copy()
    frame["institution"] = "Synthetic Institute"
    frame["customer_name"] = "SYNTHETIC PI"
    frame["service"] = "mRNA-Seq"
    frame["attention"] = "Yes"
    frame["attention_reason"] = "Synthetic SIF attention"
    frame["latest_action_required"] = "Yes"
    frame["latest_subject"] = "Synthetic notification"
    frame["latest_uid"] = "SYNTHETIC-MAIL"
    frame["planned_samples"] = 10
    frame["latest_confirmed_samples"] = 8
    frame["days_since_update"] = 10
    frame["sla_enabled"] = "Yes"
    return frame


def extract_portfolio(ns, branch, conn, board, prepay_ids):
    frame = board.copy()
    context = dict(ns)
    context.update({
        "conn": conn,
        "df_dashboard": frame,
        "df_dashboard_portfolio": frame.copy(),
        "prepayment_project_ids": prepay_ids,
        "counts": {},
        "df_overview_snoozes": pd.DataFrame(columns=["mode"]),
        "_sync_overview_snooze_actions_from_records":
            lambda *_args: (pd.DataFrame(columns=["mode"]), {}),
    })
    exec(compile(ast.Module(body=[branch], type_ignores=[]),
                 "real-main-prepayment-branch-only", "exec"), context)
    return context["df_dashboard_portfolio"], context["df_dashboard"], context["counts"]


def make_independent_inputs(p0, p1, p2):
    unanswered = pd.DataFrame([{
        "waiting_days": 5.0, "from_email": "noreply@synthetic.example.test",
        "project_ids": p0, "subject": "Synthetic inquiry", "uid": "SYN-UNANSWERED-1",
    }])
    manual = pd.DataFrame([{
        "status": "활성", "priority": "긴급", "issue_id": "SYN-MANUAL-1",
        "issue_type": "Synthetic Manual Task", "project_id": p1,
        "institution": "Synthetic Institute", "service": "mRNA-Seq",
        "reason": "Synthetic manual", "evidence": "Synthetic only",
    }])
    crm = pd.DataFrame([{
        "waiting_days": 5.0, "record_id": "SYN-CRM-1",
        "request_text": "Synthetic CRM", "customer_name": "Synthetic CRM",
        "institution": "Synthetic Institute", "customer_email": "crm@example.test",
        "mail_sent_after_enquiry": "No", "email_followup_status": "Needs response",
        "record_status": "Open",
    }])
    quote = pd.DataFrame([{
        "quotation_id": "", "invoice_number": "SYN-INV-1",
        "matched_project_id": p2, "match_type": "Ambiguous",
    }])
    return unanswered, manual, crm, quote


def test_handoff(candidate: str):
    ns_sif = sif.load_functions(candidate)
    conn, basic = sif.synthetic_db()
    try:
        prepay_ids = ns_sif["collect_active_prepayment_project_ids"](conn)
        check(len(basic) == sif.N, "SYNTHETIC_1200_RECORDS")
        check(len(prepay_ids) > 200, "PREPAYMENT_PROJECTS_PRESENT")
        branch = main_branch(candidate)
        frame = action_fixture(basic)
        portfolio, action_only, counts = extract_portfolio(
            ns_sif, branch, conn, frame, prepay_ids)
        suppressed = set(frame["project_id"]) - set(action_only["project_id"])
        check(len(suppressed) > 150, "REAL_MAIN_BRANCH_SUPPRESSES_SIF_ONLY")
        check(len(portfolio) == sif.N, "FULL_PORTFOLIO_RETAINED")
        check(counts["prepayment_project_followup_excluded"] == len(suppressed),
              "EXCLUSION_COUNT_MATCHES")
        check(set(portfolio.loc[portfolio["project_id"].isin(suppressed), "attention"])
              == {"No"}, "PREPAYMENT_ATTENTION_NO")
        check(set(portfolio.loc[portfolio["project_id"].isin(suppressed), "latest_action_required"])
              == {"No"}, "PREPAYMENT_ACTION_REQUIRED_NO")

        p0, p1, p2 = sorted(suppressed)[:3]
        independent = make_independent_inputs(p0, p1, p2)
        ns_action = action.prepare(candidate.encode("utf-8"))
        actions, reviews = action.run_case(ns_action, portfolio, *independent)
        check(not any(actions["project_id"].isin(suppressed) &
                      actions["task_type"].isin(GENERIC)),
              "GENERIC_SIF_TASKS_SUPPRESSED")
        check("미회신 고객 문의" in set(actions.loc[
              actions["project_id"] == p0, "task_type"]),
              "INDEPENDENT_UNANSWERED_IN_SAME_PROJECT")
        check("Synthetic Manual Task" in set(actions.loc[
              actions["project_id"] == p1, "task_type"]),
              "INDEPENDENT_MANUAL_IN_SAME_PROJECT")
        check(int(actions["task_type"].eq("Salesforce 문의").sum()) == 1,
              "INDEPENDENT_CRM_PRESERVED")
        check("Quotation-Invoice 모호" in set(reviews.loc[
              reviews["project_id"] == p2, "review_type"]),
              "INDEPENDENT_QUOTE_REVIEW_PRESERVED")
        check(actions["task_id"].is_unique and reviews["review_id"].is_unique,
              "ACTION_REVIEW_IDS_UNIQUE")
        check(portfolio.loc[portfolio["project_id"] == p0, "customer_name"].iat[0]
              == "SYNTHETIC PI", "PORTFOLIO_CUSTOMER_METADATA_PRESERVED")

        again, reviews_again = action.run_case(ns_action, portfolio, *independent)
        check(set(actions["task_id"]) == set(again["task_id"]) and
              set(reviews["review_id"]) == set(reviews_again["review_id"]),
              "REPEAT_HANDOFF_IDEMPOTENT")

        promoted = frame.copy()
        promoted.loc[promoted["project_id"] == p0, "current_stage"] = "Sample QC review"
        new_portfolio, new_actions_input, new_counts = extract_portfolio(
            ns_sif, branch, conn, promoted, prepay_ids)
        check(p0 in set(new_actions_input["project_id"]), "QC_REAPPEARS_ACTION_INPUT")
        check(new_portfolio.loc[new_portfolio["project_id"] == p0, "attention"].iat[0]
              == "Yes", "QC_ATTENTION_NORMAL")
        check(new_counts["prepayment_project_followup_excluded"] == len(suppressed) - 1,
              "QC_DECREASES_SUPPRESSION_BY_ONE")

        new_actions, new_review = action.run_case(ns_action, new_portfolio, *independent)
        check("미회신 고객 문의" in set(new_actions.loc[
              new_actions["project_id"] == p0, "task_type"]),
              "QC_INDEPENDENT_CUSTOMER_INQUIRY_REMAINS")
        check(new_actions["task_id"].is_unique and new_review["review_id"].is_unique,
              "QC_HANDOFF_NO_DUPLICATE_IDS")

        print("G12_REAL_FUNCTION_HANDOFF_PASS", len(CHECKS), flush=True)
        print("G12_SYNTHETIC_RECORDS", len(frame), "SUPPRESSED", len(suppressed),
              "ACTION_ROWS", len(actions), "REVIEW_ROWS", len(reviews), flush=True)
        print("G12_NO_PRODUCTION_DB_SHEETS_MAIL_CRM_WRITES", True, flush=True)
        print("G12_FULL_CSS_MAIN_NOT_EXECUTED", True, flush=True)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--patch", action="append", required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="g12-sif-handoff-") as folder:
        candidate = sif.staging(args.source, args.patch, folder)
        test_handoff(candidate)


if __name__ == "__main__":
    main()
