#!/usr/bin/env python3
"""Proposal 1 analysis helpers: All of Us CDRv9 Fitbit × Olink proteomics.

Primary use:
1) extract schema-aware nightly Fitbit phenotypes,
2) aggregate longitudinal sleep/circadian features,
3) run proteome-wide association scans,
4) prioritize significant proteins with All of Us cis-pQTL / fine-mapping summaries.

All participant-level work must remain inside the All of Us Controlled Tier workspace.
"""

from __future__ import annotations

import io
import math
import os
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import stats

from allofus_stage0 import (
    bq_table,
    find_column,
    list_tables,
    table_columns,
)


def _gcs_cat(path: str) -> bytes:
    errors = []
    for cmd in [["gcloud", "storage", "cat", path], ["gsutil", "cat", path]]:
        try:
            p = subprocess.run(cmd, check=True, capture_output=True)
            return p.stdout
        except Exception as e:
            errors.append(f"{cmd[0]}: {e}")
    raise RuntimeError("Unable to read GCS path. " + " | ".join(errors))


def read_table(path: str, nrows: Optional[int] = None) -> pd.DataFrame:
    if not path:
        raise ValueError("A resource path is required.")
    low = path.lower()
    if low.endswith(".parquet"):
        try:
            df = pd.read_parquet(path)
        except Exception:
            if not path.startswith("gs://"):
                raise
            df = pd.read_parquet(io.BytesIO(_gcs_cat(path)))
        return df.head(nrows) if nrows else df

    sep = "\t" if any(low.endswith(x) for x in [".tsv", ".txt", ".tsv.gz", ".txt.gz"]) else ","
    try:
        return pd.read_csv(path, sep=sep, nrows=nrows, low_memory=False)
    except Exception:
        if not path.startswith("gs://"):
            raise
        return pd.read_csv(io.BytesIO(_gcs_cat(path)), sep=sep, nrows=nrows, low_memory=False)


