from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv


DEFAULT_DIR = Path("/opt/kalman/state/r9_news_ngram")
CONFIRM_VALUE = "CONFIRM_R9_NEWS_NEON_STORE"
SOURCE = "GDELT_BIGQUERY_WEB_1GRAMS_2GRAMS"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Validate and mirror R9 historical news artifacts into the research-only Neon store"
    )
    p.add_argument("--registry", default=str(DEFAULT_DIR / "alias_registry.csv"))
    p.add_argument("--mentions-csv", default="")
    p.add_argument("--manifest", default="")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def normalize_registry(df: pd.DataFrame) -> pd.DataFrame:
    required = {
        "symbol",
        "company_name",
        "alias",
        "alias_lower",
        "ngram_order",
        "status",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"registry missing columns: {missing}")

    x = df[list(required)].copy()
    x["symbol"] = x["symbol"].astype(str).str.strip().str.upper()
    x["company_name"] = x["company_name"].astype(str).str.strip()
    x["alias"] = x["alias"].astype(str).str.strip()
    x["alias_lower"] = x["alias_lower"].astype(str).str.strip().str.lower()
    x["ngram_order"] = pd.to_numeric(x["ngram_order"], errors="raise").astype(int)
    x["status"] = x["status"].astype(str).str.strip().str.upper()

    if len(x) != 93:
        raise ValueError(f"expected frozen 93-symbol registry, got {len(x)}")
    if x["symbol"].duplicated().any():
        raise ValueError("registry contains duplicate symbols")
    if not x["ngram_order"].isin([1, 2]).all():
        raise ValueError("registry contains non-1/2-gram aliases")
    if not x["status"].eq("SUPPORTED").all():
        bad = x.loc[~x["status"].eq("SUPPORTED"), "symbol"].tolist()
        raise ValueError(f"registry contains unsupported aliases: {bad}")
    if (x["alias"] == "").any() or (x["company_name"] == "").any():
        raise ValueError("registry contains empty company/alias values")

    x = x.sort_values("symbol").reset_index(drop=True)
    return x


def normalize_mentions(df: pd.DataFrame, symbols: set[str]) -> pd.DataFrame:
    required = {"symbol", "day_utc", "mention_count"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"mentions missing columns: {missing}")

    x = df[list(required)].copy()
    x["symbol"] = x["symbol"].astype(str).str.strip().str.upper()
    unknown = sorted(set(x["symbol"]) - symbols)
    if unknown:
        raise ValueError(f"mentions contain symbols outside frozen registry: {unknown[:10]}")

    raw_day = x["day_utc"].astype(str).str.replace(r"\.0$", "", regex=True)
    x["day_utc"] = pd.to_datetime(raw_day, format="%Y%m%d", errors="raise").dt.date

    counts = pd.to_numeric(x["mention_count"], errors="raise")
    if counts.isna().any() or (counts < 0).any():
        raise ValueError("mention_count must be finite and nonnegative")
    if ((counts % 1) != 0).any():
        raise ValueError("mention_count must be integer-valued")
    x["mention_count"] = counts.astype("int64")

    if x.duplicated(["symbol", "day_utc"]).any():
        raise ValueError("duplicate symbol/day_utc rows")
    return x.sort_values(["day_utc", "symbol"]).reset_index(drop=True)


