"""Discover opt-in, non-sensitive IS manifest files with pinned checksums.

Only manifests with sidecar .sha256 are eligible. Never download source URLs.
"""
import hashlib
import json
from pathlib import Path
from .is_batch_executor import execute

def discover(root: Path, research_source: Path, output: Path):
    output.mkdir(parents=True,exist_ok=True)
    entries=[]
    if root.exists():
        for manifest in sorted(root.glob("*.tsv"))[:50]:
            if manifest.is_symlink() or manifest.stat().st_size > 1024*1024:
                entries.append({"name":manifest.name,"state":"BLOCKED_EXTERNAL","reason":"unsafe_manifest"})
                continue
            checksum=manifest.with_suffix(".sha256")
            if not checksum.is_file() or checksum.is_symlink():
                entries.append({"name":manifest.name,"state":"BLOCKED_EXTERNAL","reason":"missing_checksum_sidecar"})
                continue
            digest=checksum.read_text().strip()
            if len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest):
                entries.append({"name":manifest.name,"state":"BLOCKED_EXTERNAL","reason":"invalid_checksum"})
                continue
            try:
                folder=output / manifest.stem
                result=execute(research_source,manifest,digest,folder)
                entries.append({"name":manifest.name,"state":result["state"],"paired_gene_count":result["paired_gene_count"],"result":str(folder/"is-v3-batch-plan.json")})
            except (ValueError,FileNotFoundError) as exc:
                entries.append({"name":manifest.name,"state":"BLOCKED_EXTERNAL","reason":type(exc).__name__})
    report={"kind":"auto_discovery","input_source":"checked_in_sanitized_manifest_only","analysis_mr_performed":False,
            "entries":entries,"missing_inputs":not bool(entries)}
    (output/"discovery.json").write_text(json.dumps(report,indent=2)+"\n")
    return report

if __name__=="__main__":
    report=discover(Path("sanitized_inputs"),Path("research_source"),Path("artifacts/research-auto"))
    print(json.dumps(report,indent=2))