def find_col(df: pd.DataFrame, candidates: Sequence[str]) -> Optional[str]:
    lower = {str(c).strip().lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def load_proteomics_long(path: str) -> Tuple[pd.DataFrame, dict]:
    """Load CDRv9 Olink NPX into a clean long table.

    Prefer the normalized replicate-removed TSV. The official CDRv9 description
    states that this form exposes ResearchID and retains assay/QC fields.
    """
    df = read_table(path)

    id_col = find_col(df, ["ResearchID", "research_id", "person_id", "participant_id"])
    assay_col = find_col(df, ["Assay", "assay"])
    olink_col = find_col(df, ["OlinkID", "olink_id", "phenotype_id"])
    uniprot_col = find_col(df, ["UniProt", "uniprot"])
    npx_col = find_col(df, ["PCNormalizedNPX", "NPX", "npx"])
    sample_qc_col = find_col(df, ["SampleQC", "sample_qc"])
    assay_qc_col = find_col(df, ["AssayQC", "assay_qc"])
    sample_type_col = find_col(df, ["SampleType", "sample_type"])
    assay_type_col = find_col(df, ["AssayType", "assay_type"])

    required = {"ResearchID/person_id": id_col, "Assay": assay_col, "NPX": npx_col}
    missing = [k for k, v in required.items() if v is None]
    if missing:
        raise ValueError(f"Proteomics resource missing required columns: {missing}. Columns={list(df.columns)[:50]}")

    x = df.copy()

    if sample_type_col:
        mask = x[sample_type_col].astype(str).str.lower().isin(["sample", "unknown", "nan"])
        if mask.any():
            x = x[mask]
    if sample_qc_col:
        x = x[~x[sample_qc_col].astype(str).str.upper().isin(["FAIL", "FAILED"])]
    if assay_qc_col:
        x = x[~x[assay_qc_col].astype(str).str.upper().isin(["FAIL", "FAILED"])]
    if assay_type_col:
        # Exclude obvious internal controls while preserving ordinary assays.
        x = x[~x[assay_type_col].astype(str).str.lower().str.contains("control", na=False)]

    out = pd.DataFrame({
        "person_id": x[id_col].astype(str).str.strip(),
        "protein": x[assay_col].astype(str).str.strip(),
        "npx": pd.to_numeric(x[npx_col], errors="coerce"),
    })
    out["olink_id"] = x[olink_col].astype(str).str.strip() if olink_col else ""
    out["uniprot"] = x[uniprot_col].astype(str).str.strip() if uniprot_col else ""

    out = out.replace({"person_id": {"nan": np.nan, "": np.nan}})
    out = out.dropna(subset=["person_id", "protein", "npx"])
    out = (
        out.groupby(["person_id", "protein", "olink_id", "uniprot"], as_index=False, dropna=False)["npx"]
        .mean()
    )

    meta = {
        "id_column": id_col,
        "assay_column": assay_col,
        "olink_id_column": olink_col or "",
        "uniprot_column": uniprot_col or "",
        "npx_column": npx_col,
        "sample_qc_column": sample_qc_col or "",
        "assay_qc_column": assay_qc_col or "",
        "n_participants": int(out["person_id"].nunique()),
        "n_proteins": int(out["protein"].nunique()),
        "n_rows": int(len(out)),
    }
    return out, meta


def sleep_nightly_sql(client, cdr_ref: str, restrict_ids: bool = True):
    """Return schema-aware nightly sleep SQL and metadata.

    CDRv9 exposes sleep_daily_summary_ext; code falls back to sleep_daily_summary.
    Timestamp fields are SAFE_CAST to avoid source-format surprises.
    """
    existing = set(list_tables(client, cdr_ref))
    table = "sleep_daily_summary_ext" if "sleep_daily_summary_ext" in existing else "sleep_daily_summary"
    if table not in existing:
        raise RuntimeError("No Fitbit daily sleep summary table found.")

    cols = table_columns(client, cdr_ref, table)
    person = find_column(cols, ["person_id"])
    date_col = find_column(cols, ["sleep_date", "date", "date_of_sleep"])
    start_col = find_column(cols, ["start_time", "starttime"])
    end_col = find_column(cols, ["end_time", "endtime"])
    minutes_asleep = find_column(cols, ["minutes_asleep", "minutesasleep"])
    time_asleep = find_column(cols, ["time_asleep", "timeasleep"])
    duration_col = find_column(cols, ["duration", "duration_ms"])
    efficiency_col = find_column(cols, ["efficiency"])
    main_col = find_column(cols, ["is_main_sleep", "ismainsleep"])
    quality_col = find_column(cols, ["data_quality", "dataquality", "log_type", "logtype"])

    if not person:
        raise RuntimeError(f"{table} does not expose person_id.")

    if date_col:
        day_expr = f"SAFE_CAST({date_col} AS DATE)"
    elif start_col:
        day_expr = f"DATE(SAFE_CAST({start_col} AS TIMESTAMP))"
    else:
        day_expr = "CAST(NULL AS DATE)"

    sleep_min_expr = "CAST(NULL AS FLOAT64)"
    if minutes_asleep:
        sleep_min_expr = f"SAFE_CAST({minutes_asleep} AS FLOAT64)"
    elif time_asleep:
        sleep_min_expr = f"SAFE_CAST({time_asleep} AS FLOAT64)"
    elif duration_col:
        sleep_min_expr = f"SAFE_CAST({duration_col} AS FLOAT64)/60000.0"

    fields = [
        f"CAST({person} AS STRING) AS person_id",
        f"{day_expr} AS sleep_date",
        f"{sleep_min_expr} AS sleep_minutes",
        f"SAFE_CAST({efficiency_col} AS FLOAT64) AS efficiency" if efficiency_col else "CAST(NULL AS FLOAT64) AS efficiency",
        f"SAFE_CAST({start_col} AS TIMESTAMP) AS start_ts" if start_col else "CAST(NULL AS TIMESTAMP) AS start_ts",
        f"SAFE_CAST({end_col} AS TIMESTAMP) AS end_ts" if end_col else "CAST(NULL AS TIMESTAMP) AS end_ts",
        f"CAST({quality_col} AS STRING) AS data_quality" if quality_col else "CAST(NULL AS STRING) AS data_quality",
    ]

    where = [f"{person} IS NOT NULL"]
    if main_col:
        where.append(f"COALESCE(SAFE_CAST({main_col} AS BOOL), TRUE)=TRUE")
    if restrict_ids:
        where.append(f"CAST({person} AS STRING) IN UNNEST(@person_ids)")

    sql = f"""
    SELECT {', '.join(fields)}
    FROM {bq_table(cdr_ref, table)}
    WHERE {' AND '.join(where)}
    """
    meta = {
        "table": table,
        "person_id": person,
        "date": date_col or "",
        "start": start_col or "",
        "end": end_col or "",
        "minutes_asleep": minutes_asleep or time_asleep or duration_col or "",
        "efficiency": efficiency_col or "",
        "main_sleep": main_col or "",
        "quality": quality_col or "",
    }
    return sql, meta


def query_sleep_nightly(client, cdr_ref: str, person_ids: Sequence[str]) -> Tuple[pd.DataFrame, dict]:
    from google.cloud import bigquery

    ids = [str(x) for x in person_ids if str(x)]
    if not ids:
        return pd.DataFrame(), {}
    sql, meta = sleep_nightly_sql(client, cdr_ref, restrict_ids=True)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("person_ids", "STRING", ids)]
    )
    return client.query(sql, job_config=job_config).to_dataframe(), meta


