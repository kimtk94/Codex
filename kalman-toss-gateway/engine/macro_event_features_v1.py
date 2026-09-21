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

from engine.macro_consensus_provider_v1 import (
    refresh_consensus_observations,
    within_active_window,
)


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


def fetch_fred_series(
    config: dict[str, Any],
    as_of: datetime,
    series_id: str,
) -> tuple[list[Dgs2Observation], str | None]:
    fred = config.get("fred") or {}
    if not fred.get("enabled", True):
        return [], "DISABLED"
    api_key = (os.environ.get("FRED_API_KEY") or os.environ.get("FRED_KEY") or "").strip()
    if not api_key:
        return [], "FRED_API_KEY_MISSING"
    days = int(fred.get("observation_days", 14))
    start = (as_of - timedelta(days=days)).date().isoformat()
    params = {
        "series_id": series_id,
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


def fetch_dgs2(config: dict[str, Any], as_of: datetime) -> tuple[list[Dgs2Observation], str | None]:
    fred = config.get("fred") or {}
    return fetch_fred_series(config, as_of, str(fred.get("series_id", "DGS2")))


def fetch_policy_proxy_rate(
    config: dict[str, Any], as_of: datetime
) -> tuple[list[Dgs2Observation], str | None]:
    fred = config.get("fred") or {}
    return fetch_fred_series(
        config, as_of, str(fred.get("policy_proxy_series_id", "DFF"))
    )


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


def rate_spread_latest_change(
    market_rate: list[Dgs2Observation],
    policy_rate: list[Dgs2Observation],
) -> dict[str, Any]:
    m = {o.date.date(): o.value_pct for o in market_rate}
    p = {o.date.date(): o.value_pct for o in policy_rate}
    common = sorted(set(m) & set(p))
    if not common:
        return {
            "latest_date": None,
            "latest_spread_bps": None,
            "previous_date": None,
            "previous_spread_bps": None,
            "change_bps_1d": None,
        }
    latest_date = common[-1]
    latest_spread = (m[latest_date] - p[latest_date]) * 100.0
    previous_date = common[-2] if len(common) >= 2 else None
    previous_spread = (
        (m[previous_date] - p[previous_date]) * 100.0
        if previous_date is not None
        else None
    )
    return {
        "latest_date": latest_date.isoformat(),
        "latest_spread_bps": latest_spread,
        "previous_date": previous_date.isoformat() if previous_date else None,
        "previous_spread_bps": previous_spread,
        "change_bps_1d": (
            latest_spread - previous_spread if previous_spread is not None else None
        ),
    }


def rate_spread_event_reaction(
    market_rate: list[Dgs2Observation],
    policy_rate: list[Dgs2Observation],
    event_at: datetime | None,
) -> dict[str, Any]:
    if event_at is None:
        return {"event_date_et": None, "reaction_bps": None}
    event_date = event_at.astimezone(NY).date()
    m = {o.date.date(): o.value_pct for o in market_rate}
    p = {o.date.date(): o.value_pct for o in policy_rate}
    common = sorted(set(m) & set(p))
    if event_date not in common:
        return {"event_date_et": event_date.isoformat(), "reaction_bps": None}
    prior = [d for d in common if d < event_date]
    if not prior:
        return {"event_date_et": event_date.isoformat(), "reaction_bps": None}
    prior_date = prior[-1]
    event_spread = (m[event_date] - p[event_date]) * 100.0
    prior_spread = (m[prior_date] - p[prior_date]) * 100.0
    return {
        "event_date_et": event_date.isoformat(),
        "prior_date": prior_date.isoformat(),
        "event_spread_bps": event_spread,
        "prior_spread_bps": prior_spread,
        "reaction_bps": event_spread - prior_spread,
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


def select_us_reaction_anchor(
    release_rows: list[dict[str, Any]],
    official_rows: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[datetime | None, dict[str, Any]]:
    structured_with_consensus: list[tuple[datetime, dict[str, Any]]] = []
    structured_any: list[tuple[datetime, dict[str, Any]]] = []
    for row in release_rows:
        if str(row.get("market") or "").upper() != "US":
            continue
        available_at = parse_dt(row.get("available_at"))
        if available_at is None:
            continue
        item = (available_at, row)
        structured_any.append(item)
        if row.get("actual") is not None and row.get("consensus") is not None:
            structured_with_consensus.append(item)

    allowed_sources = set(
        config.get("us_reaction_anchor_sources")
        or ("fed_monetary", "bls_cpi", "bls_employment", "bls_jolts", "bea_releases")
    )
    official_candidates: list[tuple[datetime, dict[str, Any]]] = []
    for row in official_rows:
        if str(row.get("source") or "") not in allowed_sources:
            continue
        available_at = parse_dt(row.get("available_at"))
        if available_at is None:
            continue
        official_candidates.append((available_at, row))

    structured = structured_with_consensus or structured_any
    latest_structured = max(structured, key=lambda x: x[0]) if structured else None
    latest_official = (
        max(official_candidates, key=lambda x: x[0]) if official_candidates else None
    )

    duplicate_minutes = float(config.get("structured_official_match_minutes", 30.0))
    if latest_structured and latest_official:
        s_at, s_row = latest_structured
        o_at, o_row = latest_official
        if abs((s_at - o_at).total_seconds()) <= duplicate_minutes * 60.0:
            return s_at, {
                "kind": "STRUCTURED_US_RELEASE",
                "source": s_row.get("source"),
                "event_name": s_row.get("event_name"),
                "indicator_key": s_row.get("indicator_key"),
                "available_at": iso(s_at),
            }
        if o_at > s_at:
            return o_at, {
                "kind": "US_OFFICIAL_NEWS_PROXY",
                "source": o_row.get("source"),
                "event_name": o_row.get("title"),
                "indicator_key": None,
                "available_at": iso(o_at),
            }

    if latest_structured:
        available_at, row = latest_structured
        return available_at, {
            "kind": "STRUCTURED_US_RELEASE",
            "source": row.get("source"),
            "event_name": row.get("event_name"),
            "indicator_key": row.get("indicator_key"),
            "available_at": iso(available_at),
        }

    if latest_official:
        available_at, row = latest_official
        return available_at, {
            "kind": "US_OFFICIAL_NEWS_PROXY",
            "source": row.get("source"),
            "event_name": row.get("title"),
            "indicator_key": None,
            "available_at": iso(available_at),
        }

    return None, {
        "kind": "NONE",
        "source": None,
        "event_name": None,
        "indicator_key": None,
        "available_at": None,
    }


def select_matched_policy_repricing(
    policy_rows: list[dict[str, Any]],
    reaction_anchor: datetime | None,
    max_gap_hours: float,
) -> tuple[dict[str, Any] | None, float | None]:
    if reaction_anchor is None:
        return None, None
    candidates: list[tuple[float, datetime, dict[str, Any]]] = []
    max_gap_seconds = max(0.0, float(max_gap_hours)) * 3600.0
    for row in policy_rows:
        event_at = parse_dt(row.get("event_at"))
        available_at = parse_dt(row.get("available_at"))
        if event_at is None or available_at is None or row.get("repricing_bps") is None:
            continue
        gap_seconds = abs((event_at - reaction_anchor).total_seconds())
        if gap_seconds > max_gap_seconds:
            continue
        candidates.append((gap_seconds, available_at, row))
    if not candidates:
        return None, None
    gap_seconds, _, row = min(candidates, key=lambda x: (x[0], -x[1].timestamp()))
    return row, gap_seconds / 60.0


def macro_event_family(
    reaction_anchor_meta: dict[str, Any],
    config: dict[str, Any],
) -> str:
    scoring = config.get("event_scoring") or {}
    family_map = scoring.get("indicator_family") or {}
    indicator = str(reaction_anchor_meta.get("indicator_key") or "")
    if indicator and indicator in family_map:
        return str(family_map[indicator]).upper()

    source = str(reaction_anchor_meta.get("source") or "")
    if source == "fed_monetary":
        return "FOMC"
    if source == "bls_cpi":
        return "CPI"
    if source == "bls_employment":
        return "NFP"
    return "OTHER"


def select_event_bundle(
    scored_releases: list[dict[str, Any]],
    reaction_anchor: datetime | None,
    event_family: str,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    if reaction_anchor is None or event_family not in {"CPI", "NFP"}:
        return []
    scoring = config.get("event_scoring") or {}
    family_map = scoring.get("indicator_family") or {}
    window_minutes = max(
        0.0, float(scoring.get("bundle_window_minutes", 10.0))
    )
    out: list[dict[str, Any]] = []
    for row in scored_releases:
        indicator = str(row.get("indicator_key") or "")
        if str(family_map.get(indicator) or "").upper() != event_family:
            continue
        available_at = row.get("available_at_dt")
        if not isinstance(available_at, datetime):
            available_at = parse_dt(row.get("available_at"))
        if available_at is None:
            continue
        if abs((available_at - reaction_anchor).total_seconds()) <= window_minutes * 60.0:
            out.append(row)
    return sorted(out, key=lambda r: str(r.get("indicator_key") or ""))


def _clip5(value: float | None) -> float | None:
    if value is None:
        return None
    return max(-5.0, min(5.0, float(value)))


def compute_shadow_event_score(
    *,
    event_family: str,
    event_bundle: list[dict[str, Any]],
    reaction_z: float | None,
    matched_policy: dict[str, Any] | None,
    policy_proxy_event_bps: float | None,
    config: dict[str, Any],
) -> dict[str, Any]:
    scoring = config.get("event_scoring") or {}
    policy_scale = max(1e-9, float(scoring.get("policy_repricing_scale_bps", 5.0)))
    provider_policy_z = (
        _clip5(float(matched_policy["repricing_bps"]) / policy_scale)
        if matched_policy is not None and matched_policy.get("repricing_bps") is not None
        else None
    )
    proxy_policy_z = (
        _clip5(float(policy_proxy_event_bps) / policy_scale)
        if policy_proxy_event_bps is not None
        else None
    )
    policy_z = provider_policy_z if provider_policy_z is not None else proxy_policy_z
    policy_source = (
        "FUTURES_PROVIDER"
        if provider_policy_z is not None
        else "DGS2_DFF_PROXY"
        if proxy_policy_z is not None
        else None
    )

    bundle_scores = [
        float(r["policy_pressure_surprise"])
        for r in event_bundle
        if r.get("policy_pressure_surprise") is not None
    ]
    bundle_surprise = (
        sum(bundle_scores) / len(bundle_scores) if bundle_scores else None
    )

    weights_by_family = scoring.get("weights") or {}
    weights = weights_by_family.get(event_family) or {}
    blockers: list[str] = []
    components: dict[str, float | None] = {
        "bundle_surprise": bundle_surprise,
        "us2y_reaction_z": reaction_z,
        "policy_confirmation_z": policy_z,
    }

    if event_family in {"CPI", "NFP"}:
        if bundle_surprise is None:
            blockers.append("EVENT_BUNDLE_SURPRISE_UNAVAILABLE")
        if reaction_z is None:
            blockers.append("US2Y_EVENT_REACTION_UNAVAILABLE")
        if policy_z is None:
            blockers.append("POLICY_REPRICING_CONFIRMATION_UNAVAILABLE")
    elif event_family == "FOMC":
        if reaction_z is None:
            blockers.append("US2Y_EVENT_REACTION_UNAVAILABLE")
        if policy_z is None:
            blockers.append("POLICY_REPRICING_CONFIRMATION_UNAVAILABLE")
    else:
        blockers.append("UNSUPPORTED_EVENT_FAMILY")

    score = None
    if not blockers:
        if event_family in {"CPI", "NFP"}:
            score = (
                float(weights.get("surprise", 0.50)) * float(bundle_surprise)
                + float(weights.get("us2y", 0.30)) * float(reaction_z)
                + float(weights.get("policy", 0.20)) * float(policy_z)
            )
        elif event_family == "FOMC":
            score = (
                float(weights.get("us2y", 0.45)) * float(reaction_z)
                + float(weights.get("policy", 0.55)) * float(policy_z)
            )
        score = round(float(_clip5(score)), 12)

    neutral_band = abs(float(scoring.get("neutral_band", 0.50)))
    direction = (
        "HAWKISH_TIGHTENING"
        if score is not None and score > neutral_band
        else "DOVISH_EASING"
        if score is not None and score < -neutral_band
        else "NEUTRAL"
        if score is not None
        else "BLOCKED"
    )
    return {
        "event_family": event_family,
        "score": score,
        "direction": direction,
        "ready": score is not None,
        "blockers": blockers,
        "bundle_surprise": bundle_surprise,
        "bundle_indicators": [
            str(r.get("indicator_key") or "") for r in event_bundle
        ],
        "bundle_component_scores": {
            str(r.get("indicator_key") or ""): r.get("policy_pressure_surprise")
            for r in event_bundle
        },
        "us2y_reaction_z": reaction_z,
        "policy_confirmation_z": policy_z,
        "policy_confirmation_source": policy_source,
        "score_range": [-5.0, 5.0],
        "positive_direction": "HAWKISH_TIGHTENING",
        "shadow_only": True,
    }



def compute_free_reaction_shadow_score(
    *,
    event_family: str,
    reaction_z: float | None,
    policy_proxy_event_bps: float | None,
    config: dict[str, Any],
) -> dict[str, Any]:
    scoring = config.get("event_scoring") or {}
    policy_scale = max(
        1e-9, float(scoring.get("policy_repricing_scale_bps", 5.0))
    )
    policy_proxy_z = (
        _clip5(float(policy_proxy_event_bps) / policy_scale)
        if policy_proxy_event_bps is not None
        else None
    )
    blockers: list[str] = []
    if event_family not in {"CPI", "NFP", "FOMC"}:
        blockers.append("UNSUPPORTED_EVENT_FAMILY")
    if reaction_z is None:
        blockers.append("US2Y_EVENT_REACTION_UNAVAILABLE")
    if policy_proxy_z is None:
        blockers.append("DGS2_DFF_EVENT_CONFIRMATION_UNAVAILABLE")

    score = None
    weights = (scoring.get("weights") or {}).get(event_family) or {}
    if not blockers:
        if event_family in {"CPI", "NFP"}:
            us2y_weight = float(weights.get("us2y", 0.30))
            policy_weight = float(weights.get("policy", 0.20))
        else:
            us2y_weight = float(weights.get("us2y", 0.45))
            policy_weight = float(weights.get("policy", 0.55))
        denom = us2y_weight + policy_weight
        if denom <= 0:
            blockers.append("INVALID_FREE_REACTION_WEIGHTS")
        else:
            score = _clip5(
                (us2y_weight / denom) * float(reaction_z)
                + (policy_weight / denom) * float(policy_proxy_z)
            )
            score = round(float(score), 12)

    neutral_band = abs(float(scoring.get("neutral_band", 0.50)))
    direction = (
        "HAWKISH_TIGHTENING"
        if score is not None and score > neutral_band
        else "DOVISH_EASING"
        if score is not None and score < -neutral_band
        else "NEUTRAL"
        if score is not None
        else "BLOCKED"
    )
    return {
        "event_family": event_family,
        "score": score,
        "direction": direction,
        "ready": score is not None,
        "blockers": blockers,
        "us2y_reaction_z": reaction_z,
        "policy_proxy_confirmation_z": policy_proxy_z,
        "policy_confirmation_source": "DGS2_DFF_PROXY" if policy_proxy_z is not None else None,
        "quality": "DAILY_RATE_PROXY_ONLY",
        "free_only": True,
        "shadow_only": True,
        "score_range": [-5.0, 5.0],
        "positive_direction": "HAWKISH_TIGHTENING",
    }

def target_market_indicator_weight(
    config: dict[str, Any],
    target_market: str,
    indicator_key: str,
) -> float:
    impact = config.get("target_market_impact") or {}
    target = ((impact.get("targets") or {}).get(target_market.upper()) or {})
    spec = ((target.get("indicators") or {}).get(indicator_key) or {})
    if not spec:
        return 0.0
    if isinstance(spec, (int, float)):
        return max(0.0, float(spec))
    tier = str(spec.get("tier") or "").upper()
    return max(0.0, float((impact.get("tier_weights") or {}).get(tier, 0.0)))


def target_market_surprise_index(
    scored_releases: list[dict[str, Any]],
    target_market: str,
    config: dict[str, Any],
    *,
    origin_market: str | None = None,
) -> dict[str, Any]:
    contributors: list[dict[str, Any]] = []
    numerator = 0.0
    denominator = 0.0
    origin_filter = origin_market.upper() if origin_market else None
    for row in scored_releases:
        row_origin = str(row.get("market") or "").upper()
        if origin_filter and row_origin != origin_filter:
            continue
        indicator = str(row.get("indicator_key") or "")
        impact_weight = target_market_indicator_weight(config, target_market, indicator)
        if impact_weight <= 0:
            continue
        decay = max(0.0, float(row.get("decay_weight") or 0.0))
        surprise = row.get("policy_pressure_surprise")
        if surprise is None or decay <= 0:
            continue
        effective_weight = impact_weight * decay
        numerator += float(surprise) * effective_weight
        denominator += effective_weight
        contributors.append({
            "indicator_key": indicator,
            "origin_market": row_origin,
            "impact_weight": impact_weight,
            "decay_weight": decay,
            "effective_weight": effective_weight,
            "surprise": float(surprise),
            "available_at": (
                iso(row["available_at_dt"])
                if isinstance(row.get("available_at_dt"), datetime)
                else row.get("available_at")
            ),
        })
    contributors.sort(key=lambda r: str(r.get("available_at") or ""))
    score = round(numerator / denominator, 12) if denominator > 0 else None
    return {
        "target_market": target_market.upper(),
        "origin_market_filter": origin_filter,
        "score": score,
        "contributor_count": len(contributors),
        "latest_indicator": contributors[-1]["indicator_key"] if contributors else None,
        "contributors": contributors[-12:],
        "weight_semantics": str(
            (config.get("target_market_impact") or {}).get(
                "semantics", "ordinal_research_prior"
            )
        ),
    }


def target_market_event_score(
    shadow_score: dict[str, Any],
    target_market: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    impact = config.get("target_market_impact") or {}
    target = ((impact.get("targets") or {}).get(target_market.upper()) or {})
    family = str(shadow_score.get("event_family") or "OTHER").upper()
    weight = float((target.get("event_family_weights") or {}).get(family, 0.0))
    raw = shadow_score.get("score")
    score = round(float(raw) * weight, 12) if raw is not None and weight > 0 else None
    return {
        "target_market": target_market.upper(),
        "event_family": family,
        "source_score": raw,
        "impact_weight": weight,
        "score": score,
        "ready": score is not None,
        "shadow_only": True,
    }


def score_release_market(
    *,
    release_rows: list[dict[str, Any]],
    market: str,
    as_of: datetime,
    normalization: dict[str, Any],
    surprise_half_life_hours: float,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, float | None]:
    scored: list[dict[str, Any]] = []
    market_key = market.upper()
    for row in release_rows:
        if str(row.get("market") or "").upper() != market_key:
            continue
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
        scored.append(
            {
                **row,
                "available_at_dt": available_at,
                "policy_pressure_surprise": score,
                "decay_weight": decay_weight(
                    _age_hours(as_of, available_at), surprise_half_life_hours
                ),
            }
        )
    scored.sort(key=lambda r: r["available_at_dt"])
    latest = scored[-1] if scored else None
    denom = sum(r["decay_weight"] for r in scored)
    decay_ema = (
        sum(r["policy_pressure_surprise"] * r["decay_weight"] for r in scored)
        / denom
        if denom > 0
        else None
    )
    return scored, latest, decay_ema


def build_feature_payload(
    *,
    as_of: datetime,
    config: dict[str, Any],
    macro_rows: list[dict[str, Any]],
    release_rows: list[dict[str, Any]],
    policy_rows: list[dict[str, Any]],
    source_states: list[dict[str, Any]],
    dgs2_observations: list[Dgs2Observation],
    dgs2_error: str | None,
    policy_rate_observations: list[Dgs2Observation],
    policy_rate_error: str | None,
) -> tuple[dict[str, Any], float]:
    official_sources = set(config.get("official_macro_sources") or [])
    broad_sources = set(config.get("broad_macro_sources") or [])
    half_lives = config.get("half_life_hours") or {}
    official_hl = float(half_lives.get("official_macro", 12))
    broad_hl = float(half_lives.get("broad_macro_news", 6))
    surprise_hl = float(half_lives.get("surprise", 24))
    normalization = config.get("indicator_normalization") or {}
    fred_cfg = config.get("fred") or {}

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

    scored_releases, latest_release, surprise_ema = score_release_market(
        release_rows=release_rows,
        market="US",
        as_of=as_of,
        normalization=normalization,
        surprise_half_life_hours=surprise_hl,
    )
    kr_scored_releases, kr_latest_release, kr_surprise_ema = score_release_market(
        release_rows=release_rows,
        market="KR",
        as_of=as_of,
        normalization=normalization,
        surprise_half_life_hours=surprise_hl,
    )

    all_scored_releases = scored_releases + kr_scored_releases
    us_priority_surprise = target_market_surprise_index(
        all_scored_releases, "US", config
    )
    kr_priority_surprise = target_market_surprise_index(
        all_scored_releases, "KR", config
    )
    kr_domestic_priority_surprise = target_market_surprise_index(
        all_scored_releases, "KR", config, origin_market="KR"
    )
    kr_us_spillover_surprise = target_market_surprise_index(
        all_scored_releases, "KR", config, origin_market="US"
    )

    latest_official = None
    if official_rows:
        latest_official = max(
            official_rows,
            key=lambda r: parse_dt(r.get("available_at"))
            or datetime.min.replace(tzinfo=UTC),
        )

    reaction_anchor, reaction_anchor_meta = select_us_reaction_anchor(
        release_rows, official_rows, config
    )

    dgs2 = dgs2_latest_change(dgs2_observations)
    event_reaction = dgs2_event_reaction(dgs2_observations, reaction_anchor)

    proxy_latest = rate_spread_latest_change(
        dgs2_observations, policy_rate_observations
    )
    proxy_event = rate_spread_event_reaction(
        dgs2_observations, policy_rate_observations, reaction_anchor
    )

    policy_match_hours = float(config.get("policy_repricing_match_hours", 6.0))
    matched_policy, policy_event_gap_minutes = select_matched_policy_repricing(
        policy_rows, reaction_anchor, policy_match_hours
    )
    event_family = macro_event_family(reaction_anchor_meta, config)
    event_bundle = select_event_bundle(
        scored_releases, reaction_anchor, event_family, config
    )

    state_by_source = {str(r.get("source")): r for r in source_states}
    healthy_official = 0
    for source in official_sources:
        state = state_by_source.get(source)
        if state and not state.get("last_error") and state.get("last_success_at"):
            healthy_official += 1
    official_health = (
        healthy_official / len(official_sources) if official_sources else 0.0
    )

    surprise_provider_ready = latest_release is not None
    fed_repricing_ready = matched_policy is not None
    fed_proxy_ready = proxy_latest.get("latest_spread_bps") is not None
    policy_proxy_event_ready = proxy_event.get("reaction_bps") is not None

    reaction_scale_bps = float(fred_cfg.get("reaction_scale_bps", 5.0))
    reaction_z = (
        max(-5.0, min(5.0, float(event_reaction["reaction_bps"]) / reaction_scale_bps))
        if event_reaction.get("reaction_bps") is not None and reaction_scale_bps > 0
        else None
    )
    latest_surprise = (
        float(latest_release["policy_pressure_surprise"])
        if latest_release is not None
        else None
    )

    shadow_score = compute_shadow_event_score(
        event_family=event_family,
        event_bundle=event_bundle,
        reaction_z=reaction_z,
        matched_policy=matched_policy,
        policy_proxy_event_bps=proxy_event.get("reaction_bps"),
        config=config,
    )
    free_reaction_score = compute_free_reaction_shadow_score(
        event_family=event_family,
        reaction_z=reaction_z,
        policy_proxy_event_bps=proxy_event.get("reaction_bps"),
        config=config,
    )
    us_target_event_score = target_market_event_score(shadow_score, "US", config)
    kr_us_spillover_event_score = target_market_event_score(shadow_score, "KR", config)
    event_bundle_surprise = shadow_score.get("bundle_surprise")
    shock_interaction = (
        float(event_bundle_surprise) * reaction_z
        if event_bundle_surprise is not None and reaction_z is not None
        else None
    )
    policy_alignment = (
        1
        if event_bundle_surprise is not None
        and event_reaction.get("reaction_bps") is not None
        and float(event_bundle_surprise) * float(event_reaction["reaction_bps"]) > 0
        else -1
        if event_bundle_surprise is not None
        and event_reaction.get("reaction_bps") is not None
        and float(event_bundle_surprise) * float(event_reaction["reaction_bps"]) < 0
        else 0
        if event_bundle_surprise is not None and event_reaction.get("reaction_bps") == 0
        else None
    )

    us2y_event_ready = event_reaction.get("reaction_bps") is not None
    policy_confirmation_ready = fed_repricing_ready or policy_proxy_event_ready
    signal_blockers = list(shadow_score.get("blockers") or [])
    if reaction_anchor is None and "NO_US_EVENT_ANCHOR" not in signal_blockers:
        signal_blockers.insert(0, "NO_US_EVENT_ANCHOR")
    macro_event_signal_ready = bool(shadow_score.get("ready")) and reaction_anchor is not None
    macro_event_signal_full_provider_ready = (
        macro_event_signal_ready
        and matched_policy is not None
        and shadow_score.get("policy_confirmation_source") == "FUTURES_PROVIDER"
    )
    macro_event_signal_quality = (
        "FULL_PROVIDER_CONFIRMATION"
        if macro_event_signal_full_provider_ready
        else "DGS2_DFF_PROXY_CONFIRMATION"
        if macro_event_signal_ready
        and shadow_score.get("policy_confirmation_source") == "DGS2_DFF_PROXY"
        else "INCOMPLETE"
    )

    weights = config.get("coverage_weights") or {}
    coverage = (
        float(weights.get("official_news", 0.35)) * official_health
        + float(weights.get("dgs2_daily_proxy", 0.20))
        * (1.0 if dgs2_observations else 0.0)
        + float(weights.get("consensus_surprise_provider", 0.25))
        * (1.0 if surprise_provider_ready else 0.0)
        + float(weights.get("fed_repricing_provider", 0.10))
        * (1.0 if fed_repricing_ready else 0.0)
        + float(weights.get("fed_repricing_proxy", 0.10))
        * (1.0 if fed_proxy_ready else 0.0)
    )
    coverage = max(0.0, min(1.0, coverage))

    payload: dict[str, Any] = {
        "schema_version": "macro-event-feature-v1.8",
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
        "us_release_observation_count_72h": sum(
            1 for row in release_rows if str(row.get("market") or "").upper() == "US"
        ),
        "kr_release_observation_count_72h": sum(
            1 for row in release_rows if str(row.get("market") or "").upper() == "KR"
        ),
        "consensus_surprise_count_72h": len(scored_releases),
        "policy_pressure_surprise_latest": latest_surprise,
        "policy_pressure_surprise_decay_ema": surprise_ema,
        "us_consensus_surprise_count_72h": len(scored_releases),
        "us_policy_pressure_surprise_latest": latest_surprise,
        "us_policy_pressure_surprise_decay_ema": surprise_ema,
        "kr_consensus_surprise_count_72h": len(kr_scored_releases),
        "kr_policy_pressure_surprise_latest": (
            float(kr_latest_release["policy_pressure_surprise"])
            if kr_latest_release is not None
            else None
        ),
        "kr_policy_pressure_surprise_decay_ema": kr_surprise_ema,
        "kr_latest_surprise_indicator": (
            kr_latest_release.get("indicator_key") if kr_latest_release else None
        ),
        "kr_latest_surprise_actual": (
            kr_latest_release.get("actual") if kr_latest_release else None
        ),
        "kr_latest_surprise_consensus": (
            kr_latest_release.get("consensus") if kr_latest_release else None
        ),
        "kr_latest_surprise_available_at": (
            iso(kr_latest_release["available_at_dt"]) if kr_latest_release else None
        ),
        "us_priority_surprise_index": us_priority_surprise.get("score"),
        "us_priority_surprise_contributor_count": us_priority_surprise.get("contributor_count"),
        "us_priority_surprise_latest_indicator": us_priority_surprise.get("latest_indicator"),
        "kr_priority_surprise_index": kr_priority_surprise.get("score"),
        "kr_priority_surprise_contributor_count": kr_priority_surprise.get("contributor_count"),
        "kr_domestic_priority_surprise_index": kr_domestic_priority_surprise.get("score"),
        "kr_us_spillover_surprise_index": kr_us_spillover_surprise.get("score"),
        "kr_us_spillover_contributor_count": kr_us_spillover_surprise.get("contributor_count"),
        "target_market_impact_weight_semantics": us_priority_surprise.get("weight_semantics"),
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
        "reaction_anchor_kind": reaction_anchor_meta["kind"],
        "reaction_anchor_source": reaction_anchor_meta["source"],
        "reaction_anchor_event_name": reaction_anchor_meta["event_name"],
        "reaction_anchor_indicator": reaction_anchor_meta["indicator_key"],
        "reaction_anchor_available_at": reaction_anchor_meta["available_at"],
        "us2y_series": str(fred_cfg.get("series_id", "DGS2")),
        "us2y_latest_date": dgs2["latest_date"],
        "us2y_latest_pct": dgs2["latest_pct"],
        "us2y_previous_date": dgs2["previous_date"],
        "us2y_previous_pct": dgs2["previous_pct"],
        "us2y_change_bps_1d": dgs2["change_bps_1d"],
        "us2y_event_date_et": event_reaction["event_date_et"],
        "us2y_event_day_pct": event_reaction["event_day_pct"],
        "us2y_event_prior_day_pct": event_reaction["prior_day_pct"],
        "us2y_event_reaction_bps": event_reaction["reaction_bps"],
        "us2y_event_reaction_z": reaction_z,
        "us2y_reaction_quality": str(
            fred_cfg.get("reaction_quality", "DAILY_PROXY")
        ),
        "us2y_error": dgs2_error,
        "policy_proxy_series": str(
            fred_cfg.get("policy_proxy_series_id", "DFF")
        ),
        "policy_proxy_label": str(
            fred_cfg.get("policy_proxy_label", "DGS2_MINUS_DFF")
        ),
        "policy_proxy_latest_date": proxy_latest.get("latest_date"),
        "policy_proxy_spread_bps": proxy_latest.get("latest_spread_bps"),
        "policy_proxy_change_bps_1d": proxy_latest.get("change_bps_1d"),
        "policy_proxy_event_reaction_bps": proxy_event.get("reaction_bps"),
        "policy_proxy_quality": "MARKET_RATE_MINUS_EFFECTIVE_RATE_PROXY",
        "policy_proxy_error": policy_rate_error,
        "fed_policy_repricing_bps": (
            float(matched_policy["repricing_bps"]) if matched_policy else None
        ),
        "fed_policy_repricing_quality": (
            "FUTURES_PROVIDER_EVENT_MATCHED" if matched_policy else "UNAVAILABLE"
        ),
        "fed_policy_repricing_source": (
            matched_policy.get("source") if matched_policy else None
        ),
        "fed_policy_repricing_horizon": (
            matched_policy.get("horizon") if matched_policy else None
        ),
        "fed_policy_repricing_available_at": (
            iso(parse_dt(matched_policy.get("available_at")))
            if matched_policy and parse_dt(matched_policy.get("available_at"))
            else None
        ),
        "fed_policy_repricing_event_gap_minutes": policy_event_gap_minutes,
        "fed_policy_repricing_match_hours": policy_match_hours,
        "macro_event_family": event_family,
        "macro_event_shadow_score": shadow_score.get("score"),
        "macro_event_shadow_direction": shadow_score.get("direction"),
        "macro_event_shadow_components": {
            "bundle_surprise": shadow_score.get("bundle_surprise"),
            "bundle_indicators": shadow_score.get("bundle_indicators"),
            "bundle_component_scores": shadow_score.get("bundle_component_scores"),
            "us2y_reaction_z": shadow_score.get("us2y_reaction_z"),
            "policy_confirmation_z": shadow_score.get("policy_confirmation_z"),
            "policy_confirmation_source": shadow_score.get("policy_confirmation_source"),
        },
        "macro_event_shadow_score_range": shadow_score.get("score_range"),
        "macro_event_shadow_positive_direction": shadow_score.get("positive_direction"),
        "us_target_macro_event_score": us_target_event_score.get("score"),
        "us_target_macro_event_weight": us_target_event_score.get("impact_weight"),
        "kr_us_spillover_event_score": kr_us_spillover_event_score.get("score"),
        "kr_us_spillover_event_weight": kr_us_spillover_event_score.get("impact_weight"),
        "macro_event_free_reaction_score": free_reaction_score.get("score"),
        "macro_event_free_reaction_direction": free_reaction_score.get("direction"),
        "macro_event_free_reaction_ready": (
            bool(free_reaction_score.get("ready")) and reaction_anchor is not None
        ),
        "macro_event_free_reaction_quality": free_reaction_score.get("quality"),
        "macro_event_free_reaction_blockers": (
            (["NO_US_EVENT_ANCHOR"] if reaction_anchor is None else [])
            + list(free_reaction_score.get("blockers") or [])
        ),
        "macro_event_free_reaction_components": {
            "us2y_reaction_z": free_reaction_score.get("us2y_reaction_z"),
            "policy_proxy_confirmation_z": free_reaction_score.get(
                "policy_proxy_confirmation_z"
            ),
            "policy_confirmation_source": free_reaction_score.get(
                "policy_confirmation_source"
            ),
        },
        "macro_event_signal_ready": macro_event_signal_ready,
        "macro_event_signal_full_provider_ready": macro_event_signal_full_provider_ready,
        "macro_event_signal_quality": macro_event_signal_quality,
        "macro_event_signal_blockers": signal_blockers,
        "macro_shock_interaction": shock_interaction,
        "policy_alignment": policy_alignment,
        "component_status": {
            "official_news": {
                "status": "READY" if official_health == 1.0 else "PARTIAL",
                "healthy_sources": healthy_official,
                "configured_sources": len(official_sources),
            },
            "dgs2_daily_proxy": {
                "status": "READY" if dgs2_observations else "UNAVAILABLE",
                "quality": str(
                    fred_cfg.get("reaction_quality", "DAILY_PROXY")
                ),
            },
            "us2y_event_reaction": {
                "status": (
                    "READY"
                    if event_reaction.get("reaction_bps") is not None
                    else "PENDING_MARKET_OBSERVATION"
                    if reaction_anchor is not None
                    else "NO_US_EVENT_ANCHOR"
                ),
                "anchor_kind": reaction_anchor_meta["kind"],
                "anchor_source": reaction_anchor_meta["source"],
            },
            "consensus_surprise_provider": {
                "status": "READY" if surprise_provider_ready else "UNAVAILABLE"
            },
            "us_consensus_surprise_provider": {
                "status": "READY" if surprise_provider_ready else "UNAVAILABLE"
            },
            "kr_consensus_surprise_provider": {
                "status": "READY" if kr_latest_release is not None else "UNAVAILABLE",
                "quality": "SURPRISE_ONLY_NO_KR_MARKET_REACTION_CONFIRMATION",
                "shadow_only": True,
            },
            "target_market_impact": {
                "status": "READY",
                "weight_semantics": us_priority_surprise.get("weight_semantics"),
                "us_priority_surprise_index": us_priority_surprise.get("score"),
                "kr_priority_surprise_index": kr_priority_surprise.get("score"),
                "kr_domestic_priority_surprise_index": kr_domestic_priority_surprise.get("score"),
                "kr_us_spillover_surprise_index": kr_us_spillover_surprise.get("score"),
                "kr_us_spillover_event_score": kr_us_spillover_event_score.get("score"),
                "shadow_only": True,
            },
            "fed_repricing_provider": {
                "status": "READY" if fed_repricing_ready else "UNAVAILABLE",
                "event_gap_minutes": policy_event_gap_minutes,
                "match_window_hours": policy_match_hours,
            },
            "fed_repricing_proxy": {
                "status": (
                    "READY_EVENT_MATCHED"
                    if policy_proxy_event_ready
                    else "READY_LEVEL_ONLY"
                    if fed_proxy_ready
                    else "UNAVAILABLE"
                ),
                "quality": "MARKET_RATE_MINUS_EFFECTIVE_RATE_PROXY",
            },
            "macro_event_signal": {
                "status": "READY" if macro_event_signal_ready else "BLOCKED",
                "quality": macro_event_signal_quality,
                "event_family": event_family,
                "shadow_score": shadow_score.get("score"),
                "direction": shadow_score.get("direction"),
                "blockers": signal_blockers,
            },
            "macro_event_free_reaction": {
                "status": (
                    "READY"
                    if free_reaction_score.get("ready") and reaction_anchor is not None
                    else "BLOCKED"
                ),
                "quality": free_reaction_score.get("quality"),
                "event_family": event_family,
                "shadow_score": free_reaction_score.get("score"),
                "direction": free_reaction_score.get("direction"),
                "blockers": (
                    (["NO_US_EVENT_ANCHOR"] if reaction_anchor is None else [])
                    + list(free_reaction_score.get("blockers") or [])
                ),
                "free_only": True,
            },
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
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
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
    policy_rows = conn.execute(
        """
        SELECT observation_id,event_name,event_at,available_at,repricing_bps,
               horizon,source,source_item_id,time_quality,payload
        FROM public.macro_policy_repricing_observation
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
    return (
        list(macro_rows),
        list(release_rows),
        list(policy_rows),
        list(source_states),
    )


def build_snapshot(
    db_url: str,
    config: dict[str, Any],
    as_of: datetime | None = None,
) -> dict[str, Any]:
    as_of = (as_of or utc_now()).astimezone(UTC).replace(second=0, microsecond=0)
    lookback = int(config.get("lookback_hours", 72))
    dgs2, dgs2_error = fetch_dgs2(config, as_of)
    policy_rate, policy_rate_error = fetch_policy_proxy_rate(config, as_of)
    with psycopg.connect(db_url, connect_timeout=15, row_factory=dict_row) as conn:
        consensus_refresh = refresh_consensus_observations(conn, config, as_of)
        macro_rows, release_rows, policy_rows, states = fetch_inputs(
            conn, as_of, lookback, config
        )
        features, coverage = build_feature_payload(
            as_of=as_of,
            config=config,
            macro_rows=macro_rows,
            release_rows=release_rows,
            policy_rows=policy_rows,
            source_states=states,
            dgs2_observations=dgs2,
            dgs2_error=dgs2_error,
            policy_rate_observations=policy_rate,
            policy_rate_error=policy_rate_error,
        )
        features["consensus_provider_refresh"] = consensus_refresh
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


def import_policy_csv(db_url: str, path: Path) -> dict[str, int]:
    required = {
        "event_name",
        "event_at",
        "available_at",
        "repricing_bps",
        "source",
        "time_quality",
    }
    seen = inserted = 0
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing policy CSV columns: {sorted(missing)}")
        with psycopg.connect(db_url, connect_timeout=15) as conn:
            for raw in reader:
                seen += 1
                event_at = parse_dt(raw.get("event_at"))
                available_at = parse_dt(raw.get("available_at"))
                if event_at is None or available_at is None:
                    raise ValueError(f"row {seen}: invalid event_at/available_at")
                if available_at < event_at:
                    raise ValueError(f"row {seen}: available_at precedes event_at")
                material = "|".join(
                    str(raw.get(k) or "")
                    for k in (
                        "event_name",
                        "event_at",
                        "available_at",
                        "horizon",
                        "source",
                        "source_item_id",
                    )
                )
                obs_id = (raw.get("observation_id") or "").strip() or (
                    "policy-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:28]
                )
                payload_text = (raw.get("payload_json") or "").strip()
                payload = json.loads(payload_text) if payload_text else {}
                cur = conn.execute(
                    """
                    INSERT INTO public.macro_policy_repricing_observation(
                      observation_id,event_name,event_at,available_at,repricing_bps,
                      horizon,source,source_item_id,time_quality,payload,updated_at
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,now())
                    ON CONFLICT(observation_id) DO UPDATE SET
                      repricing_bps=excluded.repricing_bps,
                      payload=excluded.payload,
                      updated_at=now()
                    RETURNING (xmax = 0) AS inserted
                    """,
                    (
                        obs_id,
                        raw["event_name"].strip(),
                        event_at,
                        available_at,
                        float(raw["repricing_bps"]),
                        (raw.get("horizon") or "NEXT_FOMC").strip(),
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


def stack_status(
    db_url: str,
    config: dict[str, Any],
    as_of: datetime | None = None,
) -> dict[str, Any]:
    as_of = (as_of or utc_now()).astimezone(UTC)
    feature_version = str(config.get("feature_version", FEATURE_VERSION))
    provider = config.get("trading_economics") or {}
    with psycopg.connect(db_url, connect_timeout=15, row_factory=dict_row) as conn:
        counts = conn.execute(
            """
            SELECT
              (SELECT count(*) FROM public.macro_release_observation) AS releases,
              (SELECT count(*) FROM public.macro_policy_repricing_observation) AS policy_repricing,
              (SELECT count(*) FROM public.news_feature_snapshot
                 WHERE market='GLOBAL' AND symbol='GLOBAL'
                   AND feature_version=%s) AS snapshots
            """,
            (feature_version,),
        ).fetchone()
        latest_release = conn.execute(
            """
            SELECT indicator_key,event_name,market,release_at,available_at,
                   actual,consensus,previous,source,time_quality
            FROM public.macro_release_observation
            ORDER BY available_at DESC
            LIMIT 1
            """
        ).fetchone()
        latest_policy = conn.execute(
            """
            SELECT event_name,event_at,available_at,repricing_bps,
                   horizon,source,time_quality
            FROM public.macro_policy_repricing_observation
            ORDER BY available_at DESC
            LIMIT 1
            """
        ).fetchone()

    return {
        "as_of": iso(as_of),
        "feature_version": feature_version,
        "runtime": {
            "macro_features_enabled": env_bool("KALMAN_MACRO_FEATURES_ENABLED", False),
            "fred_key_configured": bool(
                (os.environ.get("FRED_API_KEY") or os.environ.get("FRED_KEY") or "").strip()
            ),
            "consensus_enabled": env_bool("KALMAN_MACRO_CONSENSUS_ENABLED", False),
            "trading_economics_key_configured": bool(
                (os.environ.get("TRADING_ECONOMICS_API_KEY") or "").strip()
            ),
            "consensus_active_window": within_active_window(as_of, provider),
        },
        "counts": dict(counts) if counts else {
            "releases": 0, "policy_repricing": 0, "snapshots": 0
        },
        "latest_release": dict(latest_release) if latest_release else None,
        "latest_policy_repricing": dict(latest_policy) if latest_policy else None,
        "latest_snapshot": latest_status(db_url, feature_version),
    }


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
    parser.add_argument(
        "command",
        choices=["build", "import-csv", "import-policy-csv", "status", "selftest"],
    )
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
    elif args.command == "import-policy-csv":
        if not args.input_csv:
            raise SystemExit("--input-csv is required")
        result = import_policy_csv(db_url, Path(args.input_csv))
        print("[MACRO][POLICY_IMPORT]", json.dumps(result, sort_keys=True))
    elif args.command == "status":
        as_of = parse_dt(args.as_of) if args.as_of else None
        row = stack_status(db_url, config, as_of)
        print("[MACRO][STATUS]", json.dumps(row, default=str, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
