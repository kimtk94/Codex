from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


FEATURE_VERSION = "macro-event-feature-v1"
FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
UTC = timezone.utc
NY = ZoneInfo("America/New_York")


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_env() -> None:
    env_file = os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env")
    load_dotenv(env_file, override=True)


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def decay_weight(age_hours: float, half_life_hours: float) -> float:
    if half_life_hours <= 0:
        raise ValueError("half_life_hours must be positive")
    if age_hours < 0:
        return 0.0
    return math.exp(-math.log(2.0) * age_hours / half_life_hours)


def normalized_surprise(
    indicator_key: str,
    actual: float | None,
    consensus: float | None,
    normalization: dict[str, Any],
) -> float | None:
    if actual is None or consensus is None:
        return None
    spec = normalization.get(indicator_key)
    if not spec:
        return None
    scale = float(spec.get("scale", 0.0))
    if scale <= 0:
        return None
    policy_sign = float(spec.get("policy_sign", 1.0))
    score = policy_sign * (float(actual) - float(consensus)) / scale
    clipped = max(-5.0, min(5.0, score))
    return round(clipped, 12)


def stable_observation_id(row: dict[str, Any]) -> str:
    material = "|".join(
        str(row.get(k) or "")
        for k in (
            "indicator_key",
            "event_name",
            "release_at",
            "available_at",
            "source",
            "source_item_id",
        )
    )
    return "macro-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:28]


@dataclass(frozen=True)
class Dgs2Observation:
    date: datetime
    value_pct: float


def parse_fred_observations(payload: dict[str, Any]) -> list[Dgs2Observation]:
    out: list[Dgs2Observation] = []
    for row in payload.get("observations") or []:
        value = str(row.get("value") or "").strip()
        date_text = str(row.get("date") or "").strip()
        if not date_text or value in {"", "."}:
            continue
        try:
            date = datetime.fromisoformat(date_text).replace(tzinfo=UTC)
            out.append(Dgs2Observation(date=date, value_pct=float(value)))
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda x: x.date)
    return out


def fetch_dgs2(config: dict[str, Any], as_of: datetime) -> tuple[list[Dgs2Observation], str | None]:
    fred = config.get("fred") or {}
    if not fred.get("enabled", True):
        return [], "DISABLED"
    api_key = (os.environ.get("FRED_API_KEY") or os.environ.get("FRED_KEY") or "").strip()
    if not api_key:
        return [], "FRED_API_KEY_MISSING"
    days = int(fred.get("observation_days", 14))
    start = (as_of - timedelta(days=days)).date().isoformat()
    params = {
        "series_id": str(fred.get("series_id", "DGS2")),
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
        "sort_order": "asc",
    }
    try:
        with httpx.Client(timeout=float(fred.get("timeout_seconds", 20))) as client:
            response = client.get(FRED_OBSERVATIONS_URL, params=params)
            response.raise_for_status()
            return parse_fred_observations(response.json()), None
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"


def dgs2_latest_change(observations: list[Dgs2Observation]) -> dict[str, Any]:
    if not observations:
        return {
            "latest_date": None,
            "latest_pct": None,
            "previous_date": None,
            "previous_pct": None,
            "change_bps_1d": None,
        }
    latest = observations[-1]
    previous = observations[-2] if len(observations) >= 2 else None
    return {
        "latest_date": latest.date.date().isoformat(),
        "latest_pct": latest.value_pct,
        "previous_date": previous.date.date().isoformat() if previous else None,
        "previous_pct": previous.value_pct if previous else None,
        "change_bps_1d": (
            (latest.value_pct - previous.value_pct) * 100.0 if previous else None
        ),
    }


def dgs2_event_reaction(
    observations: list[Dgs2Observation],
    event_at: datetime | None,
) -> dict[str, Any]:
    if not observations or event_at is None:
        return {
            "event_date_et": None,
            "event_day_pct": None,
            "prior_day_pct": None,
            "reaction_bps": None,
        }
    event_date = event_at.astimezone(NY).date()
    by_date = {o.date.date(): o for o in observations}
    event_obs = by_date.get(event_date)
    if event_obs is None:
        return {
            "event_date_et": event_date.isoformat(),
            "event_day_pct": None,
            "prior_day_pct": None,
            "reaction_bps": None,
        }
    prior = [o for o in observations if o.date.date() < event_date]
    prior_obs = prior[-1] if prior else None
    return {
        "event_date_et": event_date.isoformat(),
        "event_day_pct": event_obs.value_pct,
        "prior_day_pct": prior_obs.value_pct if prior_obs else None,
        "reaction_bps": (
            (event_obs.value_pct - prior_obs.value_pct) * 100.0 if prior_obs else None
        ),
    }


