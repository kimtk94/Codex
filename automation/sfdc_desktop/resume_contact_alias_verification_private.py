#!/usr/bin/env python3
"""Resume verified Korean Contact review in safe, private, read-only batches.

Only local authenticated Chrome UI and private workstation files.
No Salesforce writes, no CRM credentials in GitHub, no customer PII printed.
"""
import argparse
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

import live_contact_alias_batch_private as study
from build_private_contact_aliases import verified_private_aliases


def select_new_candidates(rows, previously_verified, previous_attempts, offset, limit, retry_holds=False):
    if not isinstance(rows, list) or not isinstance(previously_verified, set):
        raise ValueError("INVALID_CANDIDATES")
    todo = []
    for row in rows[offset:]:
        cid = row.get("contact_id")
        if not isinstance(cid, str) or cid in previously_verified:
            continue
        if not retry_holds and cid in previous_attempts:
            continue
        todo.append(row)
        if len(todo) == limit:
            break
    return todo


def private_json_write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".writing")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def run_batch(start, limit, retry_holds=False):
    root = study.ROOT.resolve()
    if not (0 <= start <= 10000 and 1 <= limit <= 10):
        raise ValueError("INVALID_BATCH_RANGE")
    evidence_path = root / "private_verified_contact_details_evidence.json"
    attempts_path = root / "contact_alias_attempts_PRIVATE.json"
    alias_path = root / "web_contact_aliases_PRIVATE.json"
    prior = json.loads(evidence_path.read_text(encoding="utf-8-sig")) if evidence_path.exists() else []
    attempts = json.loads(attempts_path.read_text(encoding="utf-8-sig")) if attempts_path.exists() else []
    if not isinstance(prior, list) or not isinstance(attempts, list):
        raise ValueError("PRIVATE_HISTORY_INVALID")
    checked_ids = {r.get("contact_id") for r in attempts if isinstance(r, dict)}
    validated_ids = {r.get("contact_id") for r in prior if isinstance(r, dict)}
    available = study.candidates()
    todo = select_new_candidates(available, validated_ids, checked_ids, start, limit, retry_holds)
    status_counts = {}
    if todo:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=16000)
            if len(browser.contexts) != 1:
                raise ValueError("HOLD_AUTHENTICATED_CONTEXT_NOT_UNIQUE")
            page = browser.contexts[0].new_page()
            try:
                for index, row in enumerate(todo, 1):
                    try:
                        result, status = study.inspect(page, row)
                    except Exception as exc:
                        result, status = None, "HOLD_" + type(exc).__name__
                    status_counts[status] = status_counts.get(status, 0) + 1
                    attempts.append({
                        "contact_id": row["contact_id"],
                        "opportunity_id": row["opportunity_id"],
                        "status": status,
                        "read_only": True,
                        "save_clicked": False
                    })
                    private_json_write(attempts_path, attempts)
                    if result is not None and status == "PASS_ALL_IDENTITY_CHECKS":
                        prior.append(result)
                        private_json_write(evidence_path, prior)
                    print("CONTACT_VERIFY", index, "/", len(todo), status, flush=True)
            finally:
                page.close()
    aliases = verified_private_aliases(prior)
    private_json_write(alias_path, aliases["records"])
    report = {
        "source_candidate_contacts": len(available),
        "batch_attempts": len(todo),
        "batch_pass": status_counts.get("PASS_ALL_IDENTITY_CHECKS", 0),
        "total_unique_verified": len(aliases["records"]),
        "total_logged_attempts": len(attempts),
        "hold_counts": {k: v for k, v in status_counts.items() if k != "PASS_ALL_IDENTITY_CHECKS"},
        "salesforce_save_count": 0,
        "customer_data_in_logs": False,
    }
    print("CONTACT_VERIFY_FINAL", json.dumps(report, sort_keys=True), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=10)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--retry-holds", action="store_true")
    args = parser.parse_args()
    run_batch(args.start, args.limit, args.retry_holds)


if __name__ == "__main__":
    main()
