#!/usr/bin/env python3
"""Daily20 26-asset price-revision decomposition on original immutable archives.

Retrospective and READ-ONLY. Compares three successive full-history reloads
plus first-vs-last for the same 2026-11-20 closed session. A pattern is not
proof of an upstream cause (dividend, split, provisional quote, or repair).
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

from daily20 import load_spec, market_file, load_bars, write_json

RUNS = ("44853890794", "44856445903", "44858008175", "44871574162")
SESSION = "2026-11-20"
PAIR_IDS = tuple(zip(RUNS[:-1], RUNS[1:])) + ((RUNS[0], RUNS[-1]),)
DATA_ARTIFACT_DIGEST = {
    "44853890794": "3f6166ce09e33f903427ed9fc9a4d5f04c486b10f290ca8f06e055063b7b9ba9",
    "44856445903": "e437f519321eb92ccec3b3987ed7a22c618dcbea2176a92337fb55376f2c5a26",
    "44858008175": "57351e216dcd48e5416b9576772b5aca2d047088d1dc041455a7fddfc2086fed",
    "44871574162": "a79197124aba572b1eaeaee2278324de0e14d32ae504fe705aa35f3cc076deb8",
}
RESEARCH_ARTIFACT_DIGEST = {
    "44853890794": "61820c4dad41f90bddc92a5c32859205181d7db56ba01862ed78dd5cfeb77aaf",
    "44856445903": "92fdb0f412bfda30aca9000fefc36805876470fee36e62bcf11c72d442f1cb0b",
    "44858008175": "9dfa7e766d5f6376f51ab8b816f0bb1bf10f151ea88042c228ad203af97f4ef4",
    "44871574162": "b940c6fed2764eeffd60a6cf459407de4a9a9bf20afdaae5d4779f8bf32882e6",
}
OHLC = ("open", "high", "low", "close")
PRICE_REL_TOL = 1e-7
MATERIAL = 0.001  # > 10 basis points, not a trivial float difference


def sha(blob):
    return sha256(blob).hexdigest()


def verified_zip(path, expected, *, prefix):
    raw = Path(path).read_bytes()
    if sha(raw) != expected:
        raise RuntimeError("UNEXPECTED_ORIGINAL_ARTIFACT_SHA:" + str(path))
    z = ZipFile(BytesIO(raw))
    names = z.namelist()
    if (len(names) != len(set(names))
            or any(n.startswith("/") or ".." in Path(n).parts or "\\" in n
                   for n in names)):
        raise RuntimeError("INVALID_ARTIFACT_PATHS")
    if z.testzip() is not None:
        raise RuntimeError("INVALID_ARTIFACT_CRC")
    if not any(n.startswith(prefix) for n in names):
        raise RuntimeError("ARCHIVE_MISSING_EXPECTED_DATA:" + prefix)
    return z


def frame(archive, symbol):
    name = f"market/raw/yfinance/yf_{symbol.lower().replace('^','')}.parquet"
    if name not in archive.namelist():
        raise RuntimeError("ASSET_MISSING:" + symbol)
    f = pd.read_parquet(BytesIO(archive.read(name)))
    if f.empty or not all(c in f.columns for c in (*OHLC, "volume", "timestamp", "is_adjusted")):
        raise RuntimeError("INVALID_OHLCV_SCHEMA:" + symbol)
    if f["symbol"].astype(str).nunique() != 1:
        raise RuntimeError("SYMBOL_IDENTITY_CORRUPTED")
    return load_bars(BytesIO(archive.read(name)))


def summarize_pair(old, new, *, symbol, left, right):
    common = old.index.intersection(new.index)
    only_a = old.index.difference(new.index)
    only_b = new.index.difference(old.index)
    asof = pd.Timestamp(SESSION)
    if len(common) < 250 or asof not in common:
        raise RuntimeError("NO_COMPLETE_COMMON_SESSIONS:" + symbol)
    a = old.loc[common]
    b = new.loc[common]
    mask_nonterminal = common != asof
    c0 = a["close"].to_numpy(dtype=float)
    c1 = b["close"].to_numpy(dtype=float)
    valid = np.isfinite(c0) & np.isfinite(c1) & (c0 > 0)
    if not np.all(valid[mask_nonterminal]):
        if symbol != "^VIX":
            raise RuntimeError("UNEXPECTED_NONFINITE_HISTORIC_CLOSE")
    rel = np.full(len(common),np.nan)
    rel[valid] = c1[valid] / c0[valid] - 1
    abs_rel = np.abs(rel)
    material_mask = abs_rel > MATERIAL
    changed_mask = abs_rel > PRICE_REL_TOL
    nonterminal_changed = int((changed_mask & mask_nonterminal).sum())
    nonterminal_material = int((material_mask & mask_nonterminal).sum())
    nonterminal_gt1bp = int(((abs_rel > .0001) & mask_nonterminal).sum())
    terminal_changed = bool(changed_mask[common.get_loc(asof)])
    terminal_material = bool(material_mask[common.get_loc(asof)])
    med = float(np.nanmedian(rel[mask_nonterminal])) if valid[mask_nonterminal].any() else None
    residual = np.abs((1+rel[mask_nonterminal])/(1+med)-1) if med is not None else np.array([])
    p95resid = float(np.nanquantile(residual,.95)) if np.isfinite(residual).any() else None
    historic_dates = common[changed_mask & mask_nonterminal]
    revised_dates = common[changed_mask]
    price_reprice = {}
    for col in (*OHLC, "volume"):
        x = pd.to_numeric(a[col],errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(b[col],errors="coerce").to_numpy(dtype=float)
        good = np.isfinite(x)&np.isfinite(y)
        relx = np.full(len(common),np.nan)
        nz = good & (x != 0)
        relx[nz] = y[nz]/x[nz]-1
        diff = np.zeros(len(common), dtype=bool)
        diff[good] = (np.abs(y[good] - x[good]) >
                     1e-7 * np.maximum(1, np.abs(x[good])))
        price_reprice[col] = {"changed_sessions": int(diff.sum()),
            "nonterminal_changed_sessions": int((diff & mask_nonterminal).sum()),
            "asof_left": float(x[common.get_loc(asof)]) if np.isfinite(x[common.get_loc(asof)]) else None,
            "asof_right": float(y[common.get_loc(asof)]) if np.isfinite(y[common.get_loc(asof)]) else None}
    volume_changed = bool(price_reprice["volume"]["changed_sessions"])
    global_scale_candidate = bool(
        med is not None and abs(med) > 1e-5 and p95resid is not None
        and p95resid < 1e-5 and
        nonterminal_changed > .8*int(mask_nonterminal.sum()) and not volume_changed)
    if (not terminal_changed and not nonterminal_changed
            and not any(price_reprice[x]["changed_sessions"] for x in (*OHLC,"volume"))):
        classification = "NUMERIC_OHLCV_STABLE"
    elif terminal_changed and not nonterminal_changed:
        classification = "TERMINAL_CLOSE_REVISION_ONLY"
    elif global_scale_candidate:
        classification = "GLOBAL_HISTORICAL_PRICE_SCALING_CANDIDATE"
    elif terminal_changed and nonterminal_changed and not nonterminal_gt1bp:
        classification = "TERMINAL_WITH_SUB_1BP_HISTORY_DRIFT"
    elif not terminal_changed and nonterminal_changed and not nonterminal_gt1bp:
        classification = "SUB_1BP_HISTORY_DRIFT_ONLY"
    elif terminal_changed and nonterminal_changed:
        classification = "TERMINAL_AND_MATERIAL_HISTORICAL_REVISIONS"
    elif nonterminal_changed:
        classification = "MATERIAL_HISTORICAL_REVISIONS_WITHOUT_TERMINAL"
    else:
        classification = "OTHER_OHLCV_OR_VOLUME_REVISION"
    return {
        "left_run":left,"right_run":right,"symbol":symbol,
        "common_sessions":len(common),"old_only_sessions":len(only_a),"new_only_sessions":len(only_b),
        "first_shared":str(common[0].date()),"last_shared":str(common[-1].date()),
        "terminal_close_old":float(c0[common.get_loc(asof)]) if np.isfinite(c0[common.get_loc(asof)]) else None,
        "terminal_close_new":float(c1[common.get_loc(asof)]) if np.isfinite(c1[common.get_loc(asof)]) else None,
        "terminal_close_change_pct":float(rel[common.get_loc(asof)]*100) if np.isfinite(rel[common.get_loc(asof)]) else None,
        "terminal_changed":terminal_changed, "terminal_material_gt10bps":terminal_material,
        "nonterminal_close_changed":nonterminal_changed,
        "nonterminal_close_material_gt10bps":nonterminal_material,
        "nonterminal_close_material_gt1bp":nonterminal_gt1bp,
        "nonterminal_median_scale_pct":med*100 if med is not None else None,
        "nonterminal_scale_residual_p95_pct":p95resid*100 if p95resid is not None else None,
        "nonterminal_close_max_abs_pct":float(np.nanmax(abs_rel[mask_nonterminal])*100)
                  if np.isfinite(abs_rel[mask_nonterminal]).any() else None,
        "first_changed_date":str(revised_dates.min().date()) if len(revised_dates) else None,
        "first_nonterminal_changed_date":str(historic_dates.min().date()) if len(historic_dates) else None,
        "volume_changed":volume_changed, "global_scale_candidate":global_scale_candidate,
        "classify_revision":classification,
        "changed_open_sessions":price_reprice["open"]["changed_sessions"],
        "changed_high_sessions":price_reprice["high"]["changed_sessions"],
        "changed_low_sessions":price_reprice["low"]["changed_sessions"],
        "changed_close_sessions":price_reprice["close"]["changed_sessions"],
        "changed_volume_sessions":price_reprice["volume"]["changed_sessions"],
        "asof_open_old":price_reprice["open"]["asof_left"],
        "asof_open_new":price_reprice["open"]["asof_right"],
        "asof_volume_old":price_reprice["volume"]["asof_left"],
        "asof_volume_new":price_reprice["volume"]["asof_right"],
    }


def _save_csv(filename,rows):
    if not rows:
        raise RuntimeError("EMPTY_CSV")
    with open(filename,"w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys()))
        w.writeheader();w.writerows(rows)


def run(input_dir, output, spec):
    root=Path(input_dir)
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    archives={}
    source_modes={}
    for rid in RUNS:
        data=verified_zip(root/f"run{rid}_data.zip",DATA_ARTIFACT_DIGEST[rid],
                          prefix="market/raw/yfinance/")
        research=verified_zip(root/f"run{rid}_research.zip",RESEARCH_ARTIFACT_DIGEST[rid],
                              prefix="research/")
        meta=json.loads(research.read("market/refresh_mode.json"))
        if (meta.get("mode") != "FULL_HISTORY" or
             meta.get("reason") != "WEEKLY_OR_FORCE_FULL" or
             meta.get("end_exclusive") != "2026-11-21"):
            raise RuntimeError("NOT_REPEATED_FULL_RELOAD:" + rid)
        archives[rid]=data
        source_modes[rid]=meta
        research.close()
    symbols=spec["core"]+spec["context"]
    if len(symbols)!=26:
        raise RuntimeError("INVALID_RESEARCH_UNIVERSE")
    rows=[]
    for symbol in symbols:
        frames={rid:frame(archives[rid],symbol) for rid in RUNS}
        for left,right in PAIR_IDS:
            rows.append(summarize_pair(frames[left],frames[right],
                         symbol=symbol,left=left,right=right))
    _save_csv(output/"price_revision_26asset_pairs.csv",rows)
    terminal=[r for r in rows if r["left_run"]==RUNS[0] and r["right_run"]==RUNS[-1]]
    _save_csv(output/"first_vs_last_26asset.csv",terminal)
    transitions=[]
    for left,right in PAIR_IDS:
        step=[x for x in rows if x["left_run"]==left and x["right_run"]==right]
        dist={}
        for r in step:
            k=r["classify_revision"];dist[k]=dist.get(k,0)+1
        transitions.append({
            "left":left, "right":right,
            "material_terminal_gt10bps":sum(r["terminal_material_gt10bps"] for r in step),
            "terminal_changed":sum(r["terminal_changed"] for r in step),
            "nonterminal_any_changes":sum(r["nonterminal_close_changed"]>0 for r in step),
            "historical_10bps_any":sum(r["nonterminal_close_material_gt10bps"]>0 for r in step),
            "historical_1bp_any":sum(r["nonterminal_close_material_gt1bp"]>0 for r in step),
            "global_scale_candidates":sum(r["global_scale_candidate"] for r in step),
            "volume_changed":sum(r["volume_changed"] for r in step),
            "classification_counts":dist,
        })
    metadata={
        "version":"daily20-26-asset-repricing-root-cause-evidence-v1",
        "status":"SOURCE_CORRECTION_UNRESOLVED_RESEARCH_HOLD",
        "source_last_closed_session":SESSION,
        "archived_versions":list(RUNS),
        "original_archive_sha256_pinned":True,
        "provider_configuration":{
            "source":"yfinance","auto_adjust_equities":True,"repair":True,
            "keepna":True,"vix_adjusted":False,
            "all_archived_runs_full_history":True,
        },
        "total_source_pairs":len(PAIR_IDS),
        "verified_asset_pair_comparisons":len(rows),
        "full_vs_full":transitions,
        "first_vs_last_terminal_gt10bps_symbols":[r["symbol"] for r in terminal
                    if r["terminal_material_gt10bps"]],
        "first_vs_last_historic_gt10bps_symbols":[r["symbol"] for r in terminal
                    if r["nonterminal_close_material_gt10bps"]>0],
        "first_vs_last_global_scaling_candidates":[r["symbol"] for r in terminal
                    if r["global_scale_candidate"]],
        "first_vs_last_terminal_negative_count":sum(
            r["terminal_close_change_pct"] is not None and
            r["terminal_close_change_pct"] < -.000001 for r in terminal),
        "first_vs_last_terminal_positive_count":sum(
            r["terminal_close_change_pct"] is not None and
            r["terminal_close_change_pct"] > .000001 for r in terminal),
        "first_vs_last_historic_max_abs_pct":max(
            (r["nonterminal_close_max_abs_pct"] or 0) for r in terminal),
        "largest_first_vs_last_terminal_abs_pct": sorted(
            [{"symbol":r["symbol"],"change_pct":r["terminal_close_change_pct"]}
             for r in terminal if r["terminal_close_change_pct"] is not None],
            key=lambda x:abs(x["change_pct"]),reverse=True)[:12],
        "external_validation":{
            "corporate_action_times_verified":False,
            "actual_yahoo_repair_trace_saved":False,
            "independent_exchange_close_verified":False,
            "attributed_cause":"UNPROVEN_PATTERN_EVIDENCE_ONLY",
        },
        "no_live_changes":True,"no_drive_writes":True,"frozen_journals_untouched":True,
        "files":["price_revision_26asset_pairs.csv","first_vs_last_26asset.csv"],
    }
    write_json(output/"price_revision_root_cause.json",metadata)
    print("DAILY20_26ASSET_REPRICE_AUDIT",json.dumps({
        "status":metadata["status"],"total_pairs":len(rows),
        "pairs":transitions,"largest":metadata["largest_first_vs_last_terminal_abs_pct"][:8]
    }))
    for z in archives.values():z.close()
    return metadata


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input-dir",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--config",default="research/kalman_daily20/universe.json")
    a=p.parse_args()
    run(a.input_dir,a.out,load_spec(a.config))


if __name__=="__main__":
    main()
