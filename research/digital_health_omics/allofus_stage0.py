#!/usr/bin/env python3
"""All of Us CDRv9 Stage-0 feasibility helpers.

Designed for the All of Us Researcher Workbench 2.0 Controlled Tier.
No participant-level data are written outside the active workspace.
"""

from __future__ import annotations

import io
import os
import subprocess
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd


FITBIT_TABLES = [
    "sleep_daily_summary_ext",
    "sleep_daily_summary",
    "sleep_daily_summary_30dayavg",
    "sleep_daily_summary_counts",
    "sleep_level",
    "sleep_level_short",
    "activity_summary",
    "steps_intraday",
    "heart_rate_summary",
    "heart_rate_minute_level",
    "device",
]

EHR_TABLES = [
    "visit_occurrence",
    "condition_occurrence",
    "measurement",
    "drug_exposure",
    "procedure_occurrence",
    "observation",
]

ID_COLUMNS = [
    "person_id",
    "researchid",
    "research_id",
    "research id",
    "participant_id",
    "participantid",
    "sample_id",
    "sampleid",
]


def get_cdr_ref(explicit: Optional[str] = None) -> str:
    ref = explicit or os.getenv("WORKSPACE_CDR", "")
    if not ref:
        raise RuntimeError(
            "WORKSPACE_CDR is not set. In Workbench 2.0, first run the official "
            "'Getting Started with Verily Workbench' notebook for your workspace."
        )
    return ref.strip(chr(96))


def split_bq_ref(ref: str) -> Tuple[str, str]:
    parts = ref.split(".")
    if len(parts) >= 2:
        return parts[0], parts[1]
    raise ValueError(f"Expected project.dataset, got: {ref}")


def bq_table(cdr_ref: str, table: str) -> str:
    q = chr(96)
    return f"{q}{cdr_ref}.{table}{q}"


def get_bq_client():
    from google.cloud import bigquery
    return bigquery.Client()


def list_tables(client, cdr_ref: str) -> List[str]:
    project, dataset = split_bq_ref(cdr_ref)
    return sorted(t.table_id for t in client.list_tables(f"{project}.{dataset}"))


def available_tables(client, cdr_ref: str, candidates: Sequence[str]) -> List[str]:
    existing = set(list_tables(client, cdr_ref))
    return [x for x in candidates if x in existing]


def table_columns(client, cdr_ref: str, table: str) -> List[str]:
    tbl = client.get_table(f"{cdr_ref}.{table}")
    return [f.name for f in tbl.schema]


