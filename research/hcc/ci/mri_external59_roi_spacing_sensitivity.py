#!/usr/bin/env python3
"""Exploratory source-locked ROI and voxel-spacing sensitivity, HCC MRI n=59.

Uses only the immutable original OpenSwissHCC v2 59-patient CSV from
GitHub Actions #41221356861. Never fetches NIfTI, refits MRI features,
changes index lesions, or tests biological outcomes.
"""
import argparse
import csv
import json
import math
import os
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "HCC_EXTERNAL_OPENSWISSHCC_V2_59_INDEX_PATIENT_GLCM_NATIVE3MM_FROZEN_20261101.csv"
N = 59
ITERATIONS = 4000
SEED = 20261101
FIELDS = ("source_mask_voxels", "source_voxel_spacing_xyz_mm",
          "original_native25_GLCM_Contrast", "resampled_3mm25_GLCM_Contrast",
          "signed_change_pct", "subject", "selected_HCC_lesion",
          "original_source_run", "claim_ceiling")


def require(ok, label):
    if not ok:
        raise ValueError(label)


def percentile(values, q):
    s = sorted(v for v in values if math.isfinite(v))
    require(bool(s), "NO_FINITE_BOOTSTRAP_VALUES")
    at = (len(s) - 1) * q
    low = int(at)
    high = min(low + 1, len(s) - 1)
    return s[low] * (high - at) + s[high] * (at - low)


def rank(values):
    order = sorted(range(len(values)), key=lambda i: (values[i], i))
    result = [0.0] * len(values)
    j = 0
    while j < len(values):
        k = j + 1
        while k < len(values) and values[order[j]] == values[order[k]]:
            k += 1
        avg = (j + 1 + k) / 2.0
        for m in range(j, k):
            result[order[m]] = avg
        j = k
    return result


def spearman(x, y):
    require(len(x) == len(y) and len(x) > 2, "BAD_CORRELATION_LENGTH")
    a, b = rank(x), rank(y)
    ma, mb = statistics.mean(a), statistics.mean(b)
    da = [v - ma for v in a]
    db = [v - mb for v in b]
    sx = sum(v * v for v in da)
    sy = sum(v * v for v in db)
    if sx == 0 or sy == 0:
        return float("nan")
    return sum(u * v for u, v in zip(da, db)) / math.sqrt(sx * sy)


def load():
    with SOURCE.open(newline="", encoding="utf-8") as f:
        dr = csv.DictReader(f)
        require(set(FIELDS).issubset(set(dr.fieldnames or ())), "FROZEN_SOURCE_SCHEMA_DRIFT")
        original = list(dr)
    require(len(original) == N, "FROZEN_SOURCE_59_ROWS_REQUIRED")
    require(len({r["subject"] for r in original}) == N, "DUPLICATED_PATIENT")
    result = []
    for r in original:
        require(r["original_source_run"] == "41221356861" and
                r["claim_ceiling"] == "S0", "SOURCE_OR_CLAIM_DRIFT")
        spacing = [float(x) for x in r["source_voxel_spacing_xyz_mm"].split("|")]
        require(len(spacing) == 3 and all(math.isfinite(x) and x > 0 for x in spacing),
                "INVALID_SOURCE_VOXEL_SPACING")
        voxels = int(r["source_mask_voxels"])
        require(voxels >= 50, "INVALID_ORIGINAL_SOURCE_MASK_COUNT")
        native = float(r["original_native25_GLCM_Contrast"])
        resampled = float(r["resampled_3mm25_GLCM_Contrast"])
        change = float(r["signed_change_pct"])
        require(all(math.isfinite(x) for x in (native, resampled, change))
                and native > 0, "NONFINITE_SOURCE_FEATURE")
        recomputed = (resampled - native) / abs(native) * 100
        require(abs(recomputed - change) < 0.002, "FROZEN_SOURCE_CHANGE_VALUE_DRIFT")
        x, y, z = spacing
        result.append({
            "subject": r["subject"],
            "index_lesion": r["selected_HCC_lesion"],
            "source_mask_voxels": voxels,
            "source_spacing_x_mm": x,
            "source_spacing_y_mm": y,
            "source_spacing_z_mm": z,
            "source_voxel_volume_mm3": x * y * z,
            "source_roi_volume_ml": voxels * x * y * z / 1000,
            "source_inplane_pixel_area_mm2": x * y,
            "source_anisotropy_z_over_inplane": z / math.sqrt(x * y),
            "native25_glcm_contrast": native,
            "resampled3mm25_glcm_contrast": resampled,
            "signed_change_pct": change,
            "absolute_change_pct": abs(change),
        })
    return sorted(result, key=lambda r: r["subject"])


