#!/usr/bin/env python3
"""Content-addressed preservation of actual Nasdaq Trader symbol-directory bytes.

The prior snapshot_journal.jsonl is a SHA256 hash chain of observed source
digests. This module restores every raw directory body available from the prior
pinned Drive ZIP and persists it alongside the current run. Legacy archives
with only raw/<source>.txt are bootstrapped if the bytes match the latest journal
event. Unrecoverable older digests remain explicitly HOLD, not invented.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re
from zipfile import ZipFile

SOURCES = ("nasdaqlisted", "otherlisted")
PRIOR_RAW_ROOT = "research/official_directory/raw/"
PRIOR_HISTORY_ROOT = "research/official_directory/history/"
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_ONE_SOURCE_BYTES = 4_000_000
MAX_FULL_SOURCE_HISTORY_BYTES = 120_000_000


def member_for(source, digest):
    if source not in SOURCES or not isinstance(digest, str) or not SHA_RE.fullmatch(digest):
        raise ValueError("SOURCE_HISTORY_INVALID_SOURCE_OR_DIGEST")
    return f"{PRIOR_HISTORY_ROOT}{source}/{digest}.txt"


def _read_bounded_verified(archive, member, digest):
    """Verify decompressed bytes, not just ZIP CRC or file name."""
    with archive.open(member) as fh:
        data = fh.read(MAX_ONE_SOURCE_BYTES + 1)
    if not data or len(data) > MAX_ONE_SOURCE_BYTES:
        raise ValueError("SOURCE_HISTORY_BLOB_OVERSIZED_OR_EMPTY")
    if sha256(data).hexdigest() != digest:
        raise ValueError("SOURCE_HISTORY_BLOB_DIGEST_MISMATCH")
    return data


def _requirements(journal):
    expected = set()
    for event in journal:
        hashes = event.get("source_sha256")
        if not isinstance(hashes, dict) or set(hashes) != set(SOURCES):
            raise ValueError("SOURCE_HISTORY_JOURNAL_EXPECTS_BOTH_LISTS")
        for source, digest in hashes.items():
            member_for(source, digest)
            expected.add((source, digest))
    return expected


def preserve(prior_zip, journal, current_responses, out_dir):
    """Persist every available previously sealed full source plus new bytes.

    The hash-chain validity of journal must be checked by the caller first.
    An old missing file is a permanent *coverage gap*, never a fake file.
    Malformed/tampered present files cause failure before any new seal.
    """
    expected = _requirements(journal)
    bodies = {}
    recovered_legacy = 0
    prior_exists = prior_zip is not None and Path(prior_zip).is_file()
    if prior_exists:
        with ZipFile(prior_zip) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("SOURCE_HISTORY_DUPLICATE_ZIP_MEMBERS")
            available = set(names)
            for source, digest in sorted(expected):
                historic_path = member_for(source, digest)
                if historic_path in available:
                    bodies[(source, digest)] = _read_bounded_verified(
                        archive, historic_path, digest)
            # First deployment produced a verified hash journal plus only the
            # latest two raw files. Recover these before they are overwritten.
            if journal:
                for source, digest in journal[-1]["source_sha256"].items():
                    key = source, digest
                    raw_path = PRIOR_RAW_ROOT + source + ".txt"
                    if key not in bodies and raw_path in available:
                        bodies[key] = _read_bounded_verified(
                            archive, raw_path, digest)
                        recovered_legacy += 1
    if current_responses is not None:
        if not isinstance(current_responses, dict) or set(current_responses) != set(SOURCES):
            raise ValueError("SOURCE_HISTORY_CURRENT_RESPONSE_COVERAGE")
        for source, blob in current_responses.items():
            digest = sha256(blob).hexdigest()
            key = (source, digest)
            if key not in expected:
                raise ValueError("SOURCE_HISTORY_CURRENT_BYTES_NOT_SEALED")
            if not blob or len(blob) > MAX_ONE_SOURCE_BYTES:
                raise ValueError("SOURCE_HISTORY_CURRENT_BLOB_INVALID")
            if key in bodies and bodies[key] != blob:
                raise ValueError("SOURCE_HISTORY_CONTENT_ADDRESS_COLLISION")
            bodies[key] = blob

    raw_bytes = sum(len(data) for data in bodies.values())
    if raw_bytes > MAX_FULL_SOURCE_HISTORY_BYTES:
        raise ValueError("SOURCE_HISTORY_SIZE_BUDGET_EXCEEDED_NEEDS_ARCHIVE_ROLLOVER")
    missing = sorted(expected - set(bodies))
    history_dir = Path(out_dir) / "history"
    for source, digest in sorted(bodies):
        output = history_dir / source / (digest + ".txt")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(bodies[(source, digest)])
        if sha256(output.read_bytes()).hexdigest() != digest:
            raise ValueError("SOURCE_HISTORY_LOCAL_READBACK_DIGEST_MISMATCH")
    return {
        "status": ("FULL_SOURCE_BYTES_VERIFIED" if not missing
                   else "LEGACY_SOURCE_BYTES_MISSING_HOLD"),
        "history_schema": "daily20-directory-source-history-v1",
        "total_journal_source_digests": len(expected),
        "raw_source_blob_count": len(bodies),
        "legacy_source_blobs_recovered": recovered_legacy,
        "uncompressed_history_bytes": raw_bytes,
        "missing_historic_source_digests": [
            {"source": source, "sha256": digest} for source, digest in missing
        ],
        "all_journal_digests_attested_by_raw_bytes": not missing,
        "raw_body_history_preserved_in_pinned_drive_zip": True,
        "regular_close_or_point_in_time_listing_certified": False,
    }


def verify_results_zip(archive):
    """Independently verify every history body in a results ZIP.

    This has no pandas, yfinance, provider credentials, or market-data runtime
    dependency. The Drive post-upload readback must execute this on remote bytes.
    """
    report_path = "research/official_directory/report.json"
    journal_path = "research/official_directory/snapshot_journal.jsonl"
    members = archive.namelist()
    names = set(members)
    if report_path not in names:
        return {
            "status": "LEGACY_NO_DIRECTORY_HISTORY",
            "journal_event_count": 0, "source_blobs_verified": 0,
            "directory_source_history_complete": False,
        }
    if journal_path not in names:
        raise ValueError("SOURCE_HISTORY_READBACK_JOURNAL_MISSING")
    import json
    report = json.loads(archive.read(report_path))
    if (report.get("research_only") is not True
            or report.get("production_writes") is not False
            or report.get("strategy_promoted") is not False
            or report.get("finality_verified") != 0
            or report.get("source_snapshot_is_historical_asof_evidence") is not False):
        raise ValueError("SOURCE_HISTORY_READBACK_GOVERNANCE_INVALID")
    lines = [
        json.loads(line) for line in
        archive.read(journal_path).decode("utf-8").splitlines()
        if line.strip()
    ]
    prev = "0" * 64
    for seq, event in enumerate(lines, 1):
        payload = {k: v for k, v in event.items() if k != "hash"}
        import json
        canonical = json.dumps(payload, ensure_ascii=False,
                               sort_keys=True, separators=(",", ":")).encode()
        digest = sha256(canonical).hexdigest()
        if (event.get("seq") != seq
                or event.get("prev_hash") != prev
                or event.get("hash") != digest):
            raise ValueError("SOURCE_HISTORY_READBACK_CHAIN_TAMPERED")
        prev = digest
    journal = report.get("journal")
    if not isinstance(journal, dict) or (
            journal.get("journal_events") != len(lines)
            or journal.get("journal_tip_sha256") != (prev if lines else None)):
        raise ValueError("SOURCE_HISTORY_READBACK_JOURNAL_REPORT_MISMATCH")
    required = _requirements(lines)
    history = report.get("source_history")
    if not isinstance(history, dict):
        raise ValueError("SOURCE_HISTORY_READBACK_REPORT_ABSENT")
    observed = set()
    for source,digest in sorted(required):
        name = member_for(source,digest)
        if name not in names:
            raise ValueError("SOURCE_HISTORY_READBACK_BLOB_MISSING:" + source)
        _read_bounded_verified(archive,name,digest)
        observed.add(name)
    listed_history = {
        name for name in names if name.startswith(PRIOR_HISTORY_ROOT)
        and not name.endswith("/")
    }
    if listed_history != observed:
        raise ValueError("SOURCE_HISTORY_READBACK_UNTRACKED_BLOB")
    if (history.get("status") != "FULL_SOURCE_BYTES_VERIFIED"
            or history.get("all_journal_digests_attested_by_raw_bytes") is not True
            or history.get("raw_body_history_preserved_in_pinned_drive_zip") is not True
            or history.get("total_journal_source_digests") != len(required)
            or history.get("raw_source_blob_count") != len(observed)
            or history.get("missing_historic_source_digests") != []
            or journal.get("earlier_full_source_bytes_preserved") is not True):
        raise ValueError("SOURCE_HISTORY_READBACK_FALSE_COMPLETENESS_CLAIM")
    source_report = report.get("sources")
    if source_report is not None:
        if set(source_report) != set(SOURCES):
            raise ValueError("SOURCE_HISTORY_READBACK_CURRENT_SOURCE_REPORT_INCOMPLETE")
        for source, meta in source_report.items():
            digest = meta.get("sha256")
            if (source, digest) not in required:
                raise ValueError("SOURCE_HISTORY_READBACK_CURRENT_SOURCE_UNSEALED")
            raw_member = PRIOR_RAW_ROOT + source + ".txt"
            if raw_member not in names:
                raise ValueError("SOURCE_HISTORY_READBACK_CURRENT_SOURCE_RAW_MISSING")
            _read_bounded_verified(archive,raw_member,digest)
    return {
        "status": "FULL_DIRECTORY_SOURCE_HISTORY_VERIFIED",
        "journal_event_count": len(lines),
        "journal_tip_sha256": prev if lines else None,
        "source_blobs_verified": len(observed),
        "directory_source_history_complete": True,
        "historical_listing_asof_certified": False,
        "close_finality_verified": 0,
    }
