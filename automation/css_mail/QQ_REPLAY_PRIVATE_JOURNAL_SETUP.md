# QQ 2026: private journal provisioning gate (NO live replay)

**Status: HOLD.** This public `Codex` repository contains synthetic tests and the read-only journal metadata preflight only. **Never add original invoice numbers, source files, amounts, UIDVALIDITY, client identifiers, HMAC keys, case approval records, signed receipts, or live journal snapshots to this repository, its Actions logs, caches, commits, artifacts, comments, or issues.**

## Required separate resource

A repository owner must first create a **new dedicated private repository**, owned by `kimtk94`, reserved for sales tax-invoice attempt/receipt evidence (do not repurpose the private research or investment repositories). Verify GitHub marks it **Private**, with collaborators limited to explicitly authorized principals and no public mirrors. Empty repo setup is fine; do **not** populate it with actual invoices.

The current tool connection cannot create this repository. Create the dedicated private repository through GitHub's **New repository** UI, using a purpose-specific name; the audit deliberately does not assume a chosen repo name.

A separate, owner-approved step may later provision a **fine-grained read-only token** limited to that private repo for repository metadata verification. Configure the following *as GitHub environment secrets*, not source variables, in the existing `TaehoonServer` environment:

- `QQ_REPLAY_PRIVATE_JOURNAL_REPO`: the exact `kimtk94/<private-repo-name>` string
- `QQ_REPLAY_PRIVATE_JOURNAL_READ_TOKEN`: fine-grained **metadata read-only** token for that one private repository

The read-only preflight makes **one GitHub GET request** to repository metadata and publishes only fixed status/counter fields. Its success does **not** mean storage write rights, immutable receipts, user authorization or any transaction atomicity were verified. The job always reports `status=HOLD` and cannot issue writes.

## Before *any* actual stage-only replay

1. Independently authenticate the user and obtain **explicit individual case approvals** (7 initially `NOT_REQUESTED`). The private review spreadsheet's choices alone are not authenticated authorization.
2. Review all Google Sheets writers, including direct API clients and service accounts. CI concurrency does **not** exclude other writers. Design and test an exclusive writer boundary.
3. Design a durable **PREPARED attempt before Sheets PUT**, uniqueness and CAS semantics in the private store, and irreversible `WRITE_UNKNOWN` hold if any response is lost; no automatic retry after uncertain results.
4. Design an exact 11-field post-save readback, separately authenticated execution receipt, and timeout/identity drift behavior. Git ref CAS alone is **not** atomic with Sheets.
5. Have the actual Stage-only writer undergo a **separately reviewed PR and explicit user approval**. Keep `qq_historical_invoice_backfill_2026_safe.py` and `qq_historical_invoice_backfill.py` 2026 APPLY hard-blocked and PREVIEW readonly until then.
6. Never update CSS canonical Invoice, Revenue, Payment, SFDC or client mail from this Stage-only flow without an entirely separate authorization.

Preflight statuses:
- `PRIVATE_JOURNAL_READER_NOT_CONFIGURED` — no secrets supplied, safe default
- `PRIVATE_REPO_NOT_PRIVATE` — rejects a public repo
- `PRIVATE_REPO_OWNER_OR_NAME_INVALID` — wrong owner or invalid reference
- `PRIVATE_METADATA_OK_NO_EXECUTION_AUTHORITY` — private metadata checked but **no writer authorization**
- `PRIVATE_JOURNAL_METADATA_UNAVAILABLE` — no access, credentials, or network; stays HOLD

Track evidence and changes at [QQ Replay issue #942](https://github.com/kimtk94/Codex/issues/942) **without identifiers or private values**.