def _circular_mean_minutes(values: Iterable[float]) -> float:
    x = pd.to_numeric(pd.Series(values), errors="coerce").dropna().to_numpy(dtype=float)
    if len(x) == 0:
        return np.nan
    ang = x / 1440.0 * 2.0 * np.pi
    mean_ang = math.atan2(np.mean(np.sin(ang)), np.mean(np.cos(ang)))
    if mean_ang < 0:
        mean_ang += 2.0 * np.pi
    return float(mean_ang / (2.0 * np.pi) * 1440.0)


def _circular_sd_minutes(values: Iterable[float]) -> float:
    x = pd.to_numeric(pd.Series(values), errors="coerce").dropna().to_numpy(dtype=float)
    if len(x) < 2:
        return np.nan
    ang = x / 1440.0 * 2.0 * np.pi
    r = np.hypot(np.mean(np.cos(ang)), np.mean(np.sin(ang)))
    r = float(np.clip(r, 1e-12, 1.0))
    sd_rad = math.sqrt(max(0.0, -2.0 * math.log(r)))
    return float(sd_rad / (2.0 * np.pi) * 1440.0)


def _circular_abs_diff_minutes(a: float, b: float) -> float:
    if pd.isna(a) or pd.isna(b):
        return np.nan
    d = abs(float(a) - float(b)) % 1440.0
    return float(min(d, 1440.0 - d))


