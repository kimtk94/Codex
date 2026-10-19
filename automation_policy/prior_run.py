"""Validate the GitHub Actions artifact origin before treating it as a checkpoint hint.

Never mark previous jobs complete from downloaded checkpoint metadata.
"""
import json
import os
from pathlib import Path

def inspect(run: dict, *, repository: str, head_sha: str, ref: str, workflow_id: int) -> dict:
    permitted = (
        run.get("repository", {}).get("full_name") == repository
        and run.get("head_sha") == head_sha
        and run.get("head_branch") == ref.removeprefix("refs/heads/")
        and run.get("workflow_id") == workflow_id
        and run.get("event") in ("schedule", "workflow_dispatch")
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
    )
    return {"origin_ok": bool(permitted), "trusted_completion": False,
            "reason": "metadata_matched_but_artifact_not_attested" if permitted else "origin_rejected"}

def main():
    p = Path("previous_artifact/run.json")
    if not p.exists():
        result = {"origin_ok": False, "trusted_completion": False, "reason": "no_prior_run"}
    else:
        result = inspect(json.loads(p.read_text()),
            repository=os.environ.get("GITHUB_REPOSITORY", ""),
            head_sha=os.environ.get("GITHUB_SHA", ""),
            ref=os.environ.get("GITHUB_REF", ""),
            workflow_id=int(os.environ.get("HARNESS_WORKFLOW_ID", "389114094")))
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/previous-artifact-audit.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))
if __name__ == "__main__":
    main()
