#!/usr/bin/env python3
"""Bounded serial QQ MIME cache backfill within a single protected GitHub job.

Each existing web_body_sync.py iteration independently rechecks UIDVALIDITY,
message headers, previous rows and Google Sheets post-write parity. This
wrapper only repeats VERIFIED idempotent iterations, under the workflow's
existing shared QQ concurrency lock. No customer send or SFDC writes.

The total time budget reserves time for health publishing and job cleanup.
Never retries a failed iteration, an unverified/unsafe error, or a timeout.
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SCRIPT = Path(__file__).with_name("web_body_sync.py")
MAX_CYCLES = 3
TOTAL_BUDGET_SECONDS = 19 * 60
MIN_AVAILABLE_SECONDS = 180
ITERATION_TIMEOUT_SECONDS = 8 * 60
RESULT = re.compile(
    r"^CSS_WEB_BODY_SYNC_(PASS|PARTIAL)"
    r" selected=(\d+) eligible=(\d+)"
    r" fetched=(\d+).*? errors=(\d+)"
    r" error_types=([A-Z_,]*)$", re.M,
)
SAFE_LOG_PREFIXES = (
    "CSS_WEB_BACKFILL_STATUS ",
    "CSS_WEB_BODY_SYNC_PASS ",
    "CSS_WEB_BODY_SYNC_PARTIAL ",
)
KNOWN_NONFATAL = {"EMPTY_BODY"}


def summary_from_output(output):
    found = RESULT.findall(output)
    if len(found) != 1:
        raise ValueError("WEB_BODY_RESULT_SCHEMA_MISSING")
    state, selected, eligible, fetched, errors, raw_errors = found[0]
    types = set(filter(None, raw_errors.split(",")))
    if int(fetched) > int(selected) or int(selected) > int(eligible):
        raise ValueError("WEB_BODY_RESULT_COUNTS_INVALID")
    if int(errors) and not types:
        raise ValueError("WEB_BODY_ERROR_TYPES_MISSING")
    return {
        "state": state,
        "selected": int(selected),
        "eligible": int(eligible),
        "fetched": int(fetched),
        "errors": int(errors),
        "types": types,
    }


def execute(max_cycles=MAX_CYCLES, runner=subprocess.run, monotonic=time.monotonic):
    if not isinstance(max_cycles, int) or not 1 <= max_cycles <= MAX_CYCLES:
        raise ValueError("WEB_BODY_SERIAL_CYCLE_LIMIT_INVALID")
    start = monotonic()
    completed = 0
    while completed < max_cycles:
        remaining = TOTAL_BUDGET_SECONDS - (monotonic() - start)
        if remaining < MIN_AVAILABLE_SECONDS:
            print("CSS_WEB_SERIAL=TIME_BUDGET_STOP completed=" + str(completed), flush=True)
            return 0 if completed else 3
        timeout = max(1, min(ITERATION_TIMEOUT_SECONDS, int(remaining)))
        try:
            proc = runner(
                [sys.executable, str(SCRIPT)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            print("CSS_WEB_SERIAL=TIMEOUT_STOP cycle=" + str(completed + 1), flush=True)
            return 3
        # Never print captured source mail, identifiers, headers, or tracebacks.
        for line in str(proc.stdout or "").splitlines():
            if line.startswith(SAFE_LOG_PREFIXES):
                print(line, flush=True)
        if proc.returncode != 0:
            print("CSS_WEB_SERIAL=FAILED_STOP cycle=" + str(completed + 1) +
                  " exit=" + str(proc.returncode), flush=True)
            return 2
        try:
            status = summary_from_output(proc.stdout or "")
        except ValueError as exc:
            print("CSS_WEB_SERIAL=" + str(exc), flush=True)
            return 2
        completed += 1
        print("CSS_WEB_SERIAL=VERIFIED_CYCLE cycle=" + str(completed) +
              " selected=" + str(status["selected"]) +
              " eligible=" + str(status["eligible"]), flush=True)
        # Missing MIME text is explicitly labeled BODY_EMPTY_MIME in the
        # existing source script, so it is not an IMAP transport error.
        # Any other error requires investigation rather than repeat attempts.
        unexpected = status["types"] - KNOWN_NONFATAL
        if unexpected:
            print("CSS_WEB_SERIAL=UNSAFE_ERROR_STOP cycle=" + str(completed) +
                  " issue_count=" + str(len(unexpected)), flush=True)
            return 2
        if status["errors"] > 0 and status["state"] == "PASS":
            print("CSS_WEB_SERIAL=CONTRADICTORY_SUCCESS_STOP", flush=True)
            return 2
        if status["selected"] == 0 or status["eligible"] <= status["selected"]:
            print("CSS_WEB_SERIAL=ELIGIBLE_QUEUE_DRAINED completed=" +
                  str(completed), flush=True)
            return 0
    print("CSS_WEB_SERIAL=MAX_CYCLES_COMPLETED count=" + str(completed), flush=True)
    return 0


def main():
    try:
        cycles = int(os.getenv("CSS_WEB_BODY_SERIAL_CYCLES", "3"))
        code = execute(max_cycles=cycles)
    except (ValueError, TypeError):
        print("CSS_WEB_SERIAL=INVALID_CONFIGURATION", flush=True)
        return 2
    return code


if __name__ == "__main__":
    sys.exit(main())
