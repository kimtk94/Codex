#!/usr/bin/env python3
"""Isolated challenger risk/significance audit. No live or data-source writes.

Input: immutable wide CSV of synchronized NET daily simple returns (not annual
summaries), with exact declared columns and an externally supplied SHA256.
Source owner must separately attest XNYS calendar, ledger and PIT provenance.
Results are descriptive retrospective evidence, never promotion signals.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import tempfile

import numpy as np

SEED = 2601121
REPS = 10000
FAMILIES = ("K1", "K2", "K3", "K1+K2", "K1+K3", "K1+K2+K3",
            "old_p60", "barrier_EVpos", "barrier_rank", "old_rank")
COHORTS = ("20", "16")
COSTS = (30, 50)
COLUMNS = ("SPY", "QQQ") + tuple(
    f"{c}_{b}_{f}" for c in COHORTS for b in COSTS for f in FAMILIES
) + ("BEAR_LOGISTIC_ONLY__ALL_20__POS5__COST20BP",
     "BULL_BASELINE__ALL_20__POS5__COST20BP")
PAIRS = tuple((f"{c}_{b}_{x}", "CASH" if y == "CASH" else f"{c}_{b}_{y}")
              for c in COHORTS for b in COSTS for x, y in (
                  ("K1+K3", "K1"), ("K1+K2+K3", "K1+K3"),
                  ("barrier_EVpos", "old_p60"), ("barrier_rank", "old_rank"),
                  ("K1+K3", "CASH")))
CONFIGS = ((1, True), (5, True), (20, True), (60, True), (20, False))
TEST_BLOCKS = (5, 20, 60)


def require(ok, code):
    if not ok:
        raise ValueError(code)


def load(path, expected_sha256):
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    require(digest == expected_sha256, "CHALLENGER_SOURCE_SHA_MISMATCH")
    reader = csv.DictReader(raw.decode("utf-8").splitlines())
    require(reader.fieldnames == ["date", *COLUMNS],
            "CHALLENGER_EXACT_SCHEMA_MISMATCH")
    dates, rows = [], []
    for row in reader:
        require(None not in row and all(v is not None for v in row.values()),
                "CHALLENGER_ROW_WIDTH")
        day = dt.date.fromisoformat(row["date"])
        require(day.isoformat() == row["date"] and day.weekday() < 5,
                "CHALLENGER_DATE_INVALID")
        dates.append(day)
        rows.append([float(row[k]) for k in COLUMNS])
    require(len(dates) >= 252 and all(a < b for a, b in zip(dates, dates[1:])),
            "CHALLENGER_CALENDAR_INVALID")
    values = np.asarray(rows, dtype=float)
    require(values.shape == (len(dates), len(COLUMNS)) and
            np.isfinite(values).all() and (values > -1).all(),
            "CHALLENGER_RETURN_INVALID")
    return dates, values, digest


def indices(rng, dates, block, count, stratified):
    years = np.array([d.year for d in dates])
    partitions = ([np.flatnonzero(years == y) for y in np.unique(years)]
                  if stratified else [np.arange(len(dates))])
    parts = []
    for part in partitions:
        m = len(part)
        b = min(block, m)
        a = rng.integers(0, m, size=(count, (m+b-1)//b))
        parts.append(part[((a[:, :, None]+np.arange(b)) % m)
                          .reshape(count, -1)[:, :m]])
    return np.concatenate(parts, axis=1)


def draws(dates, block, stratified, n):
    rng = np.random.default_rng(SEED + block*10007 +
                                (0 if stratified else 2000003))
    for start in range(0, n, 128):
        yield indices(rng, dates, block, min(128, n-start), stratified)


def holm(p):
    p = np.asarray(p, float)
    require(np.isfinite(p).all() and ((p >= 0) & (p <= 1)).all(),
            "INVALID_PVALUES")
    order = np.argsort(p)
    out = np.empty_like(p)
    out[order] = np.minimum(1, np.maximum.accumulate(
        p[order]*(len(p)-np.arange(len(p)))))
    return out


def hac_p(d, lag):
    n = len(d)
    mean = d.mean(axis=0)
    u = d-mean
    longvar = (u*u).sum(axis=0)/n
    for k in range(1, min(lag, n-1)+1):
        longvar += 2*(1-k/(lag+1))*(u[k:]*u[:-k]).sum(axis=0)/n
    se = np.sqrt(np.maximum(0, longvar)/n)
    p = []
    for m, s in zip(mean, se):
        if s == 0:
            # An all-zero paired difference is a known tie, not significance.
            require(m == 0, "DEGENERATE_NONZERO_HAC")
            p.append(1.0)
        else:
            p.append(math.erfc(abs(m/s)/math.sqrt(2)))
    return np.asarray(p)


def differences(values):
    return np.column_stack([values[:, COLUMNS.index(a)] -
                            (0 if b == "CASH" else values[:, COLUMNS.index(b)])
                            for a, b in PAIRS])


def significance(dates, values, block, n=REPS):
    d = differences(values)
    mu = d.mean(axis=0)
    centered = d-mu
    sampled = np.concatenate([centered[ix].mean(axis=1)
                              for ix in draws(dates, block, False, n)])
    p = (1+(np.abs(sampled) >= np.abs(mu)).sum(axis=0))/(n+1)
    adjusted = holm(p)
    hp = hac_p(d, block)
    ha = holm(hp)
    lo, hi = mu+np.quantile(sampled, [.025, .975], axis=0)
    return [dict(candidate=a, comparator=b, block=block, replicates=n,
                 mean_bp_day=float(mu[i]*10000),
                 ci95_low_bp_day=float(lo[i]*10000),
                 ci95_high_bp_day=float(hi[i]*10000),
                 p_raw=float(p[i]), p_holm=float(adjusted[i]),
                 p_hac=float(hp[i]), p_hac_holm=float(ha[i]),
                 retrospective_only=True, approved_live=False)
            for i, (a, b) in enumerate(PAIRS)]


def monte_carlo(dates, values, block, stratified, n=REPS):
    finals, worsts = [], []
    for ix in draws(dates, block, stratified, n):
        equity = np.cumprod(1+values[ix], axis=1)
        peak = np.maximum.accumulate(np.maximum(equity, 1), axis=1)
        finals.append(equity[:, -1, :]-1)
        worsts.append((equity/peak-1).min(axis=1))
    finals, worsts = np.concatenate(finals), np.concatenate(worsts)
    require(np.isfinite(finals).all() and np.isfinite(worsts).all(),
            "NONFINITE_MC")
    rows = []
    for i, name in enumerate(COLUMNS):
        f, d = finals[:, i], worsts[:, i]
        rows.append(dict(scenario=name, block=block, year_stratified=stratified,
                         replicates=n, observed_return=float(np.prod(1+values[:, i])-1),
                         return_p05=float(np.quantile(f, .05)),
                         return_median=float(np.median(f)),
                         return_p95=float(np.quantile(f, .95)),
                         historical_loss_frequency=float(np.mean(f < 0)),
                         cvar05=float(np.sort(f)[:max(1, n//20)].mean()),
                         mdd_p05=float(np.quantile(d, .05)),
                         dd10_frequency=float(np.mean(d <= -.1)),
                         underperform_spy=float(np.mean(f < finals[:, COLUMNS.index("SPY")])),
                         underperform_qqq=float(np.mean(f < finals[:, COLUMNS.index("QQQ")]))))
    pairs = []
    for a, b in PAIRS:
        delta = finals[:, COLUMNS.index(a)] - (
            0 if b == "CASH" else finals[:, COLUMNS.index(b)])
        pairs.append(dict(candidate=a, comparator=b, block=block,
                          year_stratified=stratified, replicates=n,
                          positive_difference_frequency=float(np.mean(delta > 0)),
                          delta_p05=float(np.quantile(delta, .05)),
                          delta_median=float(np.median(delta)),
                          delta_p95=float(np.quantile(delta, .95))))
    return rows, pairs


def write_csv(path, rows):
    require(bool(rows), "EMPTY_RESULT")
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(path, sha, source_id, out):
    require(bool(source_id.strip()), "MISSING_SOURCE_ID")
    dates, values, digest = load(path, sha)
    # This is not a calendar completeness or source-finality certification.
    out = Path(out)
    require(not out.exists(), "OUTPUT_MUST_BE_NEW_VERSIONED_DIRECTORY")
    out.mkdir(parents=True)
    mc, pairs, sig = [], [], []
    for block, stratified in CONFIGS:
        rows, comparisons = monte_carlo(dates, values, block, stratified)
        mc.extend(rows)
        pairs.extend(comparisons)
    for block in TEST_BLOCKS:
        sig.extend(significance(dates, values, block))
    require(len(mc) == 220 and len(pairs) == 100 and len(sig) == 60,
            "INCOMPLETE_AUDIT")
    write_csv(out/"monte_carlo.csv", mc)
    write_csv(out/"paired_terminal.csv", pairs)
    write_csv(out/"significance.csv", sig)
    # Primary 40-strategy family only; broader trial ledger is a separate input.
    from challenger_overfit_validation import analyze as overfit_analyze
    overfit = overfit_analyze(list(COLUMNS[2:42]), dates, values[:, 2:42])
    overfit.update(source_id=source_id, source_sha256=digest)
    (out/"overfit_report.json").write_text(json.dumps(overfit, indent=2, allow_nan=False)+"\n")
    report = dict(version="daily20-challenger-stat-validation-v2",
                  overfit_report="overfit_report.json",
                  overfit_scope="declared_primary_40_strategies_only",
                  source_id=source_id, source_sha256=digest,
                  first_session=str(dates[0]), last_session=str(dates[-1]),
                  sessions=len(dates), seed=SEED, draws_per_configuration=REPS,
                  scenario_count=len(COLUMNS), hypothesis_family_size=len(PAIRS),
                  primary_test_block=20, significance_alpha=.05,
                  raw_p_lt_05=sum(r["p_raw"] < .05 for r in sig if r["block"] == 20),
                  holm_p_lt_05=sum(r["p_holm"] < .05 for r in sig if r["block"] == 20),
                  research_only=True, approved_live=False,
                  source_finality_certified=False, forward_validated=False,
                  model_selection_allowed=False, status="RETROSPECTIVE_RESEARCH_HOLD",
                  limitations=[
                      "Adaptive historical search is not corrected by this 20-test family.",
                      "Null-centered unstratified block mean test and HAC normal approximation are exploratory.",
                      "Pointwise CI is not a simultaneous or selection-adjusted interval.",
                      "Resampled daily equity returns do not rerun path-dependent fills.",
                      "Historical loss frequency is not a forecast probability.",
                      "Input hash is not proof of market-calendar or price finality.",
                      "SPY/QQQ are uncosted and not risk/exposure-matched here.",
                      "100bp geometry/eligibility stress must be reported upstream, never inferred from zero trades."])
    (out/"report.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    print(json.dumps(report))


def self_test():
    dates = []
    day = dt.date(2024, 1, 2)
    while len(dates) < 300:
        if day.weekday() < 5:
            dates.append(day)
        day += dt.timedelta(days=1)
    require(len(COLUMNS) == 44 and len(PAIRS) == 20, "SCHEMA_TEST")
    require(np.allclose(holm([.01, .04, .03]), [.03, .06, .06]), "HOLM_TEST")
    a = indices(np.random.default_rng(5), dates, 20, 8, True)
    y = np.array([d.year for d in dates])
    require(a.shape == (8, 300) and (y[a] == y).all(), "STRATIFICATION_TEST")
    values = np.zeros((len(dates), len(COLUMNS)))
    s = significance(dates, values, 20, 256)
    require(all(r["p_raw"] == r["p_holm"] == r["p_hac"] == 1 for r in s),
            "ZERO_PAIR_TEST")
    rng = np.random.default_rng(31)
    values = rng.normal(.0001, .004, values.shape)
    s1 = significance(dates, values, 20, 256)
    s2 = significance(dates, values, 20, 256)
    require(s1 == s2 and all(r["p_holm"] >= r["p_raw"] for r in s1),
            "DETERMINISM_TEST")
    mc, pairs = monte_carlo(dates, values, 20, True, 256)
    require(len(mc) == 44 and len(pairs) == 20, "MC_TEST")
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)/"curves.csv"
        with p.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["date", *COLUMNS])
            writer.writerows([[str(d), *r] for d, r in zip(dates, values)])
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        d, v, _ = load(p, h)
        require(d == dates and np.array_equal(v, values), "ROUNDTRIP_TEST")
        try:
            load(p, "0"*64)
        except ValueError as exc:
            require(str(exc) == "CHALLENGER_SOURCE_SHA_MISMATCH", "HASH_TEST")
        else:
            raise AssertionError("HASH_NOT_REJECTED")
    print("CHALLENGER_STAT_VALIDATION_SYNTHETIC_SELF_TEST_PASS")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--input")
    p.add_argument("--expected-sha256")
    p.add_argument("--source-id")
    p.add_argument("--out")
    a = p.parse_args()
    if a.self_test:
        self_test()
    else:
        require(all([a.input, a.expected_sha256, a.source_id, a.out]),
                "MISSING_AUDIT_ARGUMENT")
        run(a.input, a.expected_sha256, a.source_id, a.out)


if __name__ == "__main__":
    main()
