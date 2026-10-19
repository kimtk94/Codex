"""Fail-closed CKD Drive intake on GitHub-hosted runner.

Requires an explicitly configured least-privilege service account secret and
private file manifest. Downloads bounded selected result tables only.
"""
import hashlib
import json
import os
from pathlib import Path

ALLOWED = {
 "STAGE2B_COLOC_DEFAULT.tsv","STAGE2B_COLOC_SUMMARY.tsv",
 "STAGE2C_SUSIE_DEFAULT.tsv","STAGE2C_SUSIE_FAILURES.tsv",
 "STAGE2C_LD_QC.tsv","STAGE3A_KIDNEY_EVIDENCE.tsv",
 "STAGE3B_INTEGRATED_EVIDENCE.tsv","STAGE3B_KIDNEY_LOCALIZATION.tsv",
}
MAX_BYTES=5_000_000

def validate_manifest(spec):
    if not isinstance(spec,dict) or set(spec)!=ALLOWED: raise ValueError("exact_eight_files_required")
    ids=set()
    for name,item in spec.items():
        if not isinstance(item,dict) or set(item)!={"id","sha256"}: raise ValueError("invalid_item")
        fid,digest=item["id"],item["sha256"]
        if not isinstance(fid,str) or not fid or len(fid)>150 or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in fid): raise ValueError("invalid_file_id")
        if fid in ids: raise ValueError("duplicate_file_id")
        ids.add(fid)
        if not isinstance(digest,str) or len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest): raise ValueError("invalid_hash")
    return True

def fetch_all(spec,client,out):
    validate_manifest(spec)
    out.mkdir(parents=True,exist_ok=True)
    completed={}
    for name,item in spec.items():
        # Google authenticated session; no browser sharing links or redirects followed to third parties
        response=client.get("https://www.googleapis.com/drive/v3/files/"+item["id"],
                            params={"alt":"media"},timeout=40,allow_redirects=False)
        if response.status_code!=200: raise ValueError("drive_fetch_failed_"+name)
        blob=response.content
        if not blob or len(blob)>MAX_BYTES or hashlib.sha256(blob).hexdigest()!=item["sha256"]:
            raise ValueError("drive_integrity_failed_"+name)
        (out/name).write_bytes(blob)
        completed[name]={"sha256":item["sha256"],"bytes":len(blob)}
    return completed

def main():
    output=Path("artifacts/ckd-drive")
    output.mkdir(parents=True,exist_ok=True)
    credential=os.environ.get("CKD_DRIVE_SA_JSON","")
    manifest_path=Path(__file__).with_name("ckd_drive_files.lock.json")
    manifest=manifest_path.read_text(encoding="utf-8")
    if not credential:
        status={"status":"BLOCKED_EXTERNAL","reason":"DRIVE_READONLY_CREDENTIALS_MISSING","scientific_analysis_executed":False}
        (output/"status.json").write_text(json.dumps(status,indent=2)+"\n")
        print(json.dumps(status))
        return
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    creds=service_account.Credentials.from_service_account_info(json.loads(credential),scopes=["https://www.googleapis.com/auth/drive.readonly"])
    client=AuthorizedSession(creds)
    completed=fetch_all(json.loads(manifest),client,output/"inputs")
    from .ckd_coloc_qc import audit
    check=audit(output/"inputs/STAGE2B_COLOC_DEFAULT.tsv",output/"inputs/STAGE2B_COLOC_SUMMARY.tsv")
    result={"status":"INPUT_QC_PASS","file_count":len(completed),"input_checksums":completed,
            "coloc_qc":check,"scientific_analysis_executed":False}
    (output/"status.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"status":result["status"],"file_count":len(completed)}))
if __name__=="__main__": main()
