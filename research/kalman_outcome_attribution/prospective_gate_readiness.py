"""Read-only progress audit for the prospective protocol registered in #1078.

This is intentionally NOT a primary-study admission or inference engine.
It verifies pinned archive bytes, immutable journal/snapshot ancestry, original
first-seal evidence, gate availability and four-session settlement chronology.
Independent scheduled first+replay evidence and source certification remain
separate prerequisites. No results, model predictions or journals are written.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

import pandas as pd

PROTOCOL = "https://github.com/kimtk94/Codex/issues/1078"
REGISTERED_UTC = "2026-11-25T06:06:18Z"
FIRST = "2026-11-25"
LAST = "2027-11-24"
ATTESTATION_COMMIT = "7d3cb91f86183fe3905b3f70327ebf1f58bb2ac4"
ANCHOR_SHA = "256467e4ed8d3979c1f8c28993f9aed1fb7f4f16135879d1809b870456c8622f"
CORE = tuple("SPY QQQ QLD IWM AAPL MSFT AMZN GOOGL META NVDA AMD AVGO MU TSLA PLTR IONQ COIN MSTR JPM XOM".split())
EXCLUDED = {"QLD", "IONQ", "COIN", "MSTR"}
FAMILIES = ("BULL_LOGISTIC", "BEAR_LOGISTIC", "BEAR_RULE")
COSTS = (20, 40, 80)
JOURNALS = {"BULL": "research/forward_shadow/journal.jsonl",
            "BEAR": "research/bear_forward/journal.jsonl"}
PREFIX = "research/stability/snapshots/"
HASH = re.compile(r"^[a-f0-9]{64}$")


def require(ok, code):
    if not ok:
        raise ValueError(code)


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def event_hash(event):
    return sha(json.dumps({k:v for k,v in event.items() if k!="hash"},
                          sort_keys=True,separators=(",",":"),allow_nan=False).encode())


def verified_zip(path, expected_sha):
    require(isinstance(expected_sha,str) and HASH.fullmatch(expected_sha),
            "EXPECTED_OUTER_SHA_REQUIRED")
    p=Path(path)
    require(p.stat().st_size<=100_000_000,"ARCHIVE_SIZE_LIMIT")
    blob=p.read_bytes()
    require(sha(blob)==expected_sha,"OUTER_SHA_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names=z.namelist()
        require(len(names)==len(set(names)) and sum(x.file_size for x in z.infolist())<=300_000_000
                and all(n and not n.startswith("/") and "\\" not in n
                        and ".." not in PurePosixPath(n).parts for n in names),
                "UNSAFE_ARCHIVE")
        manifest=json.loads(z.read("drive_manifest.json"))
        require(manifest.get("format")=="kalman-daily20-drive-v1"
                and manifest.get("research_only") is True
                and manifest.get("production_writes") is False
                and manifest.get("oos_score_count")==20,"ARCHIVE_GOVERNANCE_MISMATCH")
        hashes=manifest["payload_hashes_sha256"]
        require(set(hashes)==set(names)-{"drive_manifest.json"},"MEMBER_SET_MISMATCH")
        payload={n:z.read(n) for n in hashes}
        require(all(sha(payload[n])==h for n,h in hashes.items()),"MEMBER_SHA_MISMATCH")
    return blob,manifest,payload


def verify_ancestry(anchor,current):
    for name in JOURNALS.values():
        require(current[name].startswith(anchor[name]),"JOURNAL_ANCHOR_PREFIX_CHANGED")
    for n,b in anchor.items():
        if n.startswith(PREFIX):
            require(current.get(n)==b,"ORIGINAL_SNAPSHOT_CHANGED")


def timestamp(value):
    t=pd.Timestamp(value)
    require(not pd.isna(t) and t.tzinfo is not None,"UTC_TIMESTAMP_REQUIRED")
    return t.tz_convert("UTC")


def sessions(calendar,day):
    a=pd.Timestamp(day)
    require(str(a.date())==day,"NONCANONICAL_SESSION_DATE")
    s=calendar.sessions_in_range(day,str((a+pd.Timedelta(days=28)).date()))
    require(len(s)>=5 and str(s[0].date())==day,"NON_XNYS_SESSION")
    return s[:5]


def registration_status(calendar,day):
    s=sessions(calendar,day)
    close=timestamp(calendar.session_close(s[0]))
    if day<FIRST or close<=timestamp(REGISTERED_UTC):
        return "EXCLUDED_BEFORE_REGISTRATION"
    if day>LAST:
        return "EXCLUDED_AFTER_FIXED_WINDOW"
    return "IN_REGISTERED_WINDOW"


def journal_index(payload,asof):
    signals={};settled={}
    for group,name in JOURNALS.items():
        previous="0"*64;last_signal_day=""
        for seq,line in enumerate(payload[name].splitlines(),1):
            e=json.loads(line)
            family="BULL_LOGISTIC" if group=="BULL" else e.get("family")
            key=(e.get("signal_date"),e.get("symbol"),family)
            require(e.get("seq")==seq and e.get("prev_hash")==previous and
                    e.get("hash")==event_hash(e),"JOURNAL_CHAIN_CHANGED")
            require(e.get("research_only") is True and key[1] in CORE
                    and family in (("BULL_LOGISTIC",) if group=="BULL" else FAMILIES[1:])
                    and isinstance(key[0],str) and str(date.fromisoformat(key[0]))==key[0]
                    and key[0]<=asof,"JOURNAL_IDENTITY_INVALID")
            if e.get("kind")=="SIGNAL":
                require(key not in signals and key[0]>=last_signal_day
                        and type(e.get("candidate")) is bool
                        and e.get("shadow_only") is (key[1] in EXCLUDED),
                        "SIGNAL_IDENTITY_INVALID")
                signals[key]=e;last_signal_day=key[0]
            elif e.get("kind")=="SETTLED":
                require(key in signals and key not in settled and
                        e.get("signal_hash")==signals[key]["hash"] and
                        e.get("candidate_at_signal_time") is signals[key]["candidate"] and
                        e.get("observation_only_no_execution") is True,
                        "SETTLEMENT_LINK_CHANGED")
                settled[key]=e
            else:
                raise ValueError("UNKNOWN_JOURNAL_KIND")
            previous=e["hash"]
    days=sorted({k[0] for k in signals})
    require(set(signals)=={(d,s,f) for d in days for s in CORE for f in FAMILIES},
            "INCOMPLETE_SESSION_COHORT")
    for (d,s,f),e in signals.items():
        if f!="BULL_LOGISTIC":
            require(e.get("baseline_signal_hash")==signals[(d,s,"BULL_LOGISTIC")]["hash"],
                    "BEAR_ORIGINAL_BULL_LINK_CHANGED")
    return signals,settled,days


def verify_timing(calendar,day,asof,signal,settlement):
    s=sessions(calendar,day)
    stamp=timestamp(signal["recorded_at_utc"])
    require(timestamp(calendar.session_close(s[0]))+pd.Timedelta(minutes=45)<=stamp
            <timestamp(calendar.session_open(s[1])),"FIRST_CAPTURE_OUTSIDE_WINDOW")
    entry,exit_day=str(s[1].date()),str(s[4].date())
    if settlement is None:
        return ("OVERDUE_MISSING_SETTLEMENT" if exit_day<=asof else "PENDING_FOUR_XNYS_SESSIONS")
    require(exit_day<=asof and settlement.get("entry_date")==entry
            and settlement.get("exit_date")==exit_day
            and timestamp(settlement["recorded_at_utc"])>=
                timestamp(calendar.session_close(s[4]))+pd.Timedelta(minutes=45),
            "SETTLEMENT_TIMING_OR_HORIZON_INVALID")
    def finite(x):
        return type(x) in (int,float) and math.isfinite(x)
    op,cl=settlement.get("entry_open"),settlement.get("exit_close")
    require(finite(op) and finite(cl) and op>0 and cl>0,"SETTLEMENT_PRICES_INVALID")
    gross=cl/op-1
    require(finite(settlement.get("gross_return")) and
            abs(gross-settlement["gross_return"])<=1e-9,"GROSS_RETURN_MISMATCH")
    costs=settlement.get("net_return_by_cost_bp")
    require(isinstance(costs,dict) and set(costs)=={str(c) for c in COSTS} and
            all(finite(costs[str(c)]) and abs(costs[str(c)]-(gross-c/10000))<=1e-9
                for c in COSTS),"NET_RETURN_MISMATCH")
    return "SETTLED_ARITHMETIC_ONLY"


def gate_class(family,candidate,features):
    if family=="BEAR_RULE":
        return "COVERAGE_CONTROL"
    if not candidate:
        return "NOT_ORIGINAL_CANDIDATE"
    cols=("ret5","spy_mom5_lag") if family=="BULL_LOGISTIC" else ("vix_lag","gld_mom5_lag")
    a,b=(features.get(c) for c in cols)
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in (a,b)):
        return "ABSTAIN_MISSING_FEATURE"
    ok=(a<0 and b>=0) if family=="BULL_LOGISTIC" else (a>=20 and b>=0)
    return "QUALIFIES" if ok else "COMPLEMENT"


def load_attestation(source):
    root=Path(source).resolve()
    got=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    require(got==ATTESTATION_COMMIT,"ATTESTATION_SOURCE_COMMIT_MISMATCH")
    path=root/"research/kalman_daily20/prospective_seal_attestation.py"
    spec=importlib.util.spec_from_file_location("pinned_seal_attestation",path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def audit(archive,expected_sha,anchor_path,original_source):
    import exchange_calendars as xc
    calendar=xc.get_calendar("XNYS",start="2026-01-01",end="2028-02-01")
    blob,manifest,payload=verified_zip(archive,expected_sha)
    _,_,anchor=verified_zip(anchor_path,ANCHOR_SHA)
    verify_ancestry(anchor,payload)
    asof=manifest["data_expected_last_closed_xnys"]
    signals,settled,days=journal_index(payload,asof)
    snapshot_days=sorted(n[len(PREFIX):-5] for n in payload
                         if n.startswith(PREFIX) and n.endswith(".json"))
    require(set(snapshot_days).issubset(days),"SNAPSHOT_WITHOUT_SIGNAL_SESSION")
    attestation=load_attestation(original_source)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        proof=attestation.verify_archive_prospective_seals(z,z.namelist(),snapshot_days)
    require(proof.get("prospective_seals_attested")==len(snapshot_days),
            "INCOMPLETE_FIRST_SEAL_ATTESTATION")
    rows=[]
    for day in days:
        status=registration_status(calendar,day)
        snapshot=json.loads(payload[PREFIX+day+".json"]) if day in snapshot_days else None
        counts=Counter(); maturity=Counter()
        for s in CORE:
            for f in FAMILIES:
                k=(day,s,f)
                if day in snapshot_days:
                    m=snapshot["models"][s]
                    features=dict(zip(m["feature_columns"],m["feature_values"]))
                    label=gate_class(f,signals[k]["candidate"],features)
                    timing=verify_timing(calendar,day,asof,signals[k],settled.get(k))
                    counts[(("PRIMARY16" if s not in EXCLUDED else "EXCLUDED4"),f,label)]+=1
                    maturity[timing]+=1
                elif day>=FIRST:
                    maturity["MISSING_ORIGINAL_SNAPSHOT"]+=1
        rows.append({"session":day,"registration_status":status,
                     "first_seal_attested":day in snapshot_days,
                     "scheduled_two_pass_independently_verified":False,
                     "primary_study_admitted":False,
                     "gate_counts":[{"cohort":c,"family":f,"class":k,"n":v}
                                    for (c,f,k),v in sorted(counts.items())],
                     "maturity_counts":dict(maturity),
                     "reason":("PRE_REGISTRATION_OR_OUTSIDE_WINDOW" if status!="IN_REGISTERED_WINDOW"
                               else "WAIT_INDEPENDENT_SCHEDULE_AND_SETTLEMENT_PROOF")})
    due=[]
    if asof>=FIRST:
        due=[str(d.date()) for d in calendar.sessions_in_range(FIRST,min(asof,LAST))]
    return {"schema":"kalman-prospective-gate-readiness-v1","protocol":PROTOCOL,
            "registered_utc":REGISTERED_UTC,"first_signal_session":FIRST,
            "last_signal_session":LAST,"asof":asof,"archive_sha256":expected_sha,
            "verified_members":len(payload),"anchor_sha256":ANCHOR_SHA,
            "anchor_prefix_preserved":True,"original_first_seals_attested":len(snapshot_days),
            "original_signals":len(signals),"original_settled":len(settled),
            "registered_window_sessions_expected":len(due),
            "registered_window_sessions_missing_original_snapshot":sorted(set(due)-set(snapshot_days)),
            "registered_window_attested_sessions":sum(r["first_seal_attested"] and
                r["registration_status"]=="IN_REGISTERED_WINDOW" for r in rows),
            "primary_study_admitted_sessions":0,"primary_study_admitted_outcomes":0,
            "source_finality_reported":manifest.get("source_finality_status"),
            "source_finality_reported_assets":manifest.get("source_finality_verified_assets"),
            "independent_source_certified":False,"scheduled_proof_checked":False,
            "study_inference_performed":False,"research_only":True,"approved_live":False,
            "production_writes":False,"sessions":rows,
            "limitations":["Readiness only. Outer SHA match does not independently authenticate its supplied provenance.",
                "Original first-seal attestation is not exchange-certified price evidence.",
                "No independent scheduled job/readback or vendor-revision verification in this module.",
                "No primary study admission, statistical inference, or outcome metric is emitted."]}


if __name__=="__main__":
    p=argparse.ArgumentParser()
    for name in ("archive","expected-sha256","anchor","original-source","out"):
        p.add_argument("--"+name,required=True)
    a=p.parse_args()
    report=audit(a.archive,a.expected_sha256,a.anchor,a.original_source)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print("PROSPECTIVE_READINESS_ONLY",report["original_signals"],
          report["registered_window_attested_sessions"],report["primary_study_admitted_outcomes"])
