#!/usr/bin/env python3
"""DSR/PSR, CSCV PBO and joint block-max Sharpe research-only diagnostics.

Input is a declared, synchronized CSV of strategy-only daily NET simple
returns (date plus strategy columns; no cash or market benchmarks). A pinned
SHA256 and expected strategy count are mandatory. The entire trial ledger
must be attested separately. No pricing, orders, or source writes.
"""
import argparse
import csv
import datetime as dt
import hashlib
import itertools
import json
import math
from pathlib import Path
from statistics import NormalDist

import numpy as np

SEED = 2601121
REPS = 10000
BLOCKS = (5, 20, 60)
PARTITIONS = (8, 10, 12)
TOL = 1e-12
SD_TOL = 1e-14
NORMAL = NormalDist()
ANNUAL = math.sqrt(252)
GAMMA = .5772156649015329


def require(ok, code):
    if not ok:
        raise ValueError(code)


def load(path, expected_hash, expected_count):
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    require(digest == expected_hash, "OVERFIT_SOURCE_SHA_MISMATCH")
    reader = csv.reader(raw.decode("utf-8").splitlines())
    header = next(reader, [])
    require(len(header) == expected_count+1 and header[0] == "date"
            and len(set(header)) == len(header), "OVERFIT_SCHEMA_MISMATCH")
    names = header[1:]
    require(all(x.strip() == x and x and x not in
                ("SPY", "QQQ", "CASH", "BENCHMARK_SPY", "BENCHMARK_QQQ")
                for x in names), "OVERFIT_STRATEGY_ONLY_INPUT_REQUIRED")
    dates, rows = [], []
    for row in reader:
        require(len(row) == len(header), "OVERFIT_ROW_WIDTH")
        day = dt.date.fromisoformat(row[0])
        require(str(day) == row[0] and day.weekday() < 5, "OVERFIT_DATE_INVALID")
        dates.append(day)
        rows.append([float(v) for v in row[1:]])
    values = np.asarray(rows, dtype=float)
    validate(names, dates, values)
    return names, dates, values, digest


def validate(names, dates, values):
    require(len(names) >= 2 and len(set(names)) == len(names), "OVERFIT_NAMES")
    require(len(dates) >= 252 and all(a < b for a, b in zip(dates, dates[1:])),
            "OVERFIT_DATE_ORDER")
    require(values.shape == (len(dates), len(names)) and
            np.isfinite(values).all() and (values > -1).all(),
            "OVERFIT_RETURNS_INVALID")


def deduplicate(names, values):
    keep, duplicates, constants = [], [], []
    for i, name in enumerate(names):
        v = values[:, i]
        if v.std(ddof=1) <= SD_TOL:
            require(np.max(np.abs(v)) <= TOL, "OVERFIT_NONZERO_CONSTANT_RETURN")
            constants.append(name)
            continue
        match = next((j for j in keep if
                      np.max(np.abs(v-values[:, j])) < TOL), None)
        if match is None:
            keep.append(i)
        else:
            duplicates.append(dict(strategy=name, equivalent_to=names[match]))
    require(len(keep) >= 2, "OVERFIT_INSUFFICIENT_DISTINCT_STRATEGIES")
    return [names[i] for i in keep], values[:, keep], duplicates, constants


def sharpe(x, axis=0):
    mean, sd = x.mean(axis=axis), x.std(axis=axis, ddof=1)
    return np.divide(mean, sd, out=np.zeros_like(mean), where=sd > SD_TOL)


def psr(sr, benchmark, n, skew, kurtosis):
    denominator = np.sqrt(1-skew*sr+(kurtosis-1)*sr*sr/4)
    require(np.isfinite(denominator).all() and (denominator > 0).all(),
            "OVERFIT_PSR_MOMENTS")
    z = (sr-benchmark)*math.sqrt(n-1)/denominator
    return np.asarray([NORMAL.cdf(float(v)) for v in z])


def moments(x):
    n = len(x)
    u = x-x.mean(axis=0)
    m2 = (u*u).mean(axis=0)
    require((m2 > 0).all(), "OVERFIT_MOMENTS_CONSTANT")
    g1 = (u**3).mean(axis=0)/m2**1.5
    g2 = (u**4).mean(axis=0)/m2**2-3
    # Bias-corrected Fisher-Pearson skew and non-excess Pearson kurtosis.
    return (math.sqrt(n*(n-1))/(n-2)*g1,
            (n-1)/((n-2)*(n-3))*((n+1)*g2+6)+3)


