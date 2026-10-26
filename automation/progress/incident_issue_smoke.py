"""Controlled GitHub issue creation/readback/close smoke test; never opens production incidents."""
import json
import os
from incident_watch import get_json
def main():
    token=os.environ["GITHUB_TOKEN"]
    run=os.environ["GITHUB_RUN_ID"]
    title="[Automation OPS TEST] Workflow issue path "+run
    body="Automated E2E smoke test. Not a production failure. This issue will be closed by the same workflow."
    issue=get_json("issues",token,"POST",{"title":title,"body":body})
    number=issue["number"]
    print("ISSUE_CREATED",number)
    try:
        saved=get_json("issues/"+str(number),token)
        if saved.get("title")!=title or saved.get("state")!="open":
            raise RuntimeError("Issue readback failed")
        print("ISSUE_READBACK_VERIFIED",number)
    finally:
        closed=get_json("issues/"+str(number),token,"PATCH",{"state":"closed","state_reason":"completed"})
        if closed.get("state")!="closed":
            raise RuntimeError("Issue closure not verified")
        print("ISSUE_CLOSED_VERIFIED",number)
if __name__=="__main__":
    main()
