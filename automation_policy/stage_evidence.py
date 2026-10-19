"""Offline research result attestation with checked local artifacts.

Results never become complete from claims alone: allowlisted stages, SHA-256
of accessible files, and a locally recorded producing git commit are required.
This does not attest scientific/statistical correctness or allow publishing.
"""
import hashlib
import json
from pathlib import Path

STAGES=("pqtl_preparation","mr","coloc_susie","kidney_annotation","koges_validation")
LIMIT=50*1024*1024
def verify(root:Path,manifest:Path):
    data=json.loads(manifest.read_text())
    if data.get("version")!=1 or not isinstance(data.get("stages"),list):
        raise ValueError("unsupported manifest")
    results={}
    for item in data["stages"]:
        stage=item.get("stage")
        if stage not in STAGES or stage in results:
            raise ValueError("unknown or repeated stage")
        paths=item.get("outputs")
        commit=item.get("source_commit","")
        if not isinstance(paths,list) or not paths or len(paths)>20 or not isinstance(commit,str) or len(commit)!=40 or any(c not in "0123456789abcdef" for c in commit):
            results[stage]="BLOCKED_UNVERIFIED"
            continue
        ok=True
        for output in paths:
            relative=output.get("path","")
            digest=output.get("sha256","")
            if not isinstance(relative,str) or not isinstance(digest,str):
                ok=False;break
            p=Path(relative)
            if p.is_absolute() or ".." in p.parts or len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest):
                ok=False;break
            f=root/p
            if not f.is_file() or f.is_symlink() or f.stat().st_size>LIMIT:
                ok=False;break
            if hashlib.sha256(f.read_bytes()).hexdigest()!=digest:
                ok=False;break
        results[stage]="ARTIFACT_INTEGRITY_VERIFIED" if ok else "BLOCKED_UNVERIFIED"
    return {"verification_scope":"local_file_integrity_only","scientific_qc_verified":False,"stage_integrity":results}
