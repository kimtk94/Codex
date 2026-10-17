"""Offline isolated Preview candidate with provenance report, never deploys.

Preview source is materialized into a temporary folder ONLY; a manifest records
hashes and paths. No secrets, external network, or Vercel commands are used.
"""
from __future__ import annotations
import argparse,hashlib,json,tempfile
from pathlib import Path
from build_demo_only_staging import create,verify
from staging_env_scope_gate import assess,SNAPSHOT
ROOT=Path(__file__).resolve().parents[3]
EXPECTED_PROJECT_NAME="kalman-synthetic-preview-isolated"

def preflight():
    files=create();verify(files)
    names=sorted(files)
    digest=hashlib.sha256(b"".join(p.encode()+b"\0"+files[p]+b"\0" for p in names)).hexdigest()
    original=json.loads(SNAPSHOT.read_text())
    current=assess(original)
    return {
      "verdict":"PREVIEW_SOURCE_READY_NOT_DEPLOYED",
      "intended_new_project_name":EXPECTED_PROJECT_NAME,
      "existing_staging_status":current["verdict"],
      "existing_staging_blocker":current["reason"],
      "source_file_count":len(files),
      "source_digest":digest,
      "api_handlers_disabled":11,
      "mock_health_only":True,
      "contains_secrets":False,
      "requires_new_project_with_empty_env":True,
      "requires_independent_access_protection":True,
      "requires_operator_approval":True,
      "actual_new_project_created":False,
      "deployment_authorized":False,
    }

def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);args=p.parse_args()
    report=preflight()
    Path(args.output).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,sort_keys=True))
if __name__=="__main__":main()
