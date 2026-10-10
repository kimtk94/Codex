#!/usr/bin/env python3
"""Atomic, fail-closed root deployment for -2% LIVE flip trigger + 2m READ-ONLY check.

No changes to trade execution watcher, buy schedule or strategy model.
Never reads/prints secrets to stdout; backs up the complete env in root-only dir.
Use --check for source-only validation, --apply under root for production.
"""
from __future__ import annotations

import argparse
import fcntl
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
from datetime import datetime, timezone


APP = Path("/opt/kalman/app")
ENV = Path("/opt/kalman/.env")
CRON = Path("/etc/cron.d/kalman")
STATE = Path("/opt/kalman/state")
ROOT = Path(__file__).resolve().parent
MONITOR = ROOT / "fast_profit_flip_check.py"
INSTALLED_MONITOR = APP / "scripts" / "fast_profit_flip_check.py"
CRON_MONITOR = (
    "*/2 9-23 * * 1-5 root bash -c 'cd /opt/kalman/app && "
    "flock -n /opt/kalman/state/fast-profit-flip-monitor.lock "
    "env PYTHONPATH=/opt/kalman/app KALMAN_ENV_FILE=/opt/kalman/.env "
    "/opt/kalman/.venv/bin/python scripts/fast_profit_flip_check.py' "
    ">> /opt/kalman/logs/fast-profit-flip-check.log 2>&1\n"
    "*/2 0-5 * * 2-6 root bash -c 'cd /opt/kalman/app && "
    "flock -n /opt/kalman/state/fast-profit-flip-monitor.lock "
    "env PYTHONPATH=/opt/kalman/app KALMAN_ENV_FILE=/opt/kalman/.env "
    "/opt/kalman/.venv/bin/python scripts/fast_profit_flip_check.py' "
    ">> /opt/kalman/logs/fast-profit-flip-check.log 2>&1\n"
)
# Source cron currently has a 30-minute daytime watcher. Keep it intact;
# 2-minute check is additive, as it is strictly read-only and makes no orders.
MARKER = "# KALMAN_FAST_PROFIT_FLIP_CHECK_ONLY_2MIN_V1"
FAST_BEGIN = MARKER + "\n"
FAST_END = "# KALMAN_FAST_PROFIT_FLIP_CHECK_ONLY_END\n"


def get_values(content: str) -> dict[str,str]:
    values={}
    for line in content.splitlines():
        item=line.strip()
        if item.startswith("#") or "=" not in item:
            continue
        k,v=item.split("=",1)
        if k.startswith("AUTO_TRADE_") or k=="TRADING_STATE_DB":
            if k in values:
                raise ValueError("Duplicate config key: "+k)
            values[k]=v.strip().strip("'").strip('"')
    return values


def expected_policy(contents: str) -> None:
    v=get_values(contents)
    expected={
        "AUTO_TRADE_PROFIT_FLIP_GUARD_ENABLED":"true",
        "AUTO_TRADE_PROFIT_FLIP_ARM_PCT":"0.002",
        "AUTO_TRADE_PROFIT_FLIP_CONFIRM_OBSERVATIONS":"2",
        "AUTO_TRADE_PROFIT_FLIP_RECOVERY_PCT":"0",
        "AUTO_TRADE_STOP_LOSS_PCT":"-0.03",
        "AUTO_TRADE_FRIDAY_FLAT_ENABLED":"true",
    }
    for k,val in expected.items():
        if v.get(k) != val:
            raise ValueError(f"Unsafe current guard contract: {k} expected {val}, got {v.get(k,'ABSENT')}")
    old=v.get("AUTO_TRADE_PROFIT_FLIP_TRIGGER_PCT","-0.002")
    if old not in ("-0.002","-0.02"):
        raise ValueError("Unexpected existing flip threshold; no change applied")


def update_env(contents: str) -> str:
    expected_policy(contents)
    pattern=r"(?m)^(AUTO_TRADE_PROFIT_FLIP_TRIGGER_PCT=)[^\n]*$"
    matches=list(re.finditer(pattern,contents))
    if len(matches)>1:
        raise ValueError("Duplicate trigger keys")
    if len(matches)==1:
        new=re.sub(pattern,r"\g<1>-0.02",contents)
    else:
        new=contents.rstrip("\n")+"\nAUTO_TRADE_PROFIT_FLIP_TRIGGER_PCT=-0.02\n"
    expected_policy(new)
    assert get_values(new)["AUTO_TRADE_PROFIT_FLIP_TRIGGER_PCT"]=="-0.02"
    return new


def update_cron(contents: str) -> str:
    if "CRON_TZ=Asia/Seoul" not in contents:
        raise ValueError("Cron timezone contract not recognized")
    if MARKER in contents:
        if contents.count(MARKER)!=1 or contents.count(FAST_END.strip())!=1:
            raise ValueError("Duplicate/incomplete fast cron block")
        begin=contents.index(MARKER)
        end=contents.index(FAST_END.strip(),begin)+len(FAST_END.strip())
        return contents[:begin]+(FAST_BEGIN+CRON_MONITOR+FAST_END).rstrip("\n")+contents[end:]
    if "run_position_watch.sh" not in contents or "run_us_market_clock.sh execution" not in contents:
        raise ValueError("Expected LIVE cron schedules not found")
    return contents.rstrip("\n")+"\n\n"+FAST_BEGIN+CRON_MONITOR+FAST_END


def atomic_replace(path: Path, contents: bytes) -> None:
    before=path.stat() if path.exists() else None
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as h:
        temp=Path(h.name)
        h.write(contents)
        h.flush()
        os.fsync(h.fileno())
    try:
        os.chmod(temp,stat.S_IMODE(before.st_mode) if before else 0o755)
        if before is not None:
            os.chown(temp,before.st_uid,before.st_gid)
        os.replace(temp,path)
    finally:
        temp.unlink(missing_ok=True)


