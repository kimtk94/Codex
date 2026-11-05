# Novogene CSS — Manual Hold / Skip vs New-Mail Ordering Audit (2026-10-15)

**Status: SIX-PATCH STAGING PASS / PRODUCTION NOT DEPLOYED**

## Why this was needed

Earlier regression coverage tested manual Hold/Skip and automatic Prepayment in an initial stable state, but did not prove safety when **new mail arrives during a cycle** or when the Overview control snapshot is replayed or changed after the auto-snooze's read.

The actual server CSS synchronization function bodies were extracted with AST from the SHA-verified runtime source. **No CSS main(), collector, production Google Sheet or operational SQLite was executed or modified.**

## Baseline reproductions (before patches 5/6)

[Baseline deterministic conflict run](https://github.com/kimtk94/Codex/actions/runs/38658920005)

- **Repeated Hold command extended expiration:** the same input processed one hour later moved `hold_until` ahead by one hour.
- **No-op automatic Prepayment Skip rewrote its updated timestamp:** even without mail/stage changes, `updated_at` changed on every cycle.
- **Read/write race overwrote later manual Hold:** a deterministic test inserted a manual mode after the auto-sync's initial SELECT but just before its UPSERT. The original unguarded upsert overwrote it.

These were real server function executions on synthetic in-memory SQLite, not production incidents.

## Narrow fixes

5. `novogene_sif_atomic_auto_skip.patch`: conditional SQLite UPSERT changes an existing `skip_prepayment` only if its mail marker actually changed, and **refuses to overwrite an existing manual mode at the database write point**. Auto-active count is re-read after the upsert, eliminating false counts under an injected interleaving.
6. `novogene_css_hold_replay_guard.patch`: when a Hold is already valid, an identical retransmitted Hold control action cannot repeatedly extend its expiration. An explicit Release followed by Hold still begins a new Hold.

These are in addition to the first four SIF/portfolio/customer metadata patches.

## Verified evidence

| Gate | Result | Evidence |
|---|---|---|
| Actual manual/automatic sync: new mail + manual Hold/Skip, stale UI marker, QC transition, read error, SAVEPOINT rollback and deterministic write race | **54/54 PASS** | [Run 38659219970](https://github.com/kimtk94/Codex/actions/runs/38659219970) |
| All six patches exact-server SHA, AST compile, existing 433 functions, read-only live SQLite quick/FK, byte-exact reverse of all six | **38/38 PASS** | [Run 38659378552](https://github.com/kimtk94/Codex/actions/runs/38659378552) |
| Large synthetic 1,200-project durable Skip, stage progression, Summary/Action branch, restore/retry, manual states and six-patch byte-exact rollback | **68/68 PASS** | [Run 38659601996](https://github.com/kimtk94/Codex/actions/runs/38659601996) |

Final six-patch staged source SHA-256:
`a75fac886bd4cb881acbd7a4cf860c7246f05a00b5d2a0dc461934cbfddce083`

Original production source SHA-256:
`a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840`

## Residual limitations

- The deterministic race injection runs against an isolated **single SQLite connection** and validates conditional UPSERT semantics. A true simultaneous two-process/connection timing stress test and systemd service interaction are **not** yet verified.
- The Hold replay guard only suppresses repeated commands **while the previous Hold is still valid**. After its expiration, a persistent old command cannot be distinguished from a new deliberate Hold without a unique user-action ID / one-shot input-clearing contract. Treat this as a separate UI concurrency hardening item.
- The control snapshot is read through a batch request and changes are guarded with a SQLite SAVEPOINT. That protects database atomicity on errors, **not** the consistency of a concurrent spreadsheet edit arriving after the batch-read. Before deployment, evaluate a post-write readback / optimistic version check for manual controls.
- This work exercises targeted actual functions. Full CSS main/collector/email/CRM/Drive end-to-end in OS-enforced isolation is still not tested.
- **Do not deploy, merge, delete backups or alter operational worksheets** from this draft until the owner approves release scope, schedule and rollback plan.
