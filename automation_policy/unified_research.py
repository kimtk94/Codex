"""Unified IS/CKD research control plane. Only safe local stages execute.

This module deliberately does not read private data, run MR/coloc/SuSiE
without verified inputs, post to a website, or mutate external services.
"""
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .auto_input import ingest

STAGES = [
    ("source_checkout", [], "verified_git_checkout"),
    ("manifest_intake", ["source_checkout"], "manifest_gate"),
    ("batch_planning", ["manifest_intake"], "upstream_paired_batches"),
    ("pqtl_preparation", ["batch_planning"], "external_verified_executor"),
    ("mr", ["pqtl_preparation"], "external_verified_executor"),
    ("coloc_susie", ["mr"], "external_verified_executor"),
    ("kidney_annotation", ["coloc_susie"], "external_verified_executor"),
    ("koges_validation", ["kidney_annotation"], "controlled_access_required"),
    ("figure_generation", ["kidney_annotation"], "external_verified_executor"),
    ("paper_report", ["figure_generation"], "external_verified_executor"),
    ("website_update", ["paper_report"], "external_verified_executor"),
]

def run(source: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    git = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=False)
    sha = git.stdout.strip()
    if git.returncode or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("unverified_research_checkout")
    intake = ingest(source, output / "intake")
    complete = {"source_checkout"}
    if intake["input_discovered"] and intake["state"] == "COMPUTATION_COMPLETE":
        complete.update(("manifest_intake", "batch_planning"))
    states = []
    for stage, deps, executor in STAGES:
        if stage in complete:
            state = "DONE"
            reason = "verified_ci_checkout" if stage == "source_checkout" else "verified_manifest_batch_plan"
        elif any(dep not in complete for dep in deps):
            state, reason = "BLOCKED_EXTERNAL", "DEPENDENCY_NOT_VERIFIED"
        else:
            state = "BLOCKED_EXTERNAL"
            reason = "CONTROLLED_DATA_NOT_AVAILABLE" if executor == "controlled_access_required" else "EXECUTOR_NOT_CONNECTED"
        states.append({"stage": stage, "executor": executor, "state": state, "reason": reason})
    report = {
        "schema_version": 1, "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": sha, "manifest": intake, "stages": states,
        "real_analysis": {"mr": False, "coloc": False, "susie": False, "koges": False},
        "external_effects_performed": False,
        "completed_stage_count": sum(x["state"] == "DONE" for x in states),
    }
    raw = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    (output / "research-harness-status.json").write_text(raw, encoding="utf-8")
    lines = ["# Unified IS / CKD Research Harness", "",
             "Source SHA: `" + sha + "`", "",
             "This report distinguishes real manifest batch computation from unexecuted science.",
             "", "| Stage | Status | Reason |", "|---|---|---|"]
    lines += [f"| {s['stage']} | {s['state']} | {s['reason']} |" for s in states]
    lines += ["", "MR / colocalization / SuSiE / KoGES validation: **NOT RUN**", "",
              "Web publishing: **NOT CONNECTED**", "",
              "No live trading, mail, operating database or production deployment actions."]
    (output / "research-harness-status.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, default=Path("research_source"))
    p.add_argument("--out", type=Path, default=Path("artifacts/unified-research"))
    args = p.parse_args()
    report = run(args.source, args.out)
    print(json.dumps({"source_commit": report["source_commit"],
                      "completed_stage_count": report["completed_stage_count"],
                      "stage_status": {s["stage"]: s["state"] for s in report["stages"]}}, indent=2))
