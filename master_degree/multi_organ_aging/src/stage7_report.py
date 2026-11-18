from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result-root", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.result_root)
    summaries = {
        f"stage{i}": read_json(root / f"stage{i}" / f"STAGE{i}_SUMMARY.json")
        for i in range(5)
    }
    s0, s1, s2, s3, s4 = (
        summaries["stage0"], summaries["stage1"], summaries["stage2"],
        summaries["stage3"], summaries["stage4"]
    )

    lines = [
        "# Multi-Organ Aging Pipeline Status",
        "",
        "## Stage 0 — Feasibility audit",
        f"- Files scanned: {s0.get('n_files', 'NA')}",
        f"- Candidate variable matches: {s0.get('n_candidate_matches', 'NA')}",
        f"- Organ domains detected: {', '.join(s0.get('organs', [])) or 'NA'}",
        "",
        "## Stage 1 — Longitudinal panel",
        f"- Subjects: {s1.get('n_subjects', 'NA')}",
        f"- Person-wave rows: {s1.get('n_rows', 'NA')}",
        f"- Median waves: {s1.get('median_waves', 'NA')}",
        f"- Maximum waves: {s1.get('max_waves', 'NA')}",
        "",
        "## Stage 2 — Organ-age models",
        f"- Successful organ models: {', '.join(s2.get('organs_ok', [])) or 'NA'}",
        "",
        "## Stage 3 — Longitudinal trajectories",
        f"- Subjects: {s3.get('n_subjects', 'NA')}",
        f"- Organs: {', '.join(s3.get('organs', [])) or 'NA'}",
        f"- Non-missing velocities: {s3.get('velocity_nonmissing', {})}",
        "",
        "## Stage 4 — Cross-organ discordance",
        f"- Subjects with >=2 organ velocities: {s4.get('n_with_2plus_organs', 'NA')}",
        "",
        "## Interpretation guardrails",
        "- Organ age is a model-derived relative phenotype, not literal tissue age.",
        "- The primary target is longitudinal organ-aging velocity and cross-organ discordance.",
        "- Phenotype definitions should be frozen before prospective outcome or genetic testing.",
        "- Stage 5 and Stage 6 require separately validated outcome/PRS inputs.",
        "",
    ]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