def prepare_nightly_sleep(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    if x.empty:
        return x

    x["person_id"] = x["person_id"].astype(str)
    x["sleep_date"] = pd.to_datetime(x["sleep_date"], errors="coerce").dt.date
    x["start_ts"] = pd.to_datetime(x["start_ts"], errors="coerce", utc=True)
    x["end_ts"] = pd.to_datetime(x["end_ts"], errors="coerce", utc=True)
    x["sleep_minutes"] = pd.to_numeric(x["sleep_minutes"], errors="coerce")
    x["efficiency"] = pd.to_numeric(x["efficiency"], errors="coerce")

    valid_ts = x["start_ts"].notna() & x["end_ts"].notna()
    elapsed = (x.loc[valid_ts, "end_ts"] - x.loc[valid_ts, "start_ts"]).dt.total_seconds() / 60.0
    bad = (~np.isfinite(x.loc[valid_ts, "sleep_minutes"])) | (x.loc[valid_ts, "sleep_minutes"] <= 0)
    idx = x.loc[valid_ts].index[bad]
    x.loc[idx, "sleep_minutes"] = elapsed.loc[idx]

    x["sleep_hours"] = x["sleep_minutes"] / 60.0
    x["start_minute"] = (
        x["start_ts"].dt.hour * 60.0
        + x["start_ts"].dt.minute
        + x["start_ts"].dt.second / 60.0
    )

    duration_for_mid = x["sleep_minutes"].where(
        x["sleep_minutes"].between(60, 1200), np.nan
    )
    x["midpoint_minute"] = (x["start_minute"] + duration_for_mid / 2.0) % 1440.0

    # Keep physiologically plausible main-sleep records.
    x = x[
        x["sleep_hours"].between(1.0, 16.0)
        | x["sleep_hours"].isna()
    ].copy()

    if "sleep_date" in x:
        weekday = pd.to_datetime(x["sleep_date"], errors="coerce").dt.dayofweek
        x["is_weekend"] = weekday.ge(5)

    # If duplicate nightly records remain, retain the longest main sleep.
    x = x.sort_values("sleep_minutes", ascending=False).drop_duplicates(
        ["person_id", "sleep_date"], keep="first"
    )
    return x.sort_values(["person_id", "sleep_date"])


def aggregate_sleep_phenotypes(nightly: pd.DataFrame, min_days: int = 21) -> pd.DataFrame:
    x = prepare_nightly_sleep(nightly)
    if x.empty:
        return pd.DataFrame()

    rows = []
    for person_id, g in x.groupby("person_id"):
        g = g.sort_values("sleep_date")
        n = int(g["sleep_date"].nunique())
        if n < min_days:
            continue

        mid_all = _circular_mean_minutes(g["midpoint_minute"])
        onset_all = _circular_mean_minutes(g["start_minute"])

        wk = g[~g["is_weekend"]]
        we = g[g["is_weekend"]]
        wk_mid = _circular_mean_minutes(wk["midpoint_minute"])
        we_mid = _circular_mean_minutes(we["midpoint_minute"])

        rows.append({
            "person_id": str(person_id),
            "n_sleep_days": n,
            "mean_sleep_hours": g["sleep_hours"].mean(),
            "sd_sleep_hours": g["sleep_hours"].std(ddof=1),
            "cv_sleep_duration": g["sleep_hours"].std(ddof=1) / g["sleep_hours"].mean()
                if g["sleep_hours"].mean() not in [0, np.nan] else np.nan,
            "mean_sleep_efficiency": g["efficiency"].mean(),
            "mean_sleep_midpoint_min": mid_all,
            "sleep_midpoint_variability_min": _circular_sd_minutes(g["midpoint_minute"]),
            "mean_sleep_onset_min": onset_all,
            "sleep_onset_variability_min": _circular_sd_minutes(g["start_minute"]),
            "social_jetlag_min": _circular_abs_diff_minutes(wk_mid, we_mid),
            "weekend_sleep_midpoint_min": we_mid,
            "weekday_sleep_midpoint_min": wk_mid,
            "first_sleep_date": min(g["sleep_date"]),
            "last_sleep_date": max(g["sleep_date"]),
        })

    return pd.DataFrame(rows)


def person_covariate_sql(client, cdr_ref: str, restrict_ids: bool = True):
    existing = set(list_tables(client, cdr_ref))
    if "person" not in existing:
        raise RuntimeError("person table not found.")
    cols = table_columns(client, cdr_ref, "person")
    person = find_column(cols, ["person_id"])
    yob = find_column(cols, ["year_of_birth"])
    birth_dt = find_column(cols, ["birth_datetime"])
    gender = find_column(cols, ["gender_concept_id"])
    race = find_column(cols, ["race_concept_id"])
    ethnicity = find_column(cols, ["ethnicity_concept_id"])

    age_expr = "CAST(NULL AS FLOAT64)"
    if yob:
        age_expr = f"2025 - SAFE_CAST({yob} AS INT64)"
    elif birth_dt:
        age_expr = f"DATE_DIFF(DATE '2025-01-01', DATE(SAFE_CAST({birth_dt} AS TIMESTAMP)), YEAR)"

    fields = [
        f"CAST({person} AS STRING) AS person_id",
        f"{age_expr} AS age_at_cdr_cutoff",
        f"CAST({gender} AS STRING) AS gender_concept_id" if gender else "CAST(NULL AS STRING) AS gender_concept_id",
        f"CAST({race} AS STRING) AS race_concept_id" if race else "CAST(NULL AS STRING) AS race_concept_id",
        f"CAST({ethnicity} AS STRING) AS ethnicity_concept_id" if ethnicity else "CAST(NULL AS STRING) AS ethnicity_concept_id",
    ]
    where = [f"{person} IS NOT NULL"]
    if restrict_ids:
        where.append(f"CAST({person} AS STRING) IN UNNEST(@person_ids)")
    return f"SELECT {', '.join(fields)} FROM {bq_table(cdr_ref, 'person')} WHERE {' AND '.join(where)}"


def query_person_covariates(client, cdr_ref: str, person_ids: Sequence[str]) -> pd.DataFrame:
    from google.cloud import bigquery
    ids = [str(x) for x in person_ids if str(x)]
    if not ids:
        return pd.DataFrame()
    sql = person_covariate_sql(client, cdr_ref, restrict_ids=True)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("person_ids", "STRING", ids)]
    )
    return client.query(sql, job_config=job_config).to_dataframe()