def load_manifest(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest must be a JSON object")
    if payload.get("research_only") is not True:
        raise ValueError("manifest.research_only must be true")
    if payload.get("production_changed") is not False:
        raise ValueError("manifest.production_changed must be false")
    return payload


def load_inputs(
    registry_path: Path,
    mentions_path: Path | None,
    manifest_path: Path | None,
) -> tuple[pd.DataFrame, pd.DataFrame | None, dict[str, Any] | None]:
    registry = normalize_registry(pd.read_csv(registry_path))
    symbols = set(registry["symbol"])

    mentions = None
    if mentions_path is not None:
        mentions = normalize_mentions(pd.read_csv(mentions_path), symbols)

    manifest = load_manifest(manifest_path)
    return registry, mentions, manifest


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def write_store(
    database_url: str,
    registry: pd.DataFrame,
    mentions: pd.DataFrame | None,
    manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is missing from the Kalman environment") from exc

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL application_name = 'kalman-r9-news-research'")

            cur.execute(
                "SELECT to_regclass('research.r9_news_alias_registry'), "
                "to_regclass('research.r9_news_mentions_daily'), "
                "to_regclass('research.r9_news_manifest')"
            )
            tables = cur.fetchone()
            if not tables or any(v is None for v in tables):
                raise RuntimeError(
                    "R9 Neon schema is missing; apply research/r9_news_neon_schema.sql first"
                )

            registry_rows = [
                (
                    r.symbol,
                    r.company_name,
                    r.alias,
                    r.alias_lower,
                    int(r.ngram_order),
                    r.status,
                )
                for r in registry.itertuples(index=False)
            ]
            cur.executemany(
                """INSERT INTO research.r9_news_alias_registry (
                       symbol, company_name, alias, alias_lower, ngram_order, status
                   ) VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (symbol) DO UPDATE SET
                       company_name=EXCLUDED.company_name,
                       alias=EXCLUDED.alias,
                       alias_lower=EXCLUDED.alias_lower,
                       ngram_order=EXCLUDED.ngram_order,
                       status=EXCLUDED.status,
                       updated_at=now()""",
                registry_rows,
            )

            mention_rows = 0
            if mentions is not None:
                rows = [
                    (r.symbol, r.day_utc, int(r.mention_count), SOURCE)
                    for r in mentions.itertuples(index=False)
                ]
                cur.executemany(
                    """INSERT INTO research.r9_news_mentions_daily (
                           symbol, day_utc, mention_count, source
                       ) VALUES (%s,%s,%s,%s)
                       ON CONFLICT (symbol, day_utc) DO UPDATE SET
                           mention_count=EXCLUDED.mention_count,
                           source=EXCLUDED.source,
                           loaded_at=now()""",
                    rows,
                )
                mention_rows = len(rows)

            if manifest is not None:
                stored = dict(manifest)
                stored["storage"] = "NEON_RESEARCH"
                stored["source"] = SOURCE
                cur.execute(
                    """INSERT INTO research.r9_news_manifest (
                           manifest_key, payload
                       ) VALUES ('current', %s::jsonb)
                       ON CONFLICT (manifest_key) DO UPDATE SET
                           payload=EXCLUDED.payload,
                           updated_at=now()""",
                    (_json(stored),),
                )

            cur.execute(
                "SELECT count(*) FROM research.r9_news_alias_registry "
                "WHERE status='SUPPORTED'"
            )
            supported = int(cur.fetchone()[0])
            if supported != 93:
                raise RuntimeError(
                    f"post-write registry invariant failed: supported={supported}, expected=93"
                )

        conn.commit()

    return {
        "status": "MIRRORED",
        "research_only": True,
        "production_changed": False,
        "source": SOURCE,
        "registry_rows": len(registry),
        "mention_rows_written": mention_rows,
        "manifest_written": manifest is not None,
    }


def main() -> int:
    args = parse_args()

    registry_path = Path(args.registry).expanduser()
    mentions_path = Path(args.mentions_csv).expanduser() if args.mentions_csv else None
    manifest_path = Path(args.manifest).expanduser() if args.manifest else None

    registry, mentions, manifest = load_inputs(
        registry_path,
        mentions_path,
        manifest_path,
    )

    plan = {
        "status": "VALIDATED",
        "research_only": True,
        "production_changed": False,
        "source": SOURCE,
        "registry_rows": len(registry),
        "supported_aliases": int(registry["status"].eq("SUPPORTED").sum()),
        "mention_rows": 0 if mentions is None else len(mentions),
        "manifest_present": manifest is not None,
    }

    if args.dry_run:
        plan["status"] = "DRY_RUN"
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    load_dotenv(
        os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"),
        override=True,
    )

    enabled = os.environ.get("KALMAN_R9_NEWS_NEON_ENABLED", "false").lower() == "true"
    if not enabled:
        raise RuntimeError("KALMAN_R9_NEWS_NEON_ENABLED must be true")

    if os.environ.get("KALMAN_R9_NEWS_NEON_CONFIRM", "") != CONFIRM_VALUE:
        raise RuntimeError(
            "KALMAN_R9_NEWS_NEON_CONFIRM must equal " + CONFIRM_VALUE
        )

    database_url = os.environ.get("DATABASE_URL_WRITER", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL_WRITER is missing")

    result = write_store(database_url, registry, mentions, manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
