"""Emit a research CI status report; never imply scientific analysis completed."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

def write_report(out: Path, *, source_sha: str, tests_passed: bool) -> dict:
    out.mkdir(parents=True,exist_ok=True)
    data = {"generated_utc":datetime.now(timezone.utc).isoformat(),
            "research_repository":"kimtk94/IS_Analysis_V3",
            "research_source_sha":source_sha,
            "checks":{"python_compile":"PASS" if tests_passed else "FAIL",
                      "repository_fixture_regression":"PASS" if tests_passed else "FAIL"},
            "scientific_analysis":{"IS":"NOT_RUN","CKD":"NOT_RUN"},
            "private_data_access":False,
            "live_changes":False}
    (out/"research-ci-status.json").write_text(json.dumps(data,indent=2)+"\n")
    md=("# Research CI status\n\n"
        f"Generated (UTC): {data['generated_utc']}\n\n"
        f"Research source: `{source_sha}`\n\n"
        f"Python compile and upstream fixture regression: **{'PASS' if tests_passed else 'FAIL'}**\n\n"
        "IS biological analysis: **NOT RUN**\n\nCKD biological analysis: **NOT RUN**\n\n"
        "No private datasets were accessed. No production actions were performed.\n")
    (out/"research-ci-status.md").write_text(md)
    return data

if __name__=="__main__":
    source=os.environ.get("RESEARCH_SHA","")
    if len(source)!=40 or any(c not in "0123456789abcdef" for c in source):
        raise SystemExit("invalid research SHA")
    print(json.dumps(write_report(Path("artifacts"),source_sha=source,tests_passed=True),indent=2))
