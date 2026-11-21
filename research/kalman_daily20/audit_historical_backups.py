#!/usr/bin/env python3
"""Read-only, reproducible audit of four historically archived Daily20 Actions runs.

Reads unpacked GitHub Actions artifacts, never Google Drive credentials, never
places orders and never turns retrospective features into a prospective seal.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

RUN_IDS = ("44853890794", "44856445903", "44858008175", "44871574162")
CORE = ("SPY","QQQ","QLD","IWM","AAPL","MSFT","AMZN","GOOGL","META","NVDA",
        "AMD","AVGO","MU","TSLA","PLTR","IONQ","COIN","MSTR","JPM","XOM")
CONTEXT = ("SMH","^VIX","HYG","LQD","TLT","GLD")
EXPECTED_SESSION = "2026-11-20"
REQUIRED_RESEARCH = (
    "qc.json", "universe-derived.json", "research/summary.json",
    "research/latest_research_scores.csv", "research/oos_trades.csv",
    "research/portfolio_summary.json", "research/portfolio_scenarios.csv",
    "research/portfolio_annual.csv", "research/portfolio_daily_equity.csv",
    "research/portfolio_executions.csv",
    "research/forward_shadow/journal.jsonl",
    "research/forward_shadow/report.json",
)
LATER_RESEARCH = (
    "research/bear_forward/journal.jsonl", "research/bear_forward/report.json",
    "research/monte_carlo/monte_carlo_summary.json",
    "research/stability/report.json",
)


def digest(blob):
    return sha256(blob).hexdigest()


def json_member(archive, name):
    return json.loads(archive.read(name))


def check_zip(path):
    with ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or any(
                n.startswith("/") or "\\" in n or ".." in Path(n).parts for n in names):
            raise RuntimeError("UNSAFE_OR_DUPLICATED_ZIP_MEMBER:" + str(path))
        corrupted = z.testzip()
        if corrupted:
            raise RuntimeError("ZIP_CRC_ERROR:" + corrupted)
        return names


def time_index(df):
    if isinstance(df.index, pd.DatetimeIndex):
        return pd.to_datetime(df.index, errors="coerce", utc=True)
    for col in df.columns:
        if str(col).lower() in ("date", "datetime", "timestamp", "time", "__index_level_0__"):
            return pd.to_datetime(df[col], errors="coerce", utc=True)
    raise RuntimeError("PARQUET_TIMESTAMP_NOT_FOUND")


def read_parquet(blob, *, kind, symbol):
    df = pd.read_parquet(BytesIO(blob), engine="pyarrow")
    if df.empty:
        raise RuntimeError("PARQUET_EMPTY")
    stamps = time_index(df)
    if pd.isna(stamps).any():
        raise RuntimeError("PARQUET_INVALID_DATES")
    duplicate_dates = int(stamps.duplicated().sum())
    if duplicate_dates:
        raise RuntimeError("PARQUET_DUPLICATE_DATES:" + str(duplicate_dates))
    if not stamps.is_monotonic_increasing:
        raise RuntimeError("PARQUET_UNSORTED")
    start, end = str(stamps.min().date()), str(stamps.max().date())
    if end != EXPECTED_SESSION:
        raise RuntimeError("PARQUET_LAST_SESSION_MISMATCH:" + end)
    colmap = {str(k).lower(): k for k in df.columns}
    all_null_columns = [str(c) for c in df.columns if df[c].isna().all()]
    end_missing = [str(c) for c in df.columns if pd.isna(df[c].iloc[-1])]
    record = {
        "kind": kind, "symbol": symbol, "rows": int(len(df)),
        "first_session": start, "last_session": end,
        "columns": len(df.columns), "duplicate_dates": duplicate_dates,
        "all_null_columns": len(all_null_columns),
        "last_row_null_fields": len(end_missing),
        "missing_last_fields": ",".join(end_missing[:8]),
        "close_last": None, "ohlcv_logic_errors": None,
    }
    if kind == "OHLCV":
        required = ("open", "high", "low", "close", "volume")
        if not set(required).issubset(colmap):
            raise RuntimeError("MISSING_OHLCV_COLUMNS:" +
                               ",".join(sorted(set(required) - set(colmap))))
        vals = {k: pd.to_numeric(df[colmap[k]], errors="coerce") for k in required}
        if any(not pd.notna(vals[k].iloc[-1]) for k in required):
            raise RuntimeError("MISSING_LATEST_OHLCV")
        bad = (
            (vals["high"] + 1e-8 < vals["low"]) |
            (vals["high"] + 1e-8 < vals["open"]) |
            (vals["high"] + 1e-8 < vals["close"]) |
            (vals["low"] - 1e-8 > vals["open"]) |
            (vals["low"] - 1e-8 > vals["close"]) |
            (vals["open"] <= 0) | (vals["high"] <= 0) |
            (vals["low"] <= 0) | (vals["close"] <= 0) | (vals["volume"] < 0)
        )
        record["ohlcv_logic_errors"] = int(bad.sum())
        record["close_last"] = float(vals["close"].iloc[-1])
        if record["ohlcv_logic_errors"]:
            raise RuntimeError("INVALID_OHLCV_LOGIC:" + str(record["ohlcv_logic_errors"]))
    elif not len(df.columns):
        raise RuntimeError("EMPTY_FEATURE_SCHEMA")
    return record


def verify_journal(archive, path, *, expected, core):
    if path not in archive.namelist():
        return {"status":"NOT_PRESENT", "signals":0, "events":0, "candidate_signals":0}
    events = [json.loads(x) for x in archive.read(path).decode().splitlines() if x.strip()]
    parent = "0" * 64
    signals, candidate = set(), 0
    for i, event in enumerate(events, 1):
        old_hash = event.get("hash")
        payload = {k:v for k,v in event.items() if k != "hash"}
        calc = digest(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                 allow_nan=False).encode())
        if event.get("seq") != i or event.get("prev_hash") != parent or old_hash != calc:
            raise RuntimeError("BROKEN_FORWARD_EVENT_CHAIN:" + path)
        if event.get("symbol") not in core or event.get("research_only") is not True:
            raise RuntimeError("INVALID_FORWARD_EVENT:" + path)
        if event["kind"] == "SIGNAL":
            key = (event["signal_date"], event["symbol"],
                   event.get("family", "BULL_LOGISTIC"))
            if key in signals:
                raise RuntimeError("DUPLICATED_FORWARD_SIGNAL:" + path)
            signals.add(key)
            candidate += int(event.get("candidate") is True)
        parent = old_hash
    if len(signals) != expected:
        raise RuntimeError("WRONG_FORWARD_SIGNAL_COUNT:" + path)
    return {"status":"PASS", "events":len(events), "signals":len(signals),
            "candidate_signals":candidate, "hash_tip":parent}


def read_csv_rows(archive, member):
    return list(csv.DictReader(StringIO(archive.read(member).decode("utf-8-sig"))))


def one_run(path, run_id):
    base = Path(path)
    data_path = base / ("run" + run_id + "_data.zip")
    research_path = base / ("run" + run_id + "_research.zip")
    dn, rn = check_zip(data_path), check_zip(research_path)
    data_hash, research_hash = digest(data_path.read_bytes()), digest(research_path.read_bytes())
    per_symbol, problems = [], []
    with ZipFile(data_path) as data, ZipFile(research_path) as research:
        universe = json_member(research, "universe-derived.json")
        assets = {x["provider_symbol"]:x["group"] for x in universe["assets"]}
        expected = set(CORE + CONTEXT)
        if set(assets) != expected or {s for s,g in assets.items() if g=="DAILY20_CORE"} != set(CORE):
            raise RuntimeError("UNIVERSE_NOT_MATCHING_CANONICAL_26")
        expected_paths = set()
        for s in CORE + CONTEXT:
            key = "vix" if s=="^VIX" else s.lower()
            price = "market/raw/yfinance/yf_" + key + ".parquet"
            feature = "features/talib/" + key + ".parquet"
            expected_paths.update((price, feature))
            for kind, member in (("OHLCV",price),("TA",feature)):
                if member not in dn:
                    raise RuntimeError("MISSING_PARQUET:" + member)
                blob = data.read(member)
                try:
                    row = read_parquet(blob, kind=kind, symbol=s)
                    row.update({"run_id":run_id, "member":member,
                                "size_bytes":len(blob), "sha256":digest(blob),
                                "status":"PASS"})
                except Exception as error:
                    row = {"run_id":run_id, "symbol":s, "kind":kind,
                           "member":member, "size_bytes":len(blob),
                           "sha256":digest(blob),"status":"FAIL",
                           "error":str(error)}
                    problems.append(f"{member}: {error}")
                per_symbol.append(row)
        if set(dn) != expected_paths:
            raise RuntimeError("DATA_ARCHIVE_UNEXPECTED_MEMBER_SET")
        qc = json_member(research, "qc.json")
        summary = json_member(research, "research/summary.json")
        if qc.get("status")!="READY" or qc.get("required")!=26 or qc.get("ready")!=26:
            raise RuntimeError("QC_NOT_READY_26")
        if qc.get("expected_session")!=EXPECTED_SESSION or summary.get("latest_score_count")!=20:
            raise RuntimeError("RESEARCH_SESSION_OR_SCORES_INVALID")
        if any(name not in rn for name in REQUIRED_RESEARCH):
            raise RuntimeError("REQUIRED_RESEARCH_EVIDENCE_MISSING")
        rows = read_csv_rows(research, "research/latest_research_scores.csv")
        if len(rows)!=20 or set(x["symbol"] for x in rows)!=set(CORE):
            raise RuntimeError("RESEARCH_SCORE_ROW_COVERAGE_INVALID")
        bull = verify_journal(research, "research/forward_shadow/journal.jsonl",
                              expected=20, core=set(CORE))
        if run_id == RUN_IDS[0]:
            bear = {"status":"NOT_YET_CREATED", "signals":0, "candidate_signals":0}
        else:
            bear = verify_journal(research, "research/bear_forward/journal.jsonl",
                                  expected=40, core=set(CORE))
        coverage = {name: name in rn for name in LATER_RESEARCH}
        report = (json_member(research,"research/stability/report.json")
                  if coverage["research/stability/report.json"] else None)
        if report and report.get("current_session_has_original_snapshot"):
            raise RuntimeError("FALSE_ORIGINAL_SNAPSHOT_FOR_LEGACY_DATE")
        snapshots = [name for name in rn
                     if name.startswith("research/stability/snapshots/")]
        if snapshots:
            raise RuntimeError("LEGACY_SESSION_SNAPSHOT_WRONGFULLY_FROZEN")
    return per_symbol, {
        "run_id":run_id, "data_archive_files":len(dn), "research_archive_files":len(rn),
        "data_archive_sha256":data_hash, "research_archive_sha256":research_hash,
        "data_archive_size_bytes":data_path.stat().st_size,
        "research_archive_size_bytes":research_path.stat().st_size,
        "qc_status":qc["status"], "qc_ready":qc["ready"],
        "score_rows":len(rows), "bull_signals":bull["signals"],
        "bull_candidates":bull["candidate_signals"],
        "bear_signals":bear["signals"],
        "bear_candidates":bear["candidate_signals"],
        "bull_journal_hash_status":bull["status"],
        "bear_journal_hash_status":bear["status"],
        "monte_carlo_present":coverage["research/monte_carlo/monte_carlo_summary.json"],
        "stability_report_present":bool(report),
        "original_2026_11_20_21feature_seal_present":False,
        "parquet_failures":len(problems), "parquet_problem_details":" | ".join(problems[:12]),
    }


def write_csv(path, rows, columns):
    with Path(path).open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input-dir",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    out=Path(a.out)
    out.mkdir(parents=True,exist_ok=True)
    records,summary=[],[]
    for rid in RUN_IDS:
        rows,review=one_run(a.input_dir,rid)
        records+=rows
        summary.append(review)
    sha={(x["run_id"],x["symbol"],x["kind"]):x for x in records}
    differences=[]
    for s in CORE+CONTEXT:
        for k in ("OHLCV","TA"):
            first=sha[(RUN_IDS[0],s,k)]
            last=sha[(RUN_IDS[-1],s,k)]
            price_a=first.get("close_last")
            price_b=last.get("close_last")
            differences.append({
                "symbol":s,"kind":k,
                "initial_archive_sha256":first["sha256"],
                "final_archive_sha256":last["sha256"],
                "file_bytes_changed":first["sha256"]!=last["sha256"],
                "initial_close":price_a,
                "final_close":price_b,
                "close_revision_percent":(100*(price_b/price_a-1)
                    if k=="OHLCV" and price_a and price_b else None),
            })
    write_csv(out/"parquet_inventory.csv",records,
              ["run_id","symbol","kind","member","status","rows","first_session",
               "last_session","columns","duplicate_dates","all_null_columns",
               "last_row_null_fields","missing_last_fields","ohlcv_logic_errors",
               "close_last","size_bytes","sha256","error"])
    write_csv(out/"archive_summary.csv",summary,list(summary[0]))
    write_csv(out/"cross_version_differences.csv",differences,list(differences[0]))
    errors=[x for x in records if x["status"]!="PASS"]
    result={
        "version":"daily20-historical-backup-audit-v1",
        "last_session":EXPECTED_SESSION,
        "input_versions":len(RUN_IDS),"archived_zip_files":len(RUN_IDS)*2,
        "expected_parquet_per_version":52,
        "checked_parquet_files":len(records),
        "parquet_pass":len(records)-len(errors),"parquet_fail":len(errors),
        "raw_price_parquet_per_version":26,"ta_parquet_per_version":26,
        "rows_by_run":{s["run_id"]:{"research_files":s["research_archive_files"],
                                  "parquet_failures":s["parquet_failures"],
                                  "bull_signals":s["bull_signals"],
                                  "bear_signals":s["bear_signals"],
                                  "bear_candidates":s["bear_candidates"],
                                  "monte_carlo":s["monte_carlo_present"],
                                  "stability_report":s["stability_report_present"]}
                       for s in summary},
        "changed_ohlcv_file_hashes":sum(x["file_bytes_changed"] for x in differences
                                        if x["kind"]=="OHLCV"),
        "changed_ta_file_hashes":sum(x["file_bytes_changed"] for x in differences
                                     if x["kind"]=="TA"),
        "legacy_original_feature_snapshots":0,
        "independent_provider_price_truth_verified":False,
        "all_local_structural_checks_pass":not errors,
        "note":"Archive/Parquet structural validity does not prove original vendor quote accuracy.",
    }
    (out/"audit_report.json").write_text(json.dumps(result,indent=2)+"\n")
    print("DAILY20_ARCHIVE_AUDIT_SUMMARY",json.dumps(result))
    if errors:
        raise SystemExit("PARQUET_STRUCTURE_AUDIT_FAILURES: "+str(len(errors)))


if __name__=="__main__":
    main()
