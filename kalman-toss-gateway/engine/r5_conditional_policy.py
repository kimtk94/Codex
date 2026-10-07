from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConditionalDecision:
    regime: str
    rank1_symbol: str
    rank1_score: float | None
    rank2_symbol: str | None
    rank2_score: float | None
    relative_gap: float | None
    legs_krw: tuple[tuple[str, int], ...]
    cash_krw: int
    reason: str


def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def score_from_payload(payload: dict[str, Any] | None) -> float | None:
    payload = payload or {}
    for key in ("rank1_score", "top1_score", "selected_score", "score", "prediction", "pred"):
        value = _f(payload.get(key))
        if value is not None:
            return value
    return None


def rank2_from_payload(payload: dict[str, Any] | None) -> tuple[str | None, float | None]:
    payload = payload or {}
    direct_pairs = (
        ("rank2_symbol", "rank2_score"),
        ("top2_symbol", "top2_score"),
        ("second_symbol", "second_score"),
    )
    for sk, vk in direct_pairs:
        symbol = str(payload.get(sk) or "").strip().upper()
        score = _f(payload.get(vk))
        if symbol and score is not None:
            return symbol, score

    for key in ("ranking", "rankings", "candidates", "topk", "top_candidates"):
        rows = payload.get(key)
        if not isinstance(rows, list):
            continue
        parsed = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            symbol = str(
                item.get("symbol") or item.get("ticker") or item.get("selected_symbol") or ""
            ).strip().upper()
            score = None
            for score_key in ("score", "prediction", "pred", "alpha_score", "signal_score"):
                score = _f(item.get(score_key))
                if score is not None:
                    break
            if symbol and score is not None:
                parsed.append((symbol, score))
        if len(parsed) >= 2:
            parsed.sort(key=lambda x: x[1], reverse=True)
            return parsed[1]
    return None, None


def decide(
    *,
    rank1_symbol: str,
    rank1_score: float | None,
    rank2_symbol: str | None,
    rank2_score: float | None,
    gap_threshold: float,
    confidence_threshold: float,
    total_krw: int = 20000,
    base_leg_krw: int | None = None,
) -> ConditionalDecision:
    rank1_symbol = rank1_symbol.upper()
    base_leg = total_krw // 2 if base_leg_krw is None else int(base_leg_krw)
    if total_krw <= 0 or base_leg <= 0 or base_leg * 2 > total_krw:
        raise ValueError("invalid conditional allocation budget")

    if rank1_score is None:
        return ConditionalDecision(
            "TOP1_ONLY_NO_SCORE", rank1_symbol, None, rank2_symbol, rank2_score,
            None, ((rank1_symbol, total_krw),), 0,
            "rank1 score unavailable; deterministic Top1 fallback",
        )

    if rank1_score <= confidence_threshold:
        return ConditionalDecision(
            "LOW_CONFIDENCE", rank1_symbol, rank1_score, rank2_symbol, rank2_score,
            None, ((rank1_symbol, base_leg),), total_krw - base_leg,
            "rank1 score at/below frozen confidence threshold",
        )

    if (
        rank2_symbol
        and rank2_score is not None
        and rank1_score != 0
        and rank2_symbol.upper() != rank1_symbol
    ):
        gap = (rank1_score - rank2_score) / abs(rank1_score)
        if gap <= gap_threshold:
            return ConditionalDecision(
                "CLOSE_GAP", rank1_symbol, rank1_score, rank2_symbol.upper(), rank2_score,
                gap, ((rank1_symbol, half), (rank2_symbol.upper(), total_krw - half)), 0,
                "relative score gap at/below frozen gap threshold",
            )
        return ConditionalDecision(
            "TOP1_ONLY_WIDE_GAP", rank1_symbol, rank1_score, rank2_symbol.upper(), rank2_score,
            gap, ((rank1_symbol, total_krw),), 0,
            "rank1-rank2 gap above frozen threshold",
        )

    return ConditionalDecision(
        "TOP1_ONLY_NO_RANK2", rank1_symbol, rank1_score, None, None,
        None, ((rank1_symbol, total_krw),), 0,
        "rank2 unavailable; deterministic Top1 fallback",
    )