def find_column(columns: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    lower = {c.lower(): c for c in columns}
    for candidate in candidates:
        if candidate.lower() in lower:
            return lower[candidate.lower()]
    return None


def distinct_ids_sql(cdr_ref: str, tables: Sequence[str]) -> str:
    if not tables:
        return "SELECT CAST(NULL AS STRING) AS person_id WHERE FALSE"
    pieces = [
        f"SELECT DISTINCT CAST(person_id AS STRING) AS person_id FROM {bq_table(cdr_ref, t)} "
        "WHERE person_id IS NOT NULL"
        for t in tables
    ]
    return "\nUNION DISTINCT\n".join(pieces)


def fetch_ids(client, sql: str) -> set[str]:
    df = client.query(f"SELECT DISTINCT person_id FROM ({sql})").to_dataframe()
    return set(df["person_id"].astype(str))


def environment_resource_hints() -> pd.DataFrame:
    keys = []
    for k, v in os.environ.items():
        ku = k.upper()
        if any(token in ku for token in [
            "CDR", "WGS", "GENOM", "PROTEOM", "OLINK", "MULTIOM", "WORKSPACE_BUCKET"
        ]):
            keys.append({"env_var": k, "value": v})
    return pd.DataFrame(keys).sort_values("env_var") if keys else pd.DataFrame(columns=["env_var", "value"])


def _normalize_id_column(df: pd.DataFrame, preferred: Optional[str] = None) -> str:
    cols = list(df.columns)
    if preferred and preferred in cols:
        return preferred
    lower = {str(c).strip().lower(): c for c in cols}
    for x in ID_COLUMNS:
        if x in lower:
            return lower[x]
    raise ValueError(f"No participant ID column found. Columns: {cols[:30]}")


def _gcs_cat(path: str) -> bytes:
    errors = []
    for cmd in [["gcloud", "storage", "cat", path], ["gsutil", "cat", path]]:
        try:
            p = subprocess.run(cmd, check=True, capture_output=True)
            return p.stdout
        except Exception as e:
            errors.append(f"{cmd[0]}: {e}")
    raise RuntimeError("Unable to read GCS path. " + " | ".join(errors))


def load_participant_ids(
    path: str,
    id_column: Optional[str] = None,
    max_rows: Optional[int] = None,
) -> set[str]:
    """Load participant IDs from an accessible CSV/TSV/Parquet manifest.

    Prefer a manifest/sample-metadata resource. Do not point this Stage-0 loader
    at a huge long-form protein expression matrix if a smaller participant-level
    file is available.
    """
    if not path:
        return set()

    low = path.lower()
    if low.endswith(".parquet"):
        try:
            df = pd.read_parquet(path)
        except Exception:
            if path.startswith("gs://"):
                df = pd.read_parquet(io.BytesIO(_gcs_cat(path)))
            else:
                raise
        if max_rows:
            df = df.head(max_rows)
    else:
        sep = "\t" if any(x in low for x in [".tsv", ".txt"]) else ","
        try:
            df = pd.read_csv(path, sep=sep, nrows=max_rows, low_memory=False)
        except Exception:
            if not path.startswith("gs://"):
                raise
            df = pd.read_csv(io.BytesIO(_gcs_cat(path)), sep=sep, nrows=max_rows, low_memory=False)

    col = _normalize_id_column(df, id_column)
    ids = df[col].dropna().astype(str).str.strip()
    ids = ids[~ids.isin(["", "nan", "None", "NA"])]
    return set(ids)


def infer_wgs_manifest_path() -> Optional[str]:
    for k in ["WGS_CRAM_MANIFEST_PATH", "WGS_MANIFEST_PATH", "AOU_WGS_MANIFEST"]:
        if os.getenv(k):
            return os.getenv(k)
    for k, v in os.environ.items():
        ku, vl = k.upper(), str(v).lower()
        if "WGS" in ku and "MANIFEST" in ku and (vl.endswith(".csv") or vl.endswith(".tsv")):
            return v
    return None


def infer_proteomics_path() -> Optional[str]:
    for k in [
        "AOU_PROTEOMICS_SAMPLE_PATH",
        "AOU_PROTEOMICS_MANIFEST",
        "PROTEOMICS_MANIFEST_PATH",
        "PROTEOMICS_NPX_PATH",
        "OLINK_NPX_PATH",
    ]:
        if os.getenv(k):
            return os.getenv(k)
    for k, v in os.environ.items():
        ku, vl = k.upper(), str(v).lower()
        if any(x in ku for x in ["PROTEOM", "OLINK"]) and any(
            vl.endswith(ext) for ext in [".csv", ".tsv", ".txt", ".parquet"]
        ):
            return v
    return None


def overlap_table(
    fitbit_ids: set[str],
    ehr_ids: set[str],
    wgs_ids: set[str],
    proteomics_ids: set[str],
) -> pd.DataFrame:
    cohorts = {
        "Fitbit": fitbit_ids,
        "EHR": ehr_ids,
        "WGS": wgs_ids,
        "Proteomics": proteomics_ids,
        "Fitbit ∩ EHR": fitbit_ids & ehr_ids,
        "Fitbit ∩ WGS": fitbit_ids & wgs_ids,
        "Fitbit ∩ Proteomics": fitbit_ids & proteomics_ids,
        "Proteomics ∩ WGS": proteomics_ids & wgs_ids,
        "Fitbit ∩ Proteomics ∩ WGS": fitbit_ids & proteomics_ids & wgs_ids,
        "Fitbit ∩ Proteomics ∩ WGS ∩ EHR": fitbit_ids & proteomics_ids & wgs_ids & ehr_ids,
    }
    return pd.DataFrame([{"cohort": k, "n": len(v)} for k, v in cohorts.items()])


def proposal_decision(final_n: Optional[int]) -> Tuple[str, str]:
    if final_n is None:
        return (
            "PENDING",
            "Proteomics/WGS participant resources are not both resolved yet; add Controlled Tier resources and rerun.",
        )
    if final_n >= 1500:
        return (
            "GO_PROPOSAL_1",
            "Proceed with Fitbit × proteomics × genetics; use AoU-provided cis-pQTL/fine-mapped pQTL for causal prioritization.",
        )
    if final_n >= 500:
        return (
            "CONDITIONAL_PROPOSAL_1",
            "Proceed with reduced proteomic scope/modules and existing pQTL summaries; avoid de novo pQTL discovery.",
        )
    return (
        "PIVOT_PROPOSAL_2",
        "Make Fitbit × PRS/APOE × incident ADRD the primary thesis; keep proteomics exploratory.",
    )


def sleep_daily_aggregate_sql(client, cdr_ref: str):
    table = "sleep_daily_summary_ext"
    existing = set(list_tables(client, cdr_ref))
    if table not in existing:
        table = "sleep_daily_summary"
    if table not in existing:
        raise RuntimeError("No daily sleep summary table found.")

    cols = table_columns(client, cdr_ref, table)
    person = find_column(cols, ["person_id"])
    date_col = find_column(cols, ["sleep_date", "date", "date_of_sleep"])
    start_col = find_column(cols, ["start_time", "starttime"])
    duration_col = find_column(cols, ["duration", "duration_ms"])
    asleep_col = find_column(cols, ["minutes_asleep", "minutesasleep"])
    efficiency_col = find_column(cols, ["efficiency"])
    main_col = find_column(cols, ["is_main_sleep", "ismainsleep"])

    if not person:
        raise RuntimeError(f"{table} does not expose person_id.")

    if date_col:
        day_expr = f"DATE({date_col})"
    elif start_col:
        day_expr = f"DATE({start_col})"
    else:
        day_expr = "NULL"

    select = [
        f"CAST({person} AS STRING) AS person_id",
        f"COUNT(DISTINCT {day_expr}) AS n_sleep_days",
    ]

    if asleep_col:
        select += [
            f"AVG(SAFE_CAST({asleep_col} AS FLOAT64))/60.0 AS mean_sleep_hours",
            f"STDDEV_SAMP(SAFE_CAST({asleep_col} AS FLOAT64))/60.0 AS sd_sleep_hours",
        ]
    elif duration_col:
        select += [
            f"AVG(SAFE_CAST({duration_col} AS FLOAT64))/3600000.0 AS mean_sleep_hours",
            f"STDDEV_SAMP(SAFE_CAST({duration_col} AS FLOAT64))/3600000.0 AS sd_sleep_hours",
        ]

    if efficiency_col:
        select.append(f"AVG(SAFE_CAST({efficiency_col} AS FLOAT64)) AS mean_sleep_efficiency")

    where = [f"{person} IS NOT NULL"]
    if main_col:
        where.append(f"COALESCE(SAFE_CAST({main_col} AS BOOL), TRUE) = TRUE")

    sql = f"""
    SELECT
      {', '.join(select)}
    FROM {bq_table(cdr_ref, table)}
    WHERE {' AND '.join(where)}
    GROUP BY 1
    """
    meta = {
        "table": table,
        "date_column": date_col or "",
        "start_column": start_col or "",
        "duration_column": duration_col or "",
        "minutes_asleep_column": asleep_col or "",
        "efficiency_column": efficiency_col or "",
        "main_sleep_column": main_col or "",
    }
    return sql, meta


def activity_daily_aggregate_sql(client, cdr_ref: str):
    table = "activity_summary"
    if table not in set(list_tables(client, cdr_ref)):
        raise RuntimeError("activity_summary table not found.")
    cols = table_columns(client, cdr_ref, table)
    person = find_column(cols, ["person_id"])
    date_col = find_column(cols, ["date", "activity_date"])
    steps_col = find_column(cols, ["steps", "total_steps"])

    if not person:
        raise RuntimeError("activity_summary does not expose person_id.")

    day_expr = f"DATE({date_col})" if date_col else "NULL"
    select = [
        f"CAST({person} AS STRING) AS person_id",
        f"COUNT(DISTINCT {day_expr}) AS n_activity_days",
    ]
    if steps_col:
        select += [
            f"AVG(SAFE_CAST({steps_col} AS FLOAT64)) AS mean_steps",
            f"STDDEV_SAMP(SAFE_CAST({steps_col} AS FLOAT64)) AS sd_steps",
            f"COUNTIF(SAFE_CAST({steps_col} AS FLOAT64) >= 100) AS n_days_steps_ge_100",
        ]

    sql = f"""
    SELECT
      {', '.join(select)}
    FROM {bq_table(cdr_ref, table)}
    WHERE {person} IS NOT NULL
    GROUP BY 1
    """
    return sql, {"table": table, "date_column": date_col or "", "steps_column": steps_col or ""}


def make_qc_summary(sleep_df: pd.DataFrame, activity_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    df = sleep_df.copy()
    df["sleep_qc_21d"] = df["n_sleep_days"].fillna(0).ge(21)
    df["sleep_qc_30d"] = df["n_sleep_days"].fillna(0).ge(30)

    if activity_df is not None and not activity_df.empty:
        df = df.merge(activity_df, on="person_id", how="outer")
        if "n_activity_days" in df:
            df["activity_qc_21d"] = df["n_activity_days"].fillna(0).ge(21)
        if "n_days_steps_ge_100" in df:
            df["activity_qc_steps_21d"] = df["n_days_steps_ge_100"].fillna(0).ge(21)
    return df


def filter_qc_ids(qc_df: pd.DataFrame, min_sleep_days: int = 21) -> set[str]:
    x = qc_df[qc_df["n_sleep_days"].fillna(0).ge(min_sleep_days)]
    return set(x["person_id"].astype(str))


def stage0_summary(
    fitbit_ids: set[str],
    ehr_ids: set[str],
    wgs_ids: set[str],
    proteomics_ids: set[str],
    qc_ids: Optional[set[str]] = None,
) -> pd.DataFrame:
    rows = overlap_table(fitbit_ids, ehr_ids, wgs_ids, proteomics_ids)
    final = fitbit_ids & proteomics_ids & wgs_ids & ehr_ids
    if qc_ids is not None:
        rows = pd.concat(
            [rows, pd.DataFrame([{"cohort": "Above + wearable QC", "n": len(final & qc_ids)}])],
            ignore_index=True,
        )
    return rows
