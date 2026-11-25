"""Read-only independent schedule evidence for #1078, not a study admission.

Check actual GitHub run/job records and logs against the original sealed archive.
An operational success is not enough: reject drift, substituted first captures,
changed code, late capture, ambiguous slots, failed jobs and stale readback.
No Drive/broker credentials, raw logs, predictions or source mutations.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile
import pandas as pd

from prospective_gate_readiness import (
    PROTOCOL, ATTESTATION_COMMIT, ANCHOR_SHA, PREFIX, HASH, FIRST, LAST,
    verified_zip, verify_ancestry, load_attestation, sessions, timestamp, sha,
    registration_status, journal_index, verify_timing,
)

ROOT = "https://api.github.com/repos/kimtk94/Codex"
WORKFLOW_ID = 425141580
WORKFLOW_PATH = ".github/workflows/kalman-daily20.yml"
SLOTS = ("40 2 * * 2-6", "40 4 * * 2-6")
MODES = ("FIRST_GENUINE_SEAL_EXPECTED", "SAME_SESSION_REPLAY_EXPECTED")
STATUSES = ("FIRST_SEAL_26_PRICE_420_FEATURE_40_MODEL_60_EVENT_ATTESTED_HOLD",
            "SAME_SESSION_REPLAY_INPUTS_UNCHANGED_SOURCE_HOLD")
SEAL_STATUS = "NEW_SESSION_ORIGINAL_INPUTS_AND_EVENTS_ATTESTED_RESEARCH_HOLD"
REQUIRED = {"contracts", "restore-drive-cache", "daily-research", "persist-google-drive"}
REHEARSAL = {"session":"2026-11-23", "source_run":45382109010,
             "source_sha":"06c66c0fea6de93eeb581ce856d648d24c0ff942",
             "snapshot_sha256":"1d054e08d38a00f4c46371d3f11921310ea26b34262a98972192e416f4187d7f"}


def check(condition, problems, code):
    if not condition:
        problems.add(code)


def audit_pair(identity, runs, calendar):
    day = identity["session"]
    window = sessions(calendar,day)
    next_open = timestamp(calendar.session_open(window[1]))
    target = (pd.Timestamp(day)+pd.Timedelta(days=1)).date()
    problems=set()
    check(type(identity["source_run"]) is int and identity["source_run"]>0
          and bool(HASH.fullmatch(identity["snapshot_sha256"]))
          and isinstance(identity["source_sha"],str) and len(identity["source_sha"])==40,
          problems,"INVALID_SNAPSHOT_IDENTITY")
    by_slot = {slot:[] for slot in SLOTS}
    seen=set()
    for run in runs:
        rid = run.get("run_id")
        check(type(rid) is int and rid not in seen, problems,"DUPLICATE_OR_INVALID_RUN")
        seen.add(rid)
        check(run.get("workflow_id")==WORKFLOW_ID and run.get("path")==WORKFLOW_PATH
              and run.get("event")=="schedule" and run.get("head_branch")=="main",
              problems,"WRONG_WORKFLOW_EVENT_OR_BRANCH")
        if run.get("slot") not in by_slot:
            problems.add("UNCLASSIFIED_SCHEDULED_RUN")
        else:
            by_slot[run["slot"]].append(run)
    selected=[]
    for i,slot in enumerate(SLOTS):
        mark="FIRST" if i==0 else "REPLAY"
        group=by_slot[slot]
        if len(group)!=1:
            problems.add(mark+"_MISSING" if not group else mark+"_AMBIGUOUS")
            selected.append(None)
            continue
        run=group[0]
        selected.append(run)
        check(run.get("status")=="completed" and run.get("conclusion")=="success"
              and run.get("run_attempt")==1 and not run.get("missing_successful_jobs")
              and not run.get("log_access_error_codes"),problems,mark+"_RUN_OR_JOB_UNVERIFIED")
        check(run.get("session")==day and run.get("mode")==MODES[i],
              problems,mark+"_SESSION_OR_ROLE_MISMATCH")
        post=run.get("post") or {}
        check(post.get("session")==day and post.get("mode")==MODES[i]
              and post.get("status")==STATUSES[i] and post.get("new")==("60" if i==0 else "0"),
              problems,mark+"_POSTFLIGHT_MISMATCH")
        check(post.get("changed")=="False",problems,mark+"_INPUTS_CHANGED_OR_UNKNOWN")
        check(run.get("remote_drive_readback") is True,problems,mark+"_REMOTE_READBACK_MISSING")
        seal=run.get("first_seal_readback") or {}
        check(seal.get("session")==day and seal.get("status")==SEAL_STATUS
              and seal.get("current") is True and type(seal.get("deep")) is int and seal["deep"]>=1
              and seal.get("original_run")==identity["source_run"]
              and seal.get("snapshot_sha256")==identity["snapshot_sha256"],
              problems,mark+"_ARCHIVE_READBACK_ANCHOR_MISMATCH")
        check(run.get("head_sha")==identity["source_sha"],problems,mark+"_CODE_SHA_MISMATCH")
        try:
            created=timestamp(run["created_at"])
            start=timestamp(run["research_started_at"])
            end=timestamp(run["publisher_completed_at"])
            earliest=pd.Timestamp(str(target)+"T"+("02:40:00Z" if i==0 else "04:40:00Z"))
            check(created.date()==target and earliest<=created<=start<=end<next_open,
                  problems,mark+"_NOT_PREOPEN_SCHEDULED_CAPTURE")
        except (KeyError,ValueError,TypeError):
            problems.add(mark+"_MISSING_JOB_TIMESTAMPS")
    first,replay=selected
    if first is not None:
        check(first.get("run_id")==identity["source_run"],problems,"FIRST_NOT_ORIGINAL_CAPTURE")
    if first is not None and replay is not None:
        check(type(first.get("run_id")) is int and type(replay.get("run_id")) is int
              and first["run_id"]<replay["run_id"],problems,"REPLAY_NOT_INDEPENDENT_LATER_RUN")
        try:
            check(timestamp(first["publisher_completed_at"])<=timestamp(replay["research_started_at"]),
                  problems,"REPLAY_RESEARCH_STARTED_BEFORE_FIRST_READBACK")
        except (KeyError,ValueError,TypeError):
            problems.add("REPLAY_ORDER_TIMESTAMPS_MISSING")
    return {"schema":"kalman-prospective-schedule-evidence-v1","protocol":PROTOCOL,
            "session":day,"scheduled_utc_day":str(target),
            "source_run":identity["source_run"],"source_sha":identity["source_sha"],
            "snapshot_sha256":identity["snapshot_sha256"],
            "run_count":len(runs),"first_run":first.get("run_id") if first else None,
            "replay_run":replay.get("run_id") if replay else None,
            "scheduled_evidence_status":"PASS" if not problems else "HOLD",
            "problem_codes":sorted(problems),"research_only":True,"approved_live":False,
            "production_writes":False,"source_finality_certified":False,
            "primary_study_admitted":False,
            "limitations":["Two-pass evidence is not independent price certification or scientific approval.",
                           "Primary admission also requires complete immutable journal, settlement and source checks.",
                           "Missing or inaccessible evidence remains HOLD. No manual substitute."]}


def load_watchdog(source):
    root=Path(source).resolve()
    got=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if got!=ATTESTATION_COMMIT:
        raise ValueError("WATCHDOG_SOURCE_COMMIT_MISMATCH")
    sys.path.insert(0,str(root/"research/kalman_daily20"))
    import scheduled_slot_watchdog as watchdog
    import ops_readiness
    return watchdog,ops_readiness


def collect(day,source,token):
    watchdog,ops=load_watchdog(source)
    target=str((pd.Timestamp(day)+pd.Timedelta(days=1)).date())
    endpoint=f"{ROOT}/actions/workflows/{WORKFLOW_ID}/runs?branch=main&event=schedule&created={target}&per_page=100"
    listing=ops.api(endpoint,token)
    raw=listing.get("workflow_runs")
    if not isinstance(raw,list) or len(raw)>=100 or listing.get("total_count")!=len(raw):
        raise ValueError("INCOMPLETE_SCHEDULE_API_LIST")
    out=[]
    for run in raw:
        rid=run.get("id")
        if type(rid) is not int:
            raise ValueError("INVALID_RUN_ID")
        job_list=ops.api(f"{ROOT}/actions/runs/{rid}/jobs?per_page=100",token)
        jobs=job_list.get("jobs")
        if not isinstance(jobs,list) or len(jobs)>=100 or job_list.get("total_count")!=len(jobs):
            raise ValueError("INCOMPLETE_JOB_API_LIST")
        names={j["name"]:j for j in jobs}
        if len(names)!=len(jobs):
            raise ValueError("DUPLICATE_JOB_ROLE")
        logs=[];errors=[]
        for role in ("daily-research","persist-google-drive"):
            log,err=ops.safe_job_log(ROOT,names.get(role,{}).get("id"),token,role)
            logs.append(log)
            if err:errors.append(err)
        proof=watchdog.job_evidence(run,jobs,*logs)
        proof.update(workflow_id=run.get("workflow_id"),path=run.get("path"),
                     run_attempt=run.get("run_attempt"),log_access_error_codes=errors,
                     research_started_at=names.get("daily-research",{}).get("started_at"),
                     publisher_completed_at=names.get("persist-google-drive",{}).get("completed_at"))
        out.append(proof)
    return out


def snapshot_identity(archive,pin,anchor,day,source,calendar):
    blob,manifest,payload=verified_zip(archive,pin)
    _,_,original=verified_zip(anchor,ANCHOR_SHA)
    verify_ancestry(original,payload)
    name=PREFIX+day+".json"
    if name not in payload:
        raise ValueError("ORIGINAL_SESSION_SNAPSHOT_MISSING")
    signals,settled,days=journal_index(payload,manifest["data_expected_last_closed_xnys"])
    module=load_attestation(source)
    with ZipFile(io.BytesIO(blob)) as z:
        proof=module.verify_archive_prospective_seals(z,z.namelist(),[day])
    if proof.get("prospective_seals_attested")!=1:
        raise ValueError("ORIGINAL_FIRST_SEAL_NOT_ATTESTED")
    for key,signal in signals.items():
        if key[0]==day:
            verify_timing(calendar,day,manifest["data_expected_last_closed_xnys"],
                          signal,settled.get(key))
    if day not in days:
        raise ValueError("ORIGINAL_SIGNAL_SESSION_MISSING")
    snap=json.loads(payload[name])
    return {"session":day,"source_run":int(snap["source_actions_run_id"]),
            "source_sha":snap["source_sha"],"snapshot_sha256":sha(payload[name])}


def main():
    import exchange_calendars as xc
    parser=argparse.ArgumentParser()
    parser.add_argument("--rehearse-known-failure",action="store_true")
    parser.add_argument("--session")
    parser.add_argument("--archive")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--anchor")
    parser.add_argument("--original-source",required=True)
    parser.add_argument("--out",required=True)
    a=parser.parse_args()
    cal=xc.get_calendar("XNYS",start="2026-01-01",end="2028-02-01")
    token=os.environ.get("GH_TOKEN","")
    if not token:
        raise ValueError("READ_ONLY_ACTIONS_TOKEN_REQUIRED")
    if a.rehearse_known_failure:
        identity=REHEARSAL
    else:
        if not all((a.session,a.archive,a.expected_sha256,a.anchor)):
            raise ValueError("ORIGINAL_ARCHIVE_AND_SESSION_REQUIRED")
        if registration_status(cal,a.session)!="IN_REGISTERED_WINDOW":
            raise ValueError("SESSION_OUTSIDE_REGISTERED_WINDOW")
        identity=snapshot_identity(a.archive,a.expected_sha256,a.anchor,a.session,a.original_source,cal)
    report=audit_pair(identity,collect(identity["session"],a.original_source,token),cal)
    report["historical_rehearsal"]=a.rehearse_known_failure
    if a.rehearse_known_failure:
        required={"FIRST_NOT_ORIGINAL_CAPTURE","FIRST_INPUTS_CHANGED_OR_UNKNOWN",
                  "REPLAY_CODE_SHA_MISMATCH","REPLAY_NOT_PREOPEN_SCHEDULED_CAPTURE"}
        if (report["scheduled_evidence_status"]!="HOLD" or report["run_count"]!=2
                or report["first_run"]!=45398233974 or report["replay_run"]!=45423471061
                or not required.issubset(report["problem_codes"])
                or any("RUN_OR_JOB_UNVERIFIED" in x for x in report["problem_codes"])):
            raise ValueError("KNOWN_HISTORICAL_FAILURE_NOT_INDEPENDENTLY_REPRODUCED")
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print(json.dumps(report,allow_nan=False))
    # Known failure is expected; a live-session HOLD remains a failing check.
    return 0 if a.rehearse_known_failure or report["scheduled_evidence_status"]=="PASS" else 2


if __name__=="__main__":
    raise SystemExit(main())
