#!/usr/bin/env python3
"""Bounded and resumable 2026 QQ->Feishu backfill catch-up.

One invocation can run up to six *sequential* 3000-mail batches. Each batch
re-fetches Feishu Mail Keys and excludes already ingested records. No parallel
IMAP sessions, outbound mail, external URL publishing or SFDC writes.
"""
import os
import sys
import qq_mail_ingest as q

def positive_env(name, default, cap):
    try:
        value=int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        raise q.SafeError("CATCHUP_INVALID_INTEGER_"+name)
    if value<1 or value>cap:
        raise q.SafeError("CATCHUP_LIMIT_OUT_OF_RANGE_"+name)
    return value

def drain(batch_runner=None):
    rounds=positive_env("QQ_CATCHUP_MAX_ROUNDS",6,6)
    batch_size=positive_env("FEISHU_MAIL_BACKFILL_TOTAL",3000,3000)
    if batch_runner is None:
        batch_runner=q.run
    os.environ["FEISHU_MAIL_BACKFILL_TOTAL"]=str(batch_size)
    total=0
    completed=0
    for n in range(1,rounds+1):
        print("CATCHUP_ROUND_START="+str(n)+"/"+str(rounds)+" limit="+str(batch_size),
              flush=True)
        result=batch_runner("backfill2026")
        if not isinstance(result,dict) or "added" not in result or "scanned" not in result:
            raise q.SafeError("CATCHUP_MISSING_VERIFIED_BATCH_COUNTS")
        added,scanned=result["added"],result["scanned"]
        if not isinstance(added,int) or not isinstance(scanned,int):
            raise q.SafeError("CATCHUP_NON_INTEGER_COUNTS")
        if not(0<=added<=scanned<=batch_size):
            raise q.SafeError("CATCHUP_INVALID_COUNTS")
        total+=added
        completed+=1
        print("CATCHUP_ROUND_PASS="+str(n)+" added="+str(added)+
              " scanned="+str(scanned)+" cumulative_added="+str(total),flush=True)
        if added==0:
            # Avoid endlessly scanning old 2025 and already-seen UID candidates.
            # 0 new records is no-progress, not proof of full 2026 coverage.
            print("CATCHUP_STOP_NO_NEW_MAIL=1 backlog_completeness=NOT_VERIFIED",flush=True)
            break
    print("CATCHUP_FINISHED rounds="+str(completed)+
          " added="+str(total)+" max_rounds="+str(rounds)+
          " all_2026_coverage=UNVERIFIED",flush=True)
    return {"rounds":completed,"added":total}

if __name__=="__main__":
    try:drain()
    except Exception as exc:
        reason=str(exc) if isinstance(exc,q.SafeError) else type(exc).__name__
        print("CATCHUP_FAILED="+reason,file=sys.stderr)
        sys.exit(1)
