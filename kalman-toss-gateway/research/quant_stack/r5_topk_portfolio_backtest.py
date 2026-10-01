from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


NY = ZoneInfo("America/New_York")
SCHEMA_VERSION = "kalman-r5-topk-portfolio-v1"
PORTFOLIOS = (
    "TOP1",
    "TOP2_EQUAL",
    "TOP3_EQUAL",
    "TOP3_50_30_20",
    "TOP3_SCORE_PROP",
    "TOP4_EQUAL",
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _read_table(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".csv", ".gz"} or path.name.lower().endswith(".csv.gz"):
        return pd.read_csv(path)
    if suffix in {".tsv", ".txt"} or path.name.lower().endswith(".tsv.gz"):
        return pd.read_csv(path, sep="\t")
    raise ValueError(f"unsupported table format: {path}")


def _pick_col(
    frame: pd.DataFrame,
    names: tuple[str, ...],
    *,
    required: bool = True,
) -> str | None:
    lower = {str(c).lower(): str(c) for c in frame.columns}
    for name in names:
        if name.lower() in lower:
            return lower[name.lower()]
    if required:
        raise ValueError(
            f"missing required column; expected one of={names}, "
            f"available={list(frame.columns)}"
        )
    return None


def normalize_rankings(
    frame: pd.DataFrame,
    *,
    score_column: str | None = None,
) -> pd.DataFrame:
    seq_col = _pick_col(frame, ("expected_seq", "seq", "bar_seq", "signal_seq"))
    symbol_col = _pick_col(frame, ("symbol", "selected_symbol", "ticker", "asset"))
    if score_column is not None:
        if score_column not in frame.columns:
            raise ValueError(
                f"score column not found: {score_column}; "
                f"available={list(frame.columns)}"
            )
        score_col = score_column
    else:
        score_col = _pick_col(
            frame,
            ("score", "prediction", "pred", "alpha_score", "signal_score"),
        )
    ts_col = _pick_col(
        frame,
        ("timestamp", "signal_as_of", "ts", "as_of"),
        required=False,
    )

    z = frame[
        [seq_col, symbol_col, score_col] + ([ts_col] if ts_col else [])
    ].copy()
    z = z.rename(
        columns={
            seq_col: "expected_seq",
            symbol_col: "symbol",
            score_col: "score",
        }
    )
    if ts_col:
        z = z.rename(columns={ts_col: "timestamp"})
        z["timestamp"] = pd.to_datetime(z["timestamp"], utc=True, errors="coerce")
    else:
        z["timestamp"] = pd.NaT

    z["expected_seq"] = pd.to_numeric(z["expected_seq"], errors="coerce")
    z["score"] = pd.to_numeric(z["score"], errors="coerce")
    z["symbol"] = (
        z["symbol"]
        .astype(str)
        .str.upper()
        .str.replace(".", "-", regex=False)
        .str.strip()
    )
    z = z.dropna(subset=["expected_seq", "score"]).loc[
        lambda x: x["symbol"].ne("")
    ]
    z["expected_seq"] = z["expected_seq"].astype("int64")
    z = z.sort_values(
        ["expected_seq", "score", "symbol"],
        ascending=[True, False, True],
    )
    z = z.drop_duplicates(["expected_seq", "symbol"], keep="first")
    z["rank"] = z.groupby("expected_seq").cumcount() + 1
    return z.reset_index(drop=True)


def normalize_admissions(
    frame: pd.DataFrame,
    *,
    candidate: str | None = None,
) -> pd.DataFrame:
    if candidate is not None:
        candidate_col = _pick_col(
            frame,
            ("candidate", "candidate_id", "model", "strategy"),
        )
        frame = frame.loc[
            frame[candidate_col].astype(str).eq(candidate)
        ].copy()
        if frame.empty:
            raise ValueError(
                f"no admission rows for candidate={candidate}"
            )

    seq_col = _pick_col(frame, ("expected_seq", "seq", "bar_seq", "signal_seq"))
    ts_col = _pick_col(
        frame,
        ("timestamp", "signal_as_of", "ts", "as_of"),
        required=False,
    )
    z = frame[[seq_col] + ([ts_col] if ts_col else [])].copy()
    z = z.rename(columns={seq_col: "expected_seq"})
    z["expected_seq"] = pd.to_numeric(z["expected_seq"], errors="coerce")
    z = z.dropna(subset=["expected_seq"])
    z["expected_seq"] = z["expected_seq"].astype("int64")
    if ts_col:
        z = z.rename(columns={ts_col: "timestamp"})
        z["timestamp"] = pd.to_datetime(z["timestamp"], utc=True, errors="coerce")
    else:
        z["timestamp"] = pd.NaT
    return (
        z.sort_values("expected_seq")
        .drop_duplicates("expected_seq", keep="first")
        .reset_index(drop=True)
    )


def _read_prices(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    seq_col = _pick_col(frame, ("expected_seq", "seq", "bar_seq"))
    close_col = _pick_col(frame, ("close", "adj_close"))
    ts_col = _pick_col(frame, ("timestamp", "ts"), required=False)

    z = frame[
        [seq_col, close_col] + ([ts_col] if ts_col else [])
    ].copy()
    z = z.rename(columns={seq_col: "expected_seq", close_col: "close"})

    if ts_col:
        z = z.rename(columns={ts_col: "timestamp"})
        z["timestamp"] = pd.to_datetime(z["timestamp"], utc=True, errors="coerce")
    elif {"market_open_utc", "session_bucket"}.issubset(frame.columns):
        z["timestamp"] = (
            pd.to_datetime(frame["market_open_utc"], utc=True, errors="coerce")
            + pd.to_timedelta(
                pd.to_numeric(frame["session_bucket"], errors="coerce"),
                unit="h",
            )
        )
    else:
        raise ValueError(f"{path}: timestamp unavailable")

    z["expected_seq"] = pd.to_numeric(z["expected_seq"], errors="coerce")
    z["close"] = pd.to_numeric(z["close"], errors="coerce")
    z = z.dropna(subset=["expected_seq", "timestamp", "close"]).loc[
        lambda x: x["close"] > 0
    ]
    z["expected_seq"] = z["expected_seq"].astype("int64")
    return (
        z.sort_values(["expected_seq", "timestamp"])
        .drop_duplicates("expected_seq", keep="last")
        .reset_index(drop=True)
    )


class PriceLookup:
    def __init__(self, locked_panel: Path, live_panel: Path | None = None):
        self.locked_panel = locked_panel
        self.live_panel = live_panel
        self._cache: dict[str, pd.DataFrame] = {}

    def frame(self, symbol: str) -> pd.DataFrame:
        symbol = symbol.upper().replace(".", "-")
        if symbol in self._cache:
            return self._cache[symbol]

        rows: list[pd.DataFrame] = []

        locked = self.locked_panel / f"{symbol}_1h_gap_aware.parquet"
        if locked.is_file():
            rows.append(_read_prices(locked))

        if self.live_panel:
            live = self.live_panel / f"{symbol}_1h_live.parquet"
            if live.is_file():
                rows.append(_read_prices(live))

        if not rows:
            out = pd.DataFrame(columns=["expected_seq", "timestamp", "close"])
        else:
            out = (
                pd.concat(rows, ignore_index=True)
                .sort_values(["expected_seq", "timestamp"])
                .drop_duplicates("expected_seq", keep="last")
                .reset_index(drop=True)
            )

        self._cache[symbol] = out
        return out

    def at(
        self,
        symbol: str,
        seq: int,
    ) -> tuple[pd.Timestamp | None, float | None]:
        frame = self.frame(symbol)
        z = frame.loc[frame["expected_seq"].eq(int(seq))]
        if z.empty:
            return None, None
        row = z.iloc[-1]
        return pd.Timestamp(row["timestamp"]), float(row["close"])

    def friday_flat_exit_seq(
        self,
        symbol: str,
        entry_seq: int,
        fixed_exit_seq: int,
    ) -> int:
        frame = self.frame(symbol)
        z = frame.loc[
            frame["expected_seq"].between(
                int(entry_seq),
                int(fixed_exit_seq),
                inclusive="both",
            )
        ].copy()
        if z.empty:
            return int(fixed_exit_seq)

        z["date_et"] = z["timestamp"].dt.tz_convert(NY).dt.date
        z["weekday_et"] = z["timestamp"].dt.tz_convert(NY).dt.weekday

        fixed = z.loc[z["expected_seq"].eq(int(fixed_exit_seq))]
        if fixed.empty:
            return int(fixed_exit_seq)

        fixed_date = fixed.iloc[-1]["date_et"]
        friday = z.loc[
            (z["weekday_et"] == 4)
            & (z["date_et"] < fixed_date)
        ]
        if friday.empty:
            return int(fixed_exit_seq)

        last_friday_date = friday["date_et"].max()
        return int(
            friday.loc[
                friday["date_et"].eq(last_friday_date),
                "expected_seq",
            ].max()
        )


def portfolio_weights(name: str, scores: np.ndarray) -> np.ndarray:
    scores = np.asarray(scores, dtype=float)
    if len(scores) < 4:
        raise ValueError("scores must contain top 4")

    weights = np.zeros(4, dtype=float)

    if name == "TOP1":
        weights[0] = 1.0

    elif name == "TOP2_EQUAL":
        weights[:2] = 0.5

    elif name == "TOP3_EQUAL":
        weights[:3] = 1.0 / 3.0

    elif name == "TOP3_50_30_20":
        weights[:3] = np.asarray([0.5, 0.3, 0.2], dtype=float)

    elif name == "TOP3_SCORE_PROP":
        positive = np.maximum(scores[:3], 0.0)
        if float(positive.sum()) <= 0:
            weights[:3] = 1.0 / 3.0
        else:
            weights[:3] = positive / positive.sum()

    elif name == "TOP4_EQUAL":
        weights[:] = 0.25

    else:
        raise ValueError(name)

    return weights


def _max_drawdown(returns: pd.Series) -> float:
    wealth = (1.0 + returns.fillna(0.0)).cumprod()
    if wealth.empty:
        return float("nan")
    drawdown = wealth / wealth.cummax() - 1.0
    return float(drawdown.min())


def strategy_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {}

    returns = pd.to_numeric(frame["net_return"], errors="coerce").dropna()
    if returns.empty:
        return {}

    total_return = float((1.0 + returns).prod() - 1.0)
    max_drawdown = _max_drawdown(returns)

    start = pd.Timestamp(frame["entry_timestamp"].min())
    end = pd.Timestamp(frame["exit_timestamp"].max())
    years = max(
        (end - start).total_seconds() / (365.25 * 86400.0),
        1.0 / 365.25,
    )
    cagr = (
        float((1.0 + total_return) ** (1.0 / years) - 1.0)
        if total_return > -1.0
        else -1.0
    )

    trades_per_year = len(returns) / years
    sd = float(returns.std(ddof=0))
    sharpe = (
        float(returns.mean() / sd * math.sqrt(trades_per_year))
        if sd > 0 and trades_per_year > 0
        else None
    )

    downside = returns.loc[returns < 0]
    downside_sd = (
        float(np.sqrt(np.mean(np.square(downside))))
        if len(downside)
        else 0.0
    )
    sortino = (
        float(returns.mean() / downside_sd * math.sqrt(trades_per_year))
        if downside_sd > 0
        else None
    )

    return {
        "trades": int(len(returns)),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total_return": total_return,
        "cagr": cagr,
        "max_drawdown": max_drawdown,
        "cagr_over_abs_mdd": (
            cagr / abs(max_drawdown)
            if max_drawdown < 0
            else None
        ),
        "trade_sharpe_annualized": sharpe,
        "trade_sortino_annualized": sortino,
        "win_rate": float((returns > 0).mean()),
        "mean_net_return": float(returns.mean()),
        "median_net_return": float(returns.median()),
        "best_trade": float(returns.max()),
        "worst_trade": float(returns.min()),
    }


def build_common_trade_panel(
    rankings: pd.DataFrame,
    admissions: pd.DataFrame,
    prices: PriceLookup,
    *,
    start: str | None = None,
    end: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    admitted = set(int(x) for x in admissions["expected_seq"].tolist())
    ranks = rankings.loc[
        rankings["expected_seq"].isin(admitted)
        & rankings["rank"].le(4)
    ].copy()

    admission_ts = (
        admissions.set_index("expected_seq")["timestamp"].to_dict()
    )

    rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    start_ts = pd.Timestamp(start, tz="UTC") if start else None
    end_ts = pd.Timestamp(end, tz="UTC") if end else None

    for seq in sorted(admitted):
        group = ranks.loc[
            ranks["expected_seq"].eq(seq)
        ].sort_values("rank")

        if len(group) < 4:
            rejected.append(
                {
                    "expected_seq": seq,
                    "reason": "LT4_RANKED_CANDIDATES",
                    "available": int(len(group)),
                }
            )
            continue

        selected = group.head(4)
        symbols = selected["symbol"].tolist()
        scores = selected["score"].astype(float).to_numpy()

        entry_records: list[tuple[pd.Timestamp, float]] = []
        missing = False

        for symbol in symbols:
            ts, price = prices.at(symbol, seq)
            if ts is None or price is None:
                rejected.append(
                    {
                        "expected_seq": seq,
                        "reason": "ENTRY_PRICE_MISSING",
                        "symbol": symbol,
                    }
                )
                missing = True
                break
            entry_records.append((ts, price))

        if missing:
            continue

        entry_ts = entry_records[0][0]

        if start_ts is not None and entry_ts < start_ts:
            continue
        if end_ts is not None and entry_ts > end_ts:
            continue

        fixed_exit_seq = seq + 4
        actual_exit_seq = prices.friday_flat_exit_seq(
            symbols[0],
            seq,
            fixed_exit_seq,
        )

        exit_records: list[tuple[pd.Timestamp, float]] = []

        for symbol in symbols:
            ts, price = prices.at(symbol, actual_exit_seq)
            if ts is None or price is None:
                rejected.append(
                    {
                        "expected_seq": seq,
                        "reason": "EXIT_PRICE_MISSING",
                        "symbol": symbol,
                        "exit_seq": actual_exit_seq,
                    }
                )
                missing = True
                break
            exit_records.append((ts, price))

        if missing:
            continue

        raw_returns = np.asarray(
            [
                exit_records[i][1] / entry_records[i][1] - 1.0
                for i in range(4)
            ],
            dtype=float,
        )

        row: dict[str, Any] = {
            "expected_seq": seq,
            "fixed_exit_seq": fixed_exit_seq,
            "actual_exit_seq": actual_exit_seq,
            "friday_flat_applied": bool(
                actual_exit_seq != fixed_exit_seq
            ),
            "entry_timestamp": entry_ts,
            "exit_timestamp": exit_records[0][0],
            "admission_timestamp": admission_ts.get(seq),
        }

        for i in range(4):
            row[f"rank{i + 1}_symbol"] = symbols[i]
            row[f"rank{i + 1}_score"] = float(scores[i])
            row[f"rank{i + 1}_raw_return"] = float(raw_returns[i])

        rows.append(row)

    return pd.DataFrame(rows), pd.DataFrame(rejected)


def evaluate_portfolios(
    panel: pd.DataFrame,
    *,
    cost_bps: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if panel.empty:
        raise RuntimeError("common top4 trade panel is empty")

    cost = float(cost_bps) / 10_000.0
    detail: list[dict[str, Any]] = []

    for row in panel.itertuples(index=False):
        scores = np.asarray(
            [
                getattr(row, f"rank{i}_score")
                for i in range(1, 5)
            ],
            dtype=float,
        )
        raw_returns = np.asarray(
            [
                getattr(row, f"rank{i}_raw_return")
                for i in range(1, 5)
            ],
            dtype=float,
        )

        for name in PORTFOLIOS:
            weights = portfolio_weights(name, scores)
            gross_return = float(weights @ raw_returns)
            net_return = gross_return - cost

            record = {
                "portfolio": name,
                "expected_seq": int(row.expected_seq),
                "entry_timestamp": row.entry_timestamp,
                "exit_timestamp": row.exit_timestamp,
                "actual_exit_seq": int(row.actual_exit_seq),
                "friday_flat_applied": bool(
                    row.friday_flat_applied
                ),
                "gross_return": gross_return,
                "net_return": net_return,
                "cost_bps": float(cost_bps),
            }

            for i in range(4):
                record[f"rank{i + 1}_weight"] = float(weights[i])
                record[f"rank{i + 1}_symbol"] = getattr(
                    row,
                    f"rank{i + 1}_symbol",
                )
                record[f"rank{i + 1}_score"] = float(scores[i])
                record[f"rank{i + 1}_raw_return"] = float(
                    raw_returns[i]
                )

            detail.append(record)

    detail_df = pd.DataFrame(detail)

    summaries: list[dict[str, Any]] = []
    for name in PORTFOLIOS:
        metrics = strategy_metrics(
            detail_df.loc[
                detail_df["portfolio"].eq(name)
            ].copy()
        )
        summaries.append({"portfolio": name, **metrics})

    return detail_df, pd.DataFrame(summaries)


def rank_diagnostics(
    panel: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    stats: list[dict[str, Any]] = []
    series: dict[str, pd.Series] = {}

    for rank in range(1, 5):
        returns = pd.to_numeric(
            panel[f"rank{rank}_raw_return"],
            errors="coerce",
        )
        series[f"R{rank}"] = returns

        stats.append(
            {
                "rank": rank,
                "observations": int(returns.notna().sum()),
                "mean_raw_return": float(returns.mean()),
                "median_raw_return": float(returns.median()),
                "win_rate": float((returns > 0).mean()),
                "mean_excess_vs_rank1": (
                    0.0
                    if rank == 1
                    else float(
                        (returns - series["R1"]).mean()
                    )
                ),
                "simultaneous_loss_with_rank1": (
                    None
                    if rank == 1
                    else float(
                        (
                            (returns < 0)
                            & (series["R1"] < 0)
                        ).mean()
                    )
                ),
            }
        )

    corr = pd.DataFrame(series).corr()
    corr.index.name = "rank"
    return pd.DataFrame(stats), corr.reset_index()


def discover_ranking_files(
    root: Path,
) -> dict[str, list[dict[str, Any]]]:
    matches: list[dict[str, Any]] = []
    inspected: list[dict[str, Any]] = []

    seq_names = {
        "expected_seq",
        "seq",
        "bar_seq",
        "signal_seq",
    }
    symbol_names = {
        "symbol",
        "selected_symbol",
        "ticker",
        "asset",
    }
    score_names = {
        "score",
        "prediction",
        "pred",
        "alpha_score",
        "signal_score",
    }

    for path in root.rglob("*.parquet"):
        try:
            frame = pd.read_parquet(path)
            cols = [str(c) for c in frame.columns]
            lower = {c.lower() for c in cols}

            seq_ok = bool(lower & seq_names)
            symbol_ok = bool(lower & symbol_names)
            score_ok = bool(lower & score_names)

            name_lower = path.name.lower()
            r5_like = (
                "r5" in str(path).lower()
                or "signal" in name_lower
                or "score" in name_lower
                or "candidate" in name_lower
                or "rank" in name_lower
            )

            if seq_ok and symbol_ok and score_ok:
                matches.append(
                    {
                        "path": str(path),
                        "rows": int(len(frame)),
                        "columns": cols,
                        "contract": {
                            "seq": True,
                            "symbol": True,
                            "score": True,
                        },
                    }
                )
                continue

            if r5_like or sum((seq_ok, symbol_ok, score_ok)) >= 2:
                inspected.append(
                    {
                        "path": str(path),
                        "rows": int(len(frame)),
                        "columns": cols,
                        "contract": {
                            "seq": seq_ok,
                            "symbol": symbol_ok,
                            "score": score_ok,
                        },
                    }
                )

        except Exception as exc:
            inspected.append(
                {
                    "path": str(path),
                    "read_error": f"{type(exc).__name__}: {exc}",
                }
            )

    matches.sort(key=lambda x: x["path"])
    inspected.sort(key=lambda x: x["path"])

    return {
        "matches": matches,
        "inspected": inspected[:200],
    }

def _default_root() -> Path:
    return Path(
        os.environ.get("KALMAN_US_ETF_ROOT")
        or "/mnt/gdrive/US_ETF"
    )


def parse_args() -> argparse.Namespace:
    root = _default_root()

    parser = argparse.ArgumentParser(
        description=(
            "R5.1 FIXED_4 + Friday-flat Top-K "
            "portfolio backtest"
        )
    )
    parser.add_argument(
        "--rankings",
        type=Path,
        default=(
            root
            / "model_lab_v1/results/"
            "r5_0_1_research_sandbox_all_data/"
            "r5_0_1_scored_rows.parquet"
        ),
    )
    parser.add_argument(
        "--ranking-score-column",
        default="R5C0_HGB_REFERENCE",
    )
    parser.add_argument(
        "--admission-log",
        type=Path,
        default=(
            root
            / "model_lab_v1/results/"
            "r5_0_1_research_sandbox_all_data/"
            "r5_0_1_trade_ledger.parquet"
        ),
    )
    parser.add_argument(
        "--admission-candidate",
        default="R5C0_HGB_REFERENCE",
    )
    parser.add_argument(
        "--locked-panel",
        type=Path,
        default=(
            root
            / "directional_research/"
            "canonical_history_v1/"
            "panel_1h_gap_aware"
        ),
    )
    parser.add_argument(
        "--live-panel",
        type=Path,
        default=(
            root
            / "directional_research/"
            "r4_live_canonical_v1/"
            "panel_1h_overlay"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=(
            root
            / "model_lab_v1/results/"
            "r5_1_topk_portfolio_v1"
        ),
    )
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument(
        "--discover-root",
        type=Path,
        default=root / "model_lab_v1/results",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.discover_only:
        discovery = discover_ranking_files(args.discover_root)
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "discover_root": str(args.discover_root),
                    **discovery,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if discovery["matches"] else 2

    rankings = normalize_rankings(
        _read_table(args.rankings),
        score_column=args.ranking_score_column,
    )
    admissions = normalize_admissions(
        _read_table(args.admission_log),
        candidate=args.admission_candidate,
    )

    prices = PriceLookup(
        args.locked_panel,
        (
            args.live_panel
            if args.live_panel.is_dir()
            else None
        ),
    )

    panel, rejected = build_common_trade_panel(
        rankings,
        admissions,
        prices,
        start=args.start,
        end=args.end,
    )

    detail, summary = evaluate_portfolios(
        panel,
        cost_bps=args.cost_bps,
    )
    rank_stats, rank_corr = rank_diagnostics(panel)

    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    panel.to_parquet(
        args.output_dir
        / "r5_topk_common_trade_panel.parquet",
        index=False,
    )
    detail.to_parquet(
        args.output_dir
        / "r5_topk_portfolio_trade_detail.parquet",
        index=False,
    )
    summary.to_csv(
        args.output_dir
        / "r5_topk_portfolio_summary.csv",
        index=False,
    )
    rank_stats.to_csv(
        args.output_dir
        / "r5_topk_rank_diagnostics.csv",
        index=False,
    )
    rank_corr.to_csv(
        args.output_dir
        / "r5_topk_rank_return_correlation.csv",
        index=False,
    )
    rejected.to_csv(
        args.output_dir
        / "r5_topk_rejected_admissions.csv",
        index=False,
    )

    status = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "rankings": str(args.rankings),
        "ranking_score_column": args.ranking_score_column,
        "admission_log": str(args.admission_log),
        "admission_candidate": args.admission_candidate,
        "locked_panel": str(args.locked_panel),
        "live_panel": str(args.live_panel),
        "cost_bps": float(args.cost_bps),
        "common_admissions": int(len(panel)),
        "rejected_admissions": int(len(rejected)),
        "friday_flat_count": (
            int(panel["friday_flat_applied"].sum())
            if len(panel)
            else 0
        ),
        "portfolios": PORTFOLIOS,
        "summary": summary.to_dict(orient="records"),
    }

    _write_json(
        args.output_dir / "status.json",
        status,
    )

    print(
        json.dumps(
            status,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
