"""Create a minimal, non-sensitive gate gap report from manifest and signed records."""
import json
from pathlib import Path
from gate_evaluator import evaluate

def gap_rows(manifest, signed=None):
    verdicts=evaluate(manifest,signed or {})
    out=[]
    for item in verdicts:
        out.append({"gate_id":item["gate_id"],"state":item["state"],
            "missing_task_count":len(item["missing"]),
            "missing_task_ids":[x["task_id"] for x in item["missing"]],
            "missing_reasons":sorted(set(x["reason"] for x in item["missing"]))})
    return out

def main():
    manifest=json.loads(Path("automation/progress/acceptance_manifest.json").read_text())
    from acceptance_registry import REGISTRY, verify
    from tracker import tasks, MASTER
    registry=json.loads(REGISTRY.read_text(encoding="utf-8"))
    task_ids={t["id"] for t in tasks(Path(MASTER).read_text(encoding="utf-8"))}
    verify(registry,manifest,task_ids)
    report=gap_rows(manifest,registry["records"])
    folder=Path("progress-audit")
    folder.mkdir(exist_ok=True)
    (folder/"gate-gaps.json").write_text(json.dumps(report,indent=2))
    lines=["# Acceptance evidence gaps","","Gate states reflect the validated explicit-review registry; PR and CI links alone are not approvals.","",
    "| Gate | State | Missing tasks | Reason |","|---|---|---|---|"]
    for x in report:
        lines.append("| "+x["gate_id"]+" | "+x["state"]+" | "+", ".join(x["missing_task_ids"])+" | "+", ".join(x["missing_reasons"])+" |")
    (folder/"gate-gaps.md").write_text("\n".join(lines)+"\n")
    print("GATE_GAP_REPORT_OK",len(report),"gates")

if __name__=="__main__":
    main()