def assert_no_old_pending(env_contents: str) -> None:
    conf=get_values(env_contents)
    db=Path(conf.get("TRADING_STATE_DB","/opt/kalman/state/trading.sqlite3"))
    if not db.is_file():
        raise RuntimeError("Live SQLite trading state unavailable; refuse policy change")
    connection=sqlite3.connect(f"file:{db.as_posix()}?mode=ro",uri=True,timeout=3)
    try:
        columns={str(x[1]) for x in connection.execute("PRAGMA table_info(managed_position)")}
        if not {"state","exit_pending_reason"}.issubset(columns):
            raise RuntimeError("Cannot inspect outstanding flip exits")
        count=connection.execute(
            """SELECT COUNT(*) FROM managed_position
            WHERE state IN ('OPEN','EXIT_RESERVED','EXIT_SUBMITTED')
              AND exit_pending_reason='PROFIT_TO_LOSS_FLIP'"""
        ).fetchone()[0]
        if count:
            raise RuntimeError(f"{count} old-threshold pending profit-flip exit(s): review manually")
    finally:
        connection.close()


def main() -> int:
    arg=argparse.ArgumentParser()
    arg.add_argument("--apply",action="store_true",help="install only as root")
    args=arg.parse_args()
    if not MONITOR.is_file():
        raise RuntimeError("Missing reference monitor code")
    import ast
    ast.parse(MONITOR.read_text())
    # Dry-run source contract without needing root access.
    demo=(
        "AUTO_TRADE_PROFIT_FLIP_GUARD_ENABLED=true\n"
        "AUTO_TRADE_PROFIT_FLIP_ARM_PCT=0.002\n"
        "AUTO_TRADE_PROFIT_FLIP_TRIGGER_PCT=-0.002\n"
        "AUTO_TRADE_PROFIT_FLIP_CONFIRM_OBSERVATIONS=2\n"
        "AUTO_TRADE_PROFIT_FLIP_RECOVERY_PCT=0\n"
        "AUTO_TRADE_STOP_LOSS_PCT=-0.03\n"
        "AUTO_TRADE_FRIDAY_FLAT_ENABLED=true\n")
    assert update_env(demo).count("AUTO_TRADE_PROFIT_FLIP_TRIGGER_PCT=-0.02")==1
    assert update_cron("CRON_TZ=Asia/Seoul\nrun_position_watch.sh\nrun_us_market_clock.sh execution\n").count(MARKER)==1
    if not args.apply:
        print("SOURCE_CHECK_OK prospective -2.0pct + 2minute READ_ONLY check. LIVE_UNCHANGED")
        return 0
    if os.geteuid()!=0:
        raise PermissionError("Root required for production installation")
    if not (ENV.is_file() and CRON.is_file() and APP.is_dir() and STATE.is_dir()):
        raise RuntimeError("Production paths missing; fail closed")
    # Always maintain same lock ordering as US execution, do not change while
    # another trading/model process holds either lock.
    locks=[]
    for name in ("us-cycle.lock","auto-trade.lock"):
        h=open(STATE/name,"a")
        try:
            fcntl.flock(h.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(f"{name} busy; retry when no LIVE process is active")
        locks.append(h)
    old_env=ENV.read_bytes()
    old_cron=CRON.read_bytes()
    old_monitor=INSTALLED_MONITOR.read_bytes() if INSTALLED_MONITOR.is_file() else None
    env_text=old_env.decode("utf-8")
    cron_text=old_cron.decode("utf-8")
    new_env=update_env(env_text)
    new_cron=update_cron(cron_text)
    assert_no_old_pending(env_text)
    backup=STATE/("flip-minus2-fast-monitor-backup-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    backup.mkdir(mode=0o700)
    shutil.copy2(ENV,backup/"kalman.env.before")
    shutil.copy2(CRON,backup/"kalman.cron.before")
    if old_monitor is not None:
        shutil.copy2(INSTALLED_MONITOR,backup/"fast_profit_flip_check.before.py")
    changed=[]
    try:
        atomic_replace(INSTALLED_MONITOR,MONITOR.read_bytes()); changed.append("monitor")
        atomic_replace(CRON,new_cron.encode("utf-8")); changed.append("cron")
        atomic_replace(ENV,new_env.encode("utf-8")); changed.append("env")
        if get_values(ENV.read_text())["AUTO_TRADE_PROFIT_FLIP_TRIGGER_PCT"]!="-0.02":
            raise RuntimeError("Live threshold validation failed")
        if CRON_MONITOR not in CRON.read_text():
            raise RuntimeError("Fast read-only monitor cron validation failed")
        # Cron daemon monitors /etc/cron.d changes automatically; no service restart.
        print(f"APPLIED flip=-0.0200, fast_read_only=2min, unchanged_execution=5min, backup={backup}")
        print("WARNING: Existing pending exits are not migrated; found none pre-apply")
        return 0
    except Exception:
        if "env" in changed: atomic_replace(ENV,old_env)
        if "cron" in changed: atomic_replace(CRON,old_cron)
        if "monitor" in changed:
            if old_monitor is None: INSTALLED_MONITOR.unlink(missing_ok=True)
            else: atomic_replace(INSTALLED_MONITOR,old_monitor)
        raise


if __name__=="__main__":
    try: sys.exit(main())
    except Exception as exc:
        print("INSTALL_NOT_APPLIED_OR_ROLLED_BACK: "+type(exc).__name__+": "+str(exc),file=sys.stderr)
        sys.exit(2)
