"""Read-only research repository contract audit using imported project code.

No private data, external API, or scientific result is claimed.
"""
import importlib.util
import json
import tempfile
from pathlib import Path

def check(repo_root: Path, artifacts: Path) -> dict:
    code = repo_root / "scripts" / "ukb_ppp_batch_manifest_runner_fast.py"
    readme = repo_root / "README.md"
    guide = repo_root / "docs" / "v3_migration_guide.md"
    for path in (code, readme, guide):
        if not path.is_file():
            raise FileNotFoundError(f"required research source missing: {path.name}")
    source = code.read_text(encoding="utf-8")
    for marker in ("def read_tsv(", "def paired_batches(", "--run", "--download-only", "--test-data-only"):
        if marker not in source:
            raise ValueError(f"research runner contract missing: {marker}")
    spec = importlib.util.spec_from_file_location("is_v3_manifest_runner", str(code))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as directory:
        manifest = Path(directory) / "sample.tsv"
        manifest.write_text("gene\tancestry\tsource_url\nIDO1\tEUR\tfile:///fixture-eur\nIDO1\tEAS\tfile:///fixture-eas\n")
        rows = module.read_tsv(manifest)
        batches = module.paired_batches(rows, 15)
        if len(rows) != 2 or not any("IDO1" in batch for batch in batches):
            raise ValueError("manifest pair contract failed")
    evidence = {
        "kind": "real_repository_code_contract_test",
        "repository": "kimtk94/IS_Analysis_V3",
        "checks": ["source_presence", "runner_flag_contract", "read_tsv_import", "paired_eur_eas_fixture"],
        "passed": True,
        "is_biological_qc": False,
        "has_private_research_data": False
    }
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "research-code-contract.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence

if __name__ == "__main__":
    print(json.dumps(check(Path("research_source"), Path("artifacts")), indent=2))
