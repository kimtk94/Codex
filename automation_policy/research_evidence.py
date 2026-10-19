"""Offline verifier for sanitized research QC evidence manifests. No raw data upload."""
import argparse
import hashlib
import json
import re
from pathlib import Path

HEX64 = re.compile(r"^[0-9a-f]{64}$")
APPROVED_KINDS = {"is_gene_qc", "ckd_stage_qc"}
REQUIRED = {"schema_version","kind","project","source_commit","input_sha256","qc_metrics","checks"}

def validate_manifest(data: dict) -> dict:
    if not isinstance(data, dict) or not REQUIRED.issubset(data):
        raise ValueError("missing_required_evidence_fields")
    if data["schema_version"] != 1 or data["kind"] not in APPROVED_KINDS:
        raise ValueError("invalid_schema_or_kind")
    if data["project"] not in ("IS", "CKD") or not HEX64.fullmatch(data["input_sha256"]):
        raise ValueError("invalid_project_or_hash")
    if not re.fullmatch(r"[0-9a-f]{40}", data["source_commit"]):
        raise ValueError("invalid_source_commit")
    checks = data["checks"]
    if not isinstance(checks, list) or not checks:
        raise ValueError("missing_checks")
    if any(not isinstance(x, dict) or not isinstance(x.get("name"), str)
           or x.get("passed") is not True for x in checks):
        raise ValueError("qc_checks_not_all_passed")
    metrics = data["qc_metrics"]
    if not isinstance(metrics, dict) or not metrics or any(
        isinstance(v, bool) or not isinstance(v, (int,float)) or v != v
        for v in metrics.values()
    ):
        raise ValueError("invalid_metrics")
    if data.get("synthetic") is not False:
        raise ValueError("nonproduction_or_unspecified_evidence")
    return {"verified_manifest": True, "kind": data["kind"], "project": data["project"],
            "check_count": len(checks), "metric_count": len(metrics),
            "claim": "manifest_schema_and_reported_checks_only",
            "not_verified": ["source_file_bytes", "scientific_validity", "data_provenance_authenticity"]}

def verify(path: Path, output: Path) -> None:
    if path.stat().st_size > 65536:
        raise ValueError("oversized_manifest")
    document = json.loads(path.read_text(encoding="utf-8"))
    report = validate_manifest(document)
    report["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", type=Path, default=Path("artifacts/research-evidence-validation.json"))
    args = parser.parse_args()
    verify(args.manifest, args.out)