def _age_hours(as_of: datetime, available_at: datetime) -> float:
    return max(0.0, (as_of - available_at).total_seconds() / 3600.0)


def _count_within(rows: list[dict[str, Any]], as_of: datetime, hours: float) -> int:
    return sum(
        1
        for row in rows
        if (dt := parse_dt(row.get("available_at"))) is not None
        and 0.0 <= _age_hours(as_of, dt) <= hours
    )


def build_feature_payload(
    *,
    as_of: datetime,
    config: dict[str, Any],
    macro_rows: list[dict[str, Any]],
    release_rows: list[dict[str, Any]],
    source_states: list[dict[str, Any]],
    dgs2_observations: list[Dgs2Observation],
    dgs2_error: str | None,
) -> tuple[dict[str, Any], float]:
    official_sources = set(config.get("official_macro_sources") or [])
    broad_sources = set(config.get("broad_macro_sources") or [])
    half_lives = config.get("half_life_hours") or {}
    official_hl = float(half_lives.get("official_macro", 12))
    broad_hl = float(half_lives.get("broad_macro_news", 6))
    surprise_hl = float(half_lives.get("surprise", 24))
    normalization = config.get("indicator_normalization") or {}

    official_rows = [r for r in macro_rows if r.get("source") in official_sources]
    broad_rows = [r for r in macro_rows if r.get("source") in broad_sources]

    official_decay = sum(
        decay_weight(_age_hours(as_of, parse_dt(r["available_at"])), official_hl)
        * float(r.get("importance") or r.get("confidence") or 1.0)
        for r in official_rows
        if parse_dt(r.get("available_at")) is not None
    )
    broad_decay = sum(
        decay_weight(_age_hours(as_of, parse_dt(r["available_at"])), broad_hl)
        * float(r.get("importance") or r.get("confidence") or 1.0)
        for r in broad_rows
        if parse_dt(r.get("available_at")) is not None
    )

    scored_releases: list[dict[str, Any]] = []
    for row in release_rows:
        score = normalized_surprise(
            str(row.get("indicator_key") or ""),
            row.get("actual"),
            row.get("consensus"),
            normalization,
        )
        if score is None:
            continue
        available_at = parse_dt(row.get("available_at"))
        if available_at is None:
            continue
        scored_releases.append(
            {
                **row,
                "available_at_dt": available_at,
                "policy_pressure_surprise": score,
                "decay_weight": decay_weight(
                    _age_hours(as_of, available_at), surprise_hl
                ),
            }
        )
    scored_releases.sort(key=lambda r: r["available_at_dt"])
    latest_release = scored_releases[-1] if scored_releases else None
    denom = sum(r["decay_weight"] for r in scored_releases)
    surprise_ema = (
        sum(r["policy_pressure_surprise"] * r["decay_weight"] for r in scored_releases)
        / denom
        if denom > 0
        else None
    )

    latest_official = None
    if official_rows:
        latest_official = max(
            official_rows,
            key=lambda r: parse_dt(r.get("available_at")) or datetime.min.replace(tzinfo=UTC),
        )
    reaction_anchor = (
        latest_release["available_at_dt"]
        if latest_release is not None
        else parse_dt(latest_official.get("available_at")) if latest_official else None
    )

    dgs2 = dgs2_latest_change(dgs2_observations)
    event_reaction = dgs2_event_reaction(dgs2_observations, reaction_anchor)

    state_by_source = {str(r.get("source")): r for r in source_states}
    healthy_official = 0
    for source in official_sources:
        state = state_by_source.get(source)
        if state and not state.get("last_error") and state.get("last_success_at"):
            healthy_official += 1
    official_health = (
        healthy_official / len(official_sources) if official_sources else 0.0
    )

    surprise_provider_ready = any(
        row.get("consensus") is not None and row.get("actual") is not None
        for row in release_rows
    )
    fed_repricing_ready = False

    weights = config.get("coverage_weights") or {}
    coverage = (
        float(weights.get("official_news", 0.40)) * official_health
        + float(weights.get("dgs2_daily_proxy", 0.25)) * (1.0 if dgs2_observations else 0.0)
        + float(weights.get("consensus_surprise_provider", 0.25))
        * (1.0 if surprise_provider_ready else 0.0)
        + float(weights.get("fed_repricing_provider", 0.10))
        * (1.0 if fed_repricing_ready else 0.0)
    )
    coverage = max(0.0, min(1.0, coverage))

    payload: dict[str, Any] = {
        "schema_version": "macro-event-feature-v1",
        "as_of": iso(as_of),
        "official_macro_count_6h": _count_within(official_rows, as_of, 6),
        "official_macro_count_24h": _count_within(official_rows, as_of, 24),
        "official_macro_count_72h": _count_within(official_rows, as_of, 72),
        "broad_macro_count_6h": _count_within(broad_rows, as_of, 6),
        "broad_macro_count_24h": _count_within(broad_rows, as_of, 24),
        "official_macro_decay": official_decay,
        "broad_macro_decay": broad_decay,
        "latest_official_source": latest_official.get("source") if latest_official else None,
        "latest_official_title": latest_official.get("title") if latest_official else None,
        "latest_official_available_at": (
            iso(parse_dt(latest_official.get("available_at")))
            if latest_official and parse_dt(latest_official.get("available_at"))
            else None
        ),
        "release_observation_count_72h": len(release_rows),
        "consensus_surprise_count_72h": len(scored_releases),
        "policy_pressure_surprise_latest": (
            latest_release["policy_pressure_surprise"] if latest_release else None
        ),
        "policy_pressure_surprise_decay_ema": surprise_ema,
        "latest_surprise_indicator": (
            latest_release.get("indicator_key") if latest_release else None
        ),
        "latest_surprise_actual": latest_release.get("actual") if latest_release else None,
        "latest_surprise_consensus": (
            latest_release.get("consensus") if latest_release else None
        ),
        "latest_surprise_available_at": (
            iso(latest_release["available_at_dt"]) if latest_release else None
        ),
        "us2y_series": str((config.get("fred") or {}).get("series_id", "DGS2")),
        "us2y_latest_date": dgs2["latest_date"],
        "us2y_latest_pct": dgs2["latest_pct"],
        "us2y_previous_date": dgs2["previous_date"],
        "us2y_previous_pct": dgs2["previous_pct"],
        "us2y_change_bps_1d": dgs2["change_bps_1d"],
        "us2y_event_date_et": event_reaction["event_date_et"],
        "us2y_event_day_pct": event_reaction["event_day_pct"],
        "us2y_event_prior_day_pct": event_reaction["prior_day_pct"],
        "us2y_event_reaction_bps": event_reaction["reaction_bps"],
        "us2y_reaction_quality": str(
            (config.get("fred") or {}).get("reaction_quality", "DAILY_PROXY")
        ),
        "us2y_error": dgs2_error,
        "fed_policy_repricing_bps": None,
        "fed_policy_repricing_quality": "UNAVAILABLE",
        "component_status": {
            "official_news": {
                "status": "READY" if official_health == 1.0 else "PARTIAL",
                "healthy_sources": healthy_official,
                "configured_sources": len(official_sources),
            },
            "dgs2_daily_proxy": {
                "status": "READY" if dgs2_observations else "UNAVAILABLE",
                "quality": str(
                    (config.get("fred") or {}).get("reaction_quality", "DAILY_PROXY")
                ),
            },
            "consensus_surprise_provider": {
                "status": "READY" if surprise_provider_ready else "UNAVAILABLE"
            },
            "fed_repricing_provider": {"status": "UNAVAILABLE"},
        },
        "r51_scoring_enabled": False,
        "trade_execution_enabled": False,
        "challenger_only": True,
    }
    return payload, coverage


