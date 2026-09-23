#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${R9_PYTHON:-/opt/kalman/.venv/bin/python}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
SCHEMA="$ROOT/research/r9_news_neon_schema.sql"

if [[ "${R9_NEON_SCHEMA_APPLY:-NO}" != "YES" ]]; then
  echo "REFUSED: set R9_NEON_SCHEMA_APPLY=YES to create the research-only R9 Neon schema." >&2
  exit 20
fi

if [[ ! -f "$SCHEMA" ]]; then
  echo "ERROR: schema file not found: $SCHEMA" >&2
  exit 21
fi

sudo env   KALMAN_ENV_FILE="$ENV_FILE"   R9_NEON_SCHEMA="$SCHEMA"   "$PY" - <<'PY'
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(os.environ["KALMAN_ENV_FILE"], override=True)

database_url = os.environ.get("DATABASE_URL_WRITER", "").strip()
if not database_url:
    raise SystemExit("DATABASE_URL_WRITER is missing")

schema_path = Path(os.environ["R9_NEON_SCHEMA"])
sql = schema_path.read_text(encoding="utf-8")

statements = []
for raw in sql.split(";"):
    statement = raw.strip()
    if not statement:
        continue
    body = "\n".join(
        line for line in statement.splitlines()
        if not line.lstrip().startswith("--")
    ).strip()
    upper = body.upper()
    if not upper.startswith(("CREATE SCHEMA", "CREATE TABLE", "CREATE INDEX")):
        raise SystemExit(f"unexpected non-CREATE SQL refused: {upper[:100]}")
    if any(token in upper for token in (" DROP ", " ALTER ", " DELETE ", " UPDATE ", " INSERT ", " TRUNCATE ")):
        raise SystemExit(f"destructive/mutating SQL refused: {upper[:100]}")
    statements.append(statement)

try:
    import psycopg
except ImportError as exc:
    raise SystemExit("psycopg is missing from the Kalman venv") from exc

with psycopg.connect(database_url) as conn:
    with conn.cursor() as cur:
        cur.execute("SET LOCAL application_name = 'kalman-r9-news-schema'")
        for statement in statements:
            cur.execute(statement)

        expected = [
            'research.r9_news_alias_registry',
            'research.r9_news_mentions_daily',
            'research.r9_news_manifest',
            'research.r9_shadow_source_state',
            'research.r9_shadow_feature_snapshot',
            'research.r9_shadow_signal',
            'research.r9_shadow_trade_entry',
            'research.r9_shadow_outcome',
        ]
        cur.execute(
            "SELECT " + ", ".join(["to_regclass(%s)"] * len(expected)),
            expected,
        )
        tables = cur.fetchone()
        if not tables or any(v is None for v in tables):
            raise RuntimeError(
                f"schema verification failed: {dict(zip(expected, tables or []))!r}"
            )
    conn.commit()

print("R9_NEON_SCHEMA=PASS")
print("tables=research.r9_news_alias_registry,research.r9_news_mentions_daily,research.r9_news_manifest,research.r9_shadow_source_state,research.r9_shadow_feature_snapshot,research.r9_shadow_signal,research.r9_shadow_trade_entry,research.r9_shadow_outcome")
PY