def bh_fdr(pvalues: Sequence[float]) -> np.ndarray:
    p = np.asarray(pvalues, dtype=float)
    out = np.full(len(p), np.nan)
    ok = np.isfinite(p)
    if not ok.any():
        return out
    vals = p[ok]
    order = np.argsort(vals)
    ranked = vals[order]
    m = len(ranked)
    q = ranked * m / np.arange(1, m + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    q = np.clip(q, 0, 1)
    inv = np.empty(m, dtype=int)
    inv[order] = np.arange(m)
    out[np.where(ok)[0]] = q[inv]
    return out


def _encode_covariates(df: pd.DataFrame, covariates: Sequence[str]) -> pd.DataFrame:
    pieces = []
    for c in covariates:
        if c not in df.columns:
            continue
        s = df[c]
        numeric = pd.to_numeric(s, errors="coerce")
        if numeric.notna().mean() >= 0.9:
            pieces.append(pd.DataFrame({c: numeric}, index=df.index))
        else:
            d = pd.get_dummies(s.astype("string"), prefix=c, drop_first=True, dtype=float)
            pieces.append(d)
    if not pieces:
        return pd.DataFrame(index=df.index)
    return pd.concat(pieces, axis=1)


def _ols_beta(y: pd.Series, exposure: pd.Series, cov: pd.DataFrame, min_n: int = 50) -> dict:
    frame = pd.DataFrame({"y": pd.to_numeric(y, errors="coerce"), "x": pd.to_numeric(exposure, errors="coerce")})
    if cov is not None and not cov.empty:
        frame = pd.concat([frame, cov], axis=1)
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < min_n or frame["x"].std(ddof=1) == 0:
        return {"n": len(frame), "beta": np.nan, "se": np.nan, "p": np.nan}

    xz = (frame["x"] - frame["x"].mean()) / frame["x"].std(ddof=1)
    X_parts = [np.ones(len(frame)), xz.to_numpy(dtype=float)]
    if frame.shape[1] > 2:
        for c in frame.columns[2:]:
            v = frame[c].to_numpy(dtype=float)
            if np.nanstd(v) > 0:
                X_parts.append(v)
    X = np.column_stack(X_parts)
    yy = frame["y"].to_numpy(dtype=float)

    rank = np.linalg.matrix_rank(X)
    if rank < X.shape[1] or len(yy) <= X.shape[1] + 2:
        return {"n": len(frame), "beta": np.nan, "se": np.nan, "p": np.nan}

    xtx_inv = np.linalg.pinv(X.T @ X)
    coef = xtx_inv @ X.T @ yy
    resid = yy - X @ coef
    dfree = len(yy) - X.shape[1]
    sigma2 = float((resid @ resid) / dfree)
    se = float(np.sqrt(max(0.0, sigma2 * xtx_inv[1, 1])))
    beta = float(coef[1])
    t = beta / se if se > 0 else np.nan
    p = float(2 * stats.t.sf(abs(t), dfree)) if np.isfinite(t) else np.nan
    return {"n": len(frame), "beta": beta, "se": se, "p": p}


def proteome_wide_scan(
    proteomics: pd.DataFrame,
    phenotypes: pd.DataFrame,
    covariates: Optional[pd.DataFrame],
    digital_features: Sequence[str],
    covariate_columns: Sequence[str] = ("age_at_cdr_cutoff", "gender_concept_id"),
    min_n: int = 100,
) -> pd.DataFrame:
    base = phenotypes.copy()
    if covariates is not None and not covariates.empty:
        base = base.merge(covariates, on="person_id", how="left")

    rows = []
    protein_meta = (
        proteomics[["protein", "olink_id", "uniprot"]]
        .drop_duplicates("protein")
        .set_index("protein")
        .to_dict("index")
    )

    for feature in digital_features:
        if feature not in base.columns:
            continue
        for protein, pg in proteomics.groupby("protein"):
            d = pg[["person_id", "npx"]].merge(base, on="person_id", how="inner")
            cov = _encode_covariates(d, covariate_columns)
            result = _ols_beta(d["npx"], d[feature], cov, min_n=min_n)
            meta = protein_meta.get(protein, {})
            rows.append({
                "digital_feature": feature,
                "protein": protein,
                "olink_id": meta.get("olink_id", ""),
                "uniprot": meta.get("uniprot", ""),
                **result,
            })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["q"] = np.nan
    for feature, idx in out.groupby("digital_feature").groups.items():
        out.loc[idx, "q"] = bh_fdr(out.loc[idx, "p"].to_numpy())
    return out.sort_values(["digital_feature", "q", "p"], na_position="last").reset_index(drop=True)


def load_cis_pqtl(path: str) -> pd.DataFrame:
    x = read_table(path)
    needed = ["phenotype_id", "variant_id", "slope", "slope_se", "qval"]
    missing = [c for c in needed if find_col(x, [c]) is None]
    if missing:
        raise ValueError(f"cis-pQTL file missing expected columns: {missing}")
    rename = {find_col(x, [c]): c for c in needed}
    for extra in ["pval_nominal", "pval_beta", "af", "ma_count", "ma_samples", "pval_nominal_threshold"]:
        col = find_col(x, [extra])
        if col:
            rename[col] = extra
    return x.rename(columns=rename)[list(dict.fromkeys(rename.values()))]


def prioritize_with_pqtl(
    scan: pd.DataFrame,
    cis_pqtl: pd.DataFrame,
    scan_q: float = 0.05,
    pqtl_q: float = 0.05,
) -> pd.DataFrame:
    sig = scan[(scan["q"] <= scan_q) & scan["q"].notna()].copy()
    if sig.empty:
        return pd.DataFrame()

    pq = cis_pqtl.copy()
    pq["qval"] = pd.to_numeric(pq["qval"], errors="coerce")
    pq = pq[(pq["qval"] <= pqtl_q) & pq["qval"].notna()].copy()

    # phenotype_id may correspond to OlinkID or assay name depending on release file.
    left = sig.copy()
    left["pqtl_key"] = left["olink_id"].where(left["olink_id"].astype(str).str.len() > 0, left["protein"])
    pq["pqtl_key"] = pq["phenotype_id"].astype(str)

    merged = left.merge(pq, on="pqtl_key", how="left", suffixes=("", "_pqtl"))

    # Fallback for releases where phenotype_id uses assay names.
    unmatched = merged["variant_id"].isna() if "variant_id" in merged else pd.Series(True, index=merged.index)
    if unmatched.any():
        fb = left[unmatched.to_numpy()].drop(columns=["pqtl_key"]).merge(
            pq.drop(columns=["pqtl_key"]),
            left_on="protein",
            right_on="phenotype_id",
            how="left",
            suffixes=("", "_pqtl"),
        )
        merged.loc[unmatched, fb.columns] = fb.to_numpy()

    return merged.sort_values(["q", "qval"], na_position="last").reset_index(drop=True)


def candidate_table(scan: pd.DataFrame, q_threshold: float = 0.05, top_n_per_feature: int = 30) -> pd.DataFrame:
    if scan.empty:
        return scan.copy()
    x = scan[scan["p"].notna()].copy()
    x["significant"] = x["q"].le(q_threshold)
    return (
        x.sort_values(["digital_feature", "significant", "q", "p"], ascending=[True, False, True, True])
        .groupby("digital_feature", group_keys=False)
        .head(top_n_per_feature)
        .reset_index(drop=True)
    )