def fetch_inputs(
    conn: psycopg.Connection,
    as_of: datetime,
    lookback_hours: int,
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    since = as_of - timedelta(hours=lookback_hours)
    macro_rows = conn.execute(
        """
        SELECT a.article_id,a.source,a.title,a.available_at,
               e.importance,e.confidence
        FROM public.news_article a
        JOIN public.news_event e ON e.article_id=a.article_id
        WHERE e.event_type='MACRO'
          AND a.available_at >= %s
          AND a.available_at <= %s
        ORDER BY a.available_at
        """,
        (since, as_of),
    ).fetchall()
    release_rows = conn.execute(
        """
        SELECT observation_id,indicator_key,event_name,market,
               release_at,available_at,actual,consensus,previous,
               unit,source,source_item_id,time_quality,payload
        FROM public.macro_release_observation
        WHERE available_at >= %s
          AND available_at <= %s
        ORDER BY available_at
        """,
        (since, as_of),
    ).fetchall()
    configured = list(
        dict.fromkeys(
            (config.get("official_macro_sources") or [])
            + (config.get("broad_macro_sources") or [])
        )
    )
    source_states: list[dict[str, Any]] = []
    if configured:
        source_states = conn.execute(
            """
            SELECT source,last_attempt_at,last_success_at,last_error_at,last_error,
                   rows_seen,rows_inserted,rows_duplicate,payload,updated_at
            FROM public.news_source_state
            WHERE source = ANY(%s)
            """,
            (configured,),
        ).fetchall()
    return list(macro_rows), list(release_rows), list(source_states)


def build_snapshot(
    db_url: str,
    config: dict[str, Any],
    as_of: datetime | None = None,
) -> dict[str, Any]:
    as_of = (as_of or utc_now()).astimezone(UTC).replace(second=0, microsecond=0)
    lookback = int(config.get("lookback_hours", 72))
    dgs2, dgs2_error = fetch_dgs2(config, as_of)
    with psycopg.connect(db_url, connect_timeout=15, row_factory=dict_row) as conn:
        macro_rows, release_rows, states = fetch_inputs(conn, as_of, lookback, config)
        features, coverage = build_feature_payload(
            as_of=as_of,
            config=config,
            macro_rows=macro_rows,
            release_rows=release_rows,
            source_states=states,
            dgs2_observations=dgs2,
            dgs2_error=dgs2_error,
        )
        run_id = "MACRO-" + as_of.strftime("%Y%m%dT%H%MZ")
        conn.execute(
            """
            INSERT INTO public.news_feature_snapshot(
              market,symbol,as_of,feature_version,features,coverage_confidence,run_id
            ) VALUES('GLOBAL','GLOBAL',%s,%s,%s::jsonb,%s,%s)
            ON CONFLICT(market,symbol,as_of,feature_version) DO UPDATE SET
              features=excluded.features,
              coverage_confidence=excluded.coverage_confidence,
              run_id=excluded.run_id,
              created_at=now()
            """,
            (
                as_of,
                str(config.get("feature_version", FEATURE_VERSION)),
                json.dumps(features, ensure_ascii=False, sort_keys=True),
                coverage,
                run_id,
            ),
        )
        conn.commit()
    return {
        "run_id": run_id,
        "as_of": iso(as_of),
        "coverage_confidence": coverage,
        "features": features,
    }


def _float_or_none(value: str | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def import_csv(db_url: str, path: Path) -> dict[str, int]:
    required = {
        "indicator_key",
        "event_name",
        "release_at",
        "available_at",
        "source",
        "time_quality",
    }
    seen = inserted = 0
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing CSV columns: {sorted(missing)}")
        with psycopg.connect(db_url, connect_timeout=15) as conn:
            for raw in reader:
                seen += 1
                release_at = parse_dt(raw.get("release_at"))
                available_at = parse_dt(raw.get("available_at"))
                if release_at is None or available_at is None:
                    raise ValueError(f"row {seen}: invalid release_at/available_at")
                if available_at < release_at:
                    raise ValueError(f"row {seen}: available_at precedes release_at")
                row: dict[str, Any] = {
                    **raw,
                    "release_at": iso(release_at),
                    "available_at": iso(available_at),
                }
                obs_id = (raw.get("observation_id") or "").strip() or stable_observation_id(row)
                payload_text = (raw.get("payload_json") or "").strip()
                payload = json.loads(payload_text) if payload_text else {}
                cur = conn.execute(
                    """
                    INSERT INTO public.macro_release_observation(
                      observation_id,indicator_key,event_name,market,
                      release_at,available_at,actual,consensus,previous,
                      unit,source,source_item_id,time_quality,payload,updated_at
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,now())
                    ON CONFLICT(observation_id) DO UPDATE SET
                      actual=excluded.actual,
                      consensus=excluded.consensus,
                      previous=excluded.previous,
                      payload=excluded.payload,
                      updated_at=now()
                    RETURNING (xmax = 0) AS inserted
                    """,
                    (
                        obs_id,
                        raw["indicator_key"].strip(),
                        raw["event_name"].strip(),
                        (raw.get("market") or "GLOBAL").strip().upper(),
                        release_at,
                        available_at,
                        _float_or_none(raw.get("actual")),
                        _float_or_none(raw.get("consensus")),
                        _float_or_none(raw.get("previous")),
                        (raw.get("unit") or "").strip() or None,
                        raw["source"].strip(),
                        (raw.get("source_item_id") or "").strip() or None,
                        raw["time_quality"].strip(),
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    ),
                ).fetchone()
                inserted += int(bool(cur and cur[0]))
            conn.commit()
    return {"seen": seen, "inserted": inserted}


def latest_status(db_url: str, feature_version: str) -> dict[str, Any] | None:
    with psycopg.connect(db_url, connect_timeout=15, row_factory=dict_row) as conn:
        row = conn.execute(
            """
            SELECT market,symbol,as_of,feature_version,features,
                   coverage_confidence,run_id,created_at
            FROM public.news_feature_snapshot
            WHERE market='GLOBAL' AND symbol='GLOBAL' AND feature_version=%s
            ORDER BY as_of DESC
            LIMIT 1
            """,
            (feature_version,),
        ).fetchone()
        return dict(row) if row else None


def selftest() -> None:
    assert abs(decay_weight(12, 12) - 0.5) < 1e-12
    norm = {
        "CPI_HEADLINE_YOY": {"scale": 0.1, "policy_sign": 1.0},
        "UNEMPLOYMENT_RATE": {"scale": 0.1, "policy_sign": -1.0},
    }
    assert normalized_surprise("CPI_HEADLINE_YOY", 3.2, 3.0, norm) == 2.0
    assert normalized_surprise("UNEMPLOYMENT_RATE", 4.2, 4.1, norm) == -1.0
    obs = parse_fred_observations(
        {
            "observations": [
                {"date": "2026-09-16", "value": "4.74"},
                {"date": "2026-09-17", "value": "4.67"},
            ]
        }
    )
    change = dgs2_latest_change(obs)
    assert round(float(change["change_bps_1d"]), 6) == -7.0
    reaction = dgs2_event_reaction(obs, datetime(2026, 9, 17, 12, 30, tzinfo=UTC))
    assert round(float(reaction["reaction_bps"]), 6) == -7.0
    print("MACRO_EVENT_FEATURE_V1_SELFTEST_OK")


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Kalman Macro Event Feature Layer V1")
    parser.add_argument("command", choices=["build", "import-csv", "status", "selftest"])
    parser.add_argument(
        "--config",
        default=os.environ.get(
            "KALMAN_MACRO_FEATURE_CONFIG",
            "/opt/kalman/app/config/macro-event-features-v1.json",
        ),
    )
    parser.add_argument("--input-csv")
    parser.add_argument("--as-of")
    args = parser.parse_args()

    if args.command == "selftest":
        selftest()
        return

    config = load_config(Path(args.config))
    db_url = os.environ.get("DATABASE_URL_WRITER") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL_WRITER/DATABASE_URL missing")

    if args.command == "build":
        if not env_bool("KALMAN_MACRO_FEATURES_ENABLED", False):
            print("[MACRO][BUILD] disabled by KALMAN_MACRO_FEATURES_ENABLED")
            return
        as_of = parse_dt(args.as_of) if args.as_of else None
        result = build_snapshot(db_url, config, as_of)
        print("[MACRO][BUILD]", json.dumps(result, ensure_ascii=False, sort_keys=True))
    elif args.command == "import-csv":
        if not args.input_csv:
            raise SystemExit("--input-csv is required")
        result = import_csv(db_url, Path(args.input_csv))
        print("[MACRO][IMPORT]", json.dumps(result, sort_keys=True))
    elif args.command == "status":
        row = latest_status(
            db_url, str(config.get("feature_version", FEATURE_VERSION))
        )
        print("[MACRO][STATUS]", json.dumps(row, default=str, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