def dsr(names, x):
    sr = sharpe(x)
    skew, kurtosis = moments(x)
    corr = np.corrcoef(x, rowvar=False)
    effective = float(len(names)**2/np.sum(corr*corr))
    # Participation-ratio effective count is only an illustrative sensitivity,
    # not a certified estimate of the number of independent historical trials.
    cases = (("uncorrected_PSR", 1),
             ("all_distinct_assumed_independent", len(names)),
             ("correlation_sensitivity", max(2, min(len(names), round(effective)))))
    sd = float(sr.std(ddof=1))
    rows = []
    for case, n in cases:
        threshold = (0 if n == 1 else sd*((1-GAMMA)*NORMAL.inv_cdf(1-1/n)
                         + GAMMA*NORMAL.inv_cdf(1-1/(n*math.e))))
        probs = psr(sr, threshold, len(x), skew, kurtosis)
        for i, name in enumerate(names):
            rows.append(dict(strategy=name, assumption=case, trials=n,
                             annualized_sharpe=float(sr[i]*ANNUAL),
                             annualized_threshold=float(threshold*ANNUAL),
                             score=float(probs[i]), skew=float(skew[i]),
                             pearson_kurtosis=float(kurtosis[i])))
    return rows, effective


def cscv(names, x, partitions):
    require(partitions >= 4 and partitions % 2 == 0 and len(x) >= partitions*2,
            "OVERFIT_PARTITIONS")
    usable = len(x)//partitions*partitions
    # Equal contiguous blocks; exclude the earliest remainder, never invent data.
    a = x[-usable:]
    blocks = np.split(np.arange(usable), partitions)
    logs, train_sr, test_sr = [], [], []
    ties = 0
    selected = {name: 0 for name in names}
    for cs in itertools.combinations(range(partitions), partitions//2):
        train = np.concatenate([blocks[k] for k in cs])
        test = np.concatenate([blocks[k] for k in range(partitions) if k not in cs])
        si, so = sharpe(a[train]), sharpe(a[test])
        # Deterministic first declared name for an exact numerical tie.
        k = int(np.argmax(si))
        ties += int(np.sum(np.abs(si-si[k]) <= TOL) > 1)
        selected[names[k]] += 1
        rank = np.sum(so < so[k]-TOL)+.5*(np.sum(np.abs(so-so[k]) <= TOL)+1)
        relative = rank/(len(names)+1)
        logs.append(math.log(relative/(1-relative)))
        train_sr.append(float(si[k]*ANNUAL))
        test_sr.append(float(so[k]*ANNUAL))
    require(len(logs) == math.comb(partitions, partitions//2), "OVERFIT_CSCV_COUNT")
    return dict(partitions=partitions, splits=len(logs), usable_sessions=usable,
                dropped_earliest=len(x)-usable,
                pbo_median_or_below=float(np.mean(np.asarray(logs) <= TOL)),
                negative_selected_test_sharpe=float(np.mean(np.asarray(test_sr) < 0)),
                median_selected_train_sharpe=float(np.median(train_sr)),
                median_selected_test_sharpe=float(np.median(test_sr)),
                train_tie_splits=ties, selected_counts=selected)


def max_sharpe_null(names, x, block, n=REPS):
    """Zero-mean joint circular block bootstrap, preserving within-block dependence.

    This is a separate max-statistic sensitivity, not a DSR or future p-value.
    Constant sampled series are assigned zero score, not infinite Sharpe.
    """
    require(block >= 1 and n >= 200, "OVERFIT_BOOTSTRAP_SETTINGS")
    centered = x-x.mean(axis=0)
    observed = sharpe(x)*ANNUAL
    rng = np.random.default_rng(SEED+block*10007+2000003)
    maxima = []
    for start in range(0, n, 128):
        b = min(128, n-start)
        starts = rng.integers(0, len(x), size=(b, (len(x)+block-1)//block))
        ix = ((starts[:, :, None]+np.arange(block)) % len(x)).reshape(b, -1)[:, :len(x)]
        maxima.extend((sharpe(centered[ix], axis=1)*ANNUAL).max(axis=1))
    maxima = np.asarray(maxima)
    require(np.isfinite(maxima).all(), "OVERFIT_NULL_INVALID")
    return dict(block=block, repetitions=n, max_sharpe_p95=float(np.quantile(maxima, .95)),
                best_observed=float(observed.max()),
                adjusted_tail_probability_by_strategy={
                    name: float((1+np.sum(maxima >= observed[i]))/(n+1))
                    for i, name in enumerate(names)})


def analyze(names, dates, values, *, repetitions=REPS):
    validate(names, dates, values)
    original_count = len(names)
    names, x, duplicates, constants = deduplicate(names, values)
    scores, effective = dsr(names, x)
    return dict(version="daily20-challenger-overfit-validation-v1",
                status="RETROSPECTIVE_RESEARCH_HOLD", research_only=True,
                approved_live=False, model_selection_allowed=False,
                forward_validated=False, source_finality_certified=False,
                sessions=len(dates), first_session=str(dates[0]), last_session=str(dates[-1]),
                input_strategy_count=original_count, unique_strategy_count=len(names),
                duplicate_tolerance=TOL, duplicate_paths=duplicates, zero_return_paths=constants,
                correlation_effective_count_sensitivity=effective, dsr=scores,
                pbo=[cscv(names, x, p) for p in PARTITIONS],
                block_max_sharpe=[max_sharpe_null(names, x, b, repetitions) for b in BLOCKS],
                seed=SEED, limitations=[
                    "Declared trial matrix may omit previous adaptive searches.",
                    "Daily zero-cash-rate Sharpe; analytic DSR assumes independent trials and iid observations.",
                    "Correlation participation ratio is sensitivity, not an established independent trial count.",
                    "CSCV selects among frozen realized paths; it does not refit, purge trades at boundaries, or create chronological holdout.",
                    "PBO counts median ties as failure; no-variance subsample Sharpe is zero; first declared name wins a training tie.",
                    "Block-max null is historical, not independent forward evidence.",
                    "Hash integrity does not certify source, execution or exchange-calendar completeness."])


def self_test():
    dates = []
    day = dt.date(2024, 1, 2)
    while len(dates) < 300:
        if day.weekday() < 5:
            dates.append(day)
        day += dt.timedelta(days=1)
    rng = np.random.default_rng(42)
    x = rng.normal(.0002, .006, (len(dates), 4))
    x = np.column_stack([x, x[:, 0], np.zeros(len(dates))])
    names = ["a", "b", "c", "d", "a_duplicate", "cash_like"]
    a = analyze(names, dates, x, repetitions=256)
    b = analyze(names, dates, x, repetitions=256)
    require(a == b, "OVERFIT_DETERMINISM")
    require(a["unique_strategy_count"] == 4 and len(a["duplicate_paths"]) == 1
            and a["zero_return_paths"] == ["cash_like"], "OVERFIT_DEDUP_TEST")
    require([r["splits"] for r in a["pbo"]] == [70, 252, 924], "OVERFIT_SPLITS_TEST")
    require(all(0 <= r["pbo_median_or_below"] <= 1 for r in a["pbo"]), "OVERFIT_PBO_RANGE")
    require(all(0 <= r["score"] <= 1 for r in a["dsr"]), "OVERFIT_DSR_RANGE")
    require(all(0 <= p <= 1 for r in a["block_max_sharpe"]
                for p in r["adjusted_tail_probability_by_strategy"].values()),
            "OVERFIT_NULL_RANGE")
    require(abs(psr(np.array([0.]), 0, 300, np.array([0.]), np.array([3.]))[0]-.5)
            < 1e-12, "OVERFIT_PSR_REFERENCE")
    print("CHALLENGER_OVERFIT_VALIDATION_SYNTHETIC_SELF_TEST_PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--input")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--strategy-count", type=int)
    parser.add_argument("--source-id")
    parser.add_argument("--out")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    require(all([args.input, args.expected_sha256, args.strategy_count,
                 args.source_id, args.out]), "OVERFIT_ARGUMENTS")
    names, dates, values, digest = load(args.input, args.expected_sha256,
                                        args.strategy_count)
    result = analyze(names, dates, values)
    result.update(source_id=args.source_id, source_sha256=digest)
    out = Path(args.out)
    require(not out.exists(), "OVERFIT_OUTPUT_MUST_BE_NEW")
    out.mkdir(parents=True)
    (out/"overfit_report.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps({k: result[k] for k in ("status", "sessions",
                         "input_strategy_count", "unique_strategy_count", "source_sha256")}))


if __name__ == "__main__":
    main()