VARIABLES = {
    "roi_physical_volume_ml": lambda r: math.log10(r["source_roi_volume_ml"]),
    "roi_source_voxel_count": lambda r: r["source_mask_voxels"],
    "source_inplane_pixel_area_mm2": lambda r: r["source_inplane_pixel_area_mm2"],
    "source_anisotropy_z_over_inplane": lambda r: r["source_anisotropy_z_over_inplane"],
}


def analyze(rows):
    y = [r["absolute_change_pct"] for r in rows]
    analysis = {}
    for name, func in VARIABLES.items():
        x = [func(r) for r in rows]
        point = spearman(x, y)
        loorho = [spearman(x[:i] + x[i+1:], y[:i] + y[i+1:])
                  for i in range(len(rows))]
        require(all(math.isfinite(t) for t in loorho), "INVALID_LOO_RHO")
        rng = random.Random(SEED + list(VARIABLES).index(name))
        vals = []
        for _ in range(ITERATIONS):
            indices = [rng.randrange(N) for _ in range(N)]
            value = spearman([x[i] for i in indices], [y[i] for i in indices])
            if math.isfinite(value):
                vals.append(value)
        require(len(vals) >= 3900, "TOO_MANY_DEGENERATE_BOOTSTRAP_REPLICATES")
        analysis[name] = {
            "spearman_rho": round(point, 6),
            "patient_bootstrap95_low": round(percentile(vals, 0.025), 6),
            "patient_bootstrap95_high": round(percentile(vals, 0.975), 6),
            "loo_rho_min": round(min(loorho), 6),
            "loo_rho_max": round(max(loorho), 6),
            "valid_bootstrap_replicates": len(vals),
        }
    ordered = sorted(rows, key=lambda r: (r["source_roi_volume_ml"], r["subject"]))
    quartiles = []
    for i in range(4):
        group = ordered[i*N//4:(i+1)*N//4]
        quartiles.append({
            "source_volume_rank_quartile": i + 1,
            "independent_n": len(group),
            "source_roi_min_ml": round(group[0]["source_roi_volume_ml"], 6),
            "source_roi_max_ml": round(group[-1]["source_roi_volume_ml"], 6),
            "absolute_change_median_pct": round(
                statistics.median(r["absolute_change_pct"] for r in group), 6),
        })
    return {
        "stage": "HCC_STAGE32_ROI_SPACING_EXPLORATORY",
        "source_action": 41221356861,
        "source_patients": N,
        "source_image_mask_rows_used": N,
        "original_6_condition_rows_not_independent": 354,
        "source": SOURCE.name,
        "comparison": "native_venous_bw25_vs_3mm_isotropic_bw25",
        "endpoint": "within_patient_absolute_percent_change_GLCM_Contrast",
        "statistics": "descriptive_spearman_percentile_patient_bootstrap_and_leave_one_out",
        "analysis_declaration": "POST_HOC_EXPLORATORY_AFTER_PRIMARY_59_COHORT_RESULTS",
        "bootstrap_draws": ITERATIONS,
        "bootstrap_seed": SEED,
        "associations": analysis,
        "roi_physical_volume_quartiles": quartiles,
        "technical_source_geometry_hold": 0,
        "MRI_RNA_tests": 0,
        "clinical_utility": "NOT_ESTABLISHED",
        "mask_independent_reader_qualification": "NOT_ASSESSED",
        "claim_ceiling": "S0",
    }


def format_report(j):
    lines = [
        "# HCC Stage 32: external n=59 ROI size and native acquisition-spacing sensitivity",
        "",
        "Source: original 59 independent venous MRI and HCC expert source masks, GitHub Actions #41221356861.",
        "The extracted frozen patient data are reused; no source imaging or radiomics is rerun.",
        "**Post-hoc exploratory descriptive analysis, not a prespecified hypothesis test.**",
        "Each patient contributes exactly one native→3mm / binWidth 25 change; no 354-row pseudoreplication.",
        "",
        "## Associations with absolute GLCM Contrast change (%)",
        "",
        "| Original-source covariate | Spearman rho | Patient bootstrap 95% interval | Leave-one-out rho range |",
        "|---|---:|---:|---:|",
    ]
    for name, s in j["associations"].items():
        lines.append("| " + name + " | " +
                     f'{s["spearman_rho"]:.3f} | [{s["patient_bootstrap95_low"]:.3f}, {s["patient_bootstrap95_high"]:.3f}]' +
                     f' | [{s["loo_rho_min"]:.3f}, {s["loo_rho_max"]:.3f}] |')
    lines += ["", "## Source-physical ROI volume quartiles", "",
              "| Ordered volume group | n | Range, mL | Median absolute change (%) |",
              "|---|---:|---:|---:|"]
    for r in j["roi_physical_volume_quartiles"]:
        lines.append(f'| Q{r["source_volume_rank_quartile"]} | {r["independent_n"]} | ' +
                     f'{r["source_roi_min_ml"]:.3f}–{r["source_roi_max_ml"]:.3f} | ' +
                     f'{r["absolute_change_median_pct"]:.2f} |')
    lines += [
        "", "## Interpretation and non-negotiable limitations", "",
        "- Physical ROI volume = original manual mask voxel count × original voxel spacing x/y/z / 1000 mL.",
        "- Voxel count alone is NOT physical tumor size; post-resampling voxel count is never substituted.",
        "- Anisotropy z/sqrt(x*y) and in-plane area are correlated acquisition surrogates, not causal predictors.",
        "- Interpolation and intensity discretization interact; this observational study cannot isolate effects.",
        "- Bootstrap resamples patients, not conditions or feature rows. Intervals are descriptive, not proof of significance.",
        "- Original Swiss source vs TCGA/LiverHccSeg acquisition and registration differences remain unmatched.",
        "- Expert independent review and pretreatment patient-matched MRI/RNA remain HOLD; biology 0/12, S0.",
        "",
    ]
    return "\n".join(lines)


def self_test():
    require(rank([2, 2, 5]) == [1.5, 1.5, 3.0], "BAD_MIDRANKS")
    require(abs(spearman([1, 2, 3], [3, 2, 1]) + 1) < 1e-10, "BAD_SPEARMAN")
    require(abs(percentile([0, 10], .25) - 2.5) < 1e-10, "BAD_PERCENTILE")
    require(math.isnan(spearman([1, 1, 1], [1, 2, 3])), "BAD_CONSTANT_GUARD")
    print("HCC_STAGE32_OFFLINE_CONTRACT_PASS")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--out-dir", type=Path)
    args = ap.parse_args()
    self_test()
    if args.self_test:
        return
    require(args.out_dir is not None, "OUTPUT_DIRECTORY_REQUIRED")
    rows = load()
    summary = analyze(rows)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with (args.out_dir / "roi_spacing_59_patient_observations.csv").open("w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (args.out_dir / "roi_spacing_59_associations.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    report = format_report(summary)
    (args.out_dir / "roi_spacing_59_exploratory_report.md").write_text(report, encoding="utf8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf8") as f:
            f.write(report)
    print("HCC_STAGE32_59_PATIENT_SOURCE_ROI_SPACING_PASS " +
          json.dumps(summary["associations"], sort_keys=True))


if __name__ == "__main__":
    main()
