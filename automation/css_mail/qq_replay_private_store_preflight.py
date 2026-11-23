#!/usr/bin/env python3
"""Fail-closed, read-only readiness check for a future PRIVATE QQ receipt store.

This file never writes GitHub, Sheets, email, receipts, or approval decisions.
In particular a private GitHub repository alone does not imply Google Sheets
atomicity, an independently authenticated approval, or authorization to
execute real-world financial writes.

The connected Codex repo is PUBLIC. Real invoice values, IDs, hashes, HMAC
secrets, approver names or journal entries MUST NEVER be committed there.
"""
import json
import os
import re
from urllib import error, request

EXPECTED_OWNER = "kimtk94"
PUBLIC_SOURCE_REPO = "Codex"
REPO_PATTERN = re.compile(r"([A-Za-z0-9-]{1,39})/([A-Za-z0-9_.-]{1,100})\Z")


def _hold(reason_code, metadata_ok=False):
    """Only fixed aggregate keys/codes, safe for public GitHub logs."""
    return {
        "status": "HOLD",
        "reason_code": reason_code,
        "private_repo_metadata_verified": int(metadata_ok),
        "dedicated_owner_verified": int(metadata_ok),
        "repository_write_access_verified": 0,
        "independent_case_approvals_verified": 0,
        "external_writer_exclusion_verified": 0,
        "durable_real_receipts_verified": 0,
        "cross_system_atomicity_verified": 0,
        "qq_stage_writes": 0,
        "qq_cursor_writes": 0,
        "qq_canonical_writes": 0,
        "can_execute_replay": False,
    }


def check_private_repository(metadata, repo_path):
    """Conservative metadata validator; success still means HOLD for writes.

    The repository should be private, dedicated to this sales receipt use,
    non-fork, owned by the expected user and active. No repo identifiers or
    metadata are returned or logged. No API permissions inference.
    """
    match = REPO_PATTERN.fullmatch(repo_path or "")
    if not match or match.group(1) != EXPECTED_OWNER:
        return _hold("PRIVATE_REPO_OWNER_OR_NAME_INVALID")
    name = match.group(2)
    if name.lower() == PUBLIC_SOURCE_REPO.lower() or name.startswith("."):
        return _hold("PRIVATE_REPO_NOT_DEDICATED")
    if not isinstance(metadata, dict):
        return _hold("PRIVATE_REPO_METADATA_INVALID")
    owner = metadata.get("owner")
    if not isinstance(owner, dict) or owner.get("login") != EXPECTED_OWNER:
        return _hold("PRIVATE_REPO_OWNER_MISMATCH")
    if metadata.get("full_name") != repo_path:
        return _hold("PRIVATE_REPO_IDENTITY_MISMATCH")
    if metadata.get("private") is not True or metadata.get("visibility") != "private":
        return _hold("PRIVATE_REPO_NOT_PRIVATE")
    if metadata.get("fork") is not False:
        return _hold("PRIVATE_REPO_FORK_OR_UNKNOWN")
    if metadata.get("archived") is not False or metadata.get("disabled") is not False:
        return _hold("PRIVATE_REPO_ARCHIVED_DISABLED_OR_UNKNOWN")
    if not isinstance(metadata.get("id"), int) or metadata["id"] <= 0:
        return _hold("PRIVATE_REPO_STABLE_ID_INVALID")
    return _hold("PRIVATE_METADATA_OK_NO_EXECUTION_AUTHORITY", metadata_ok=True)


class _RejectRedirects(request.HTTPRedirectHandler):
    """Do not forward a private-repo bearer token through HTTP redirects."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _read_metadata(repo_path, token, opener=None):
    """GitHub GET only. Never echoes credentials or private repo identifiers."""
    match = REPO_PATTERN.fullmatch(repo_path or "")
    if not match or match.group(1) != EXPECTED_OWNER:
        return None
    # urllib normally follows redirects; block them so the private token
    # cannot be forwarded if a response points at an unexpected host.
    opener = opener or request.build_opener(_RejectRedirects()).open
    uri = "https://api.github.com/repos/" + match.group(1) + "/" + match.group(2)
    req = request.Request(uri, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "qq-private-journal-readonly-preflight",
    }, method="GET")
    with opener(req, timeout=15) as response:
        return json.load(response)


def main():
    repo_path = os.environ.get("QQ_REPLAY_PRIVATE_JOURNAL_REPO", "").strip()
    token = os.environ.get("QQ_REPLAY_PRIVATE_JOURNAL_READ_TOKEN", "").strip()
    if not repo_path or not token:
        result = _hold("PRIVATE_JOURNAL_READER_NOT_CONFIGURED")
    else:
        try:
            metadata = _read_metadata(repo_path, token)
            result = check_private_repository(metadata, repo_path)
        except (OSError, ValueError, TypeError, KeyError, TimeoutError):
            result = _hold("PRIVATE_JOURNAL_METADATA_UNAVAILABLE")
        except Exception:
            # Fail closed without printing HTTP payload, headers or token.
            result = _hold("PRIVATE_JOURNAL_METADATA_UNAVAILABLE")
    print("QQ_PRIVATE_JOURNAL_PREFLIGHT=" + json.dumps(result, sort_keys=True))
    # Successful execution means audit ran, not that financial writes were approved.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
