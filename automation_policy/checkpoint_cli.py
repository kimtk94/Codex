"""Produce continuation metadata; cannot mark external work as completed."""
import json
import os
from pathlib import Path
from .checkpoint import resume,save

def main():
    spec=json.loads((Path(__file__).parent/"plan_example.json").read_text())
    prior_path=Path("previous_artifact/checkpoint.json")
    try:
        prior=json.loads(prior_path.read_text()) if prior_path.is_file() else None
    except (ValueError,OSError):
        prior=None
    report=resume(spec,prior,expected_commit=os.environ.get("GITHUB_SHA","0"*40))
    save(Path("artifacts/checkpoint.json"),report)
    print(json.dumps(report,indent=2))
if __name__=="__main__":
    main()
