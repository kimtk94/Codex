# G16 synthetic container boundary — 2026-10-16

**Status: PARTIAL G16 evidence. G16 remains BLOCKED; G12 has not run. No production deployment.**

## Scope
The standalone GitHub Actions workflow `novogene-css-g16-boundary-probe.yml` exercises a **public, synthetic-only Python fixture** under a disposable Docker container. It does not download, import, execute, or package the proprietary CSS dashboard or mail collector. It connects to no SSH host and receives no company credentials.

The job provides only:
- `--network none`, tested using a UDP route probe to the reserved TEST-NET-2 IP (no packet transmission)
- `--read-only` root filesystem, with an explicit read-only source bind mount
- `--cap-drop ALL`, `--security-opt no-new-privileges`, non-root UID/GID
- bounded CPU/memory/process limits and a disposable tmpfs
- explicit fail-closed assertions for unexpected production secret environment variables, mounted production paths, network routes, write permission to protected locations
- no user mail, customer records, confidential source, database, actual Sheets ID, or keys in CI logs

**The boundary is a demonstration, not a complete runtime integration.**
The probe does not verify interception of each SQL/Google Sheets/mail/CRM/Drive caller in CSS. Docker `--network none` and read-only mounts must be carried forward unchanged or strengthened when a private full-engine fixture is built. The absence of a production path under this specific container does not prove that every path in the real engine is isolated.

## CI evidence
- Synthetic boundary workflow: https://github.com/kimtk94/Codex/actions/workflows/novogene-css-g16-boundary-probe.yml
- Source-level risk inventory: https://github.com/kimtk94/Codex/actions/runs/38637952229 (attempt 2)
- Import and unsafe `main()` fail-closed gate: https://github.com/kimtk94/Codex/actions/runs/38638533644 (attempt 2)
- Issue #167: https://github.com/kimtk94/Codex/issues/167

## Next implementation gates

1. Move the proprietary source and any realistic database fixtures to a **private** execution environment, not this public repo or the public Actions log.
2. Build a path and adapter inventory covering all direct/indirect sinks and exception-handler writes; reject unknown operations.
3. Use disposable synthetic mail/CRM inputs and prevent importing the collector's import-time side effects.
4. Use a namespaced no-network container with only fixture files mounted; preflight rejects production paths, tokens and identifiers.
5. Run the staged full engine exclusively against synthetic/cloned non-sensitive DBs and fake Sheets/mail/CRM adapters in that namespace. On errors, verify all outputs remain inside the sandbox.
6. Verify first run, no-op repeat, manual control replay, SIF Prepayment and QC transition, collisions, backups/logs and failure paths; compare deterministic results.
7. Report a minimal redacted CI artifact; still require **explicit** approval for the production patch and migration.

**Prohibited for this phase:** production CSS `main()` execution, importing the live collector, service changes, scheduled job changes, real customer data export, public code dump, live Google Sheet or SQLite writes, mail sends, backup deletion and production deployment.

## Synthetic adapter integration milestone (2026-10-16)

The companion `g16_synthetic_pipeline.py` implements a **model**, not the production CSS engine:
- An in-container throwaway SQLite database under `/tmp` stores TEST-prefixed projects, synthetic mail ledger keys, per-sample timeline events and manual/auto snooze state.
- `FakeMail` emits static `test:` UIDs and `synthetic:` Message IDs only; `FakeCRM` returns static synthetic inquiries; `FakeSheets` holds results in memory, with a deterministic injected failure before write.
- The synthetic model suppresses only a generic SIF follow-up during Prepayment SIF stages while retaining portfolio rows and independent CRM inquiries.
- Sample IDs deduplicate events even if Message IDs are absent or separate UID records refer to the same sample.
- Manual Hold/Skip supersedes automatic Prepayment snooze; QC advancement releases only automatic snoozes.
- Transaction rollback is tested for a **fake sheet failure before it applies any output** and an orphan project FK failure.
- Reusing a UID for a conflicting project/message fails closed.

`test_g16_synthetic_pipeline.py` runs these lifecycle cases inside the existing network-disabled, read-only Docker CI, using a disposable `/tmp` SQLite file and **no SSH, customer data, live API credentials or production module imports**.

### Known limits / next milestones
1. This synthetic model does not execute even an isolated AST extraction of the actual CSS source. It demonstrates desired invariants and is **not proof of the production implementation**.
2. The memory-based fake Sheet does not demonstrate real Google Sheets/SQLite distributed transaction atomicity. No automatic rollback can be claimed if real Sheets commits and SQLite later fails, or vice versa.
3. OS network and write boundaries are verified for this specific minimal container configuration, not for every production helper reachable by the full engine.
4. Full G16 sink coverage, G12 full-engine integration, operational deployment, and migration gates all remain blocked until a private production-equivalent isolated harness is complete.

## Strict mock ports integration (2026-10-16)

- Synthetic-only adapter module: `g16_mock_ports.py`; regression suite: `test_g16_mock_ports.py`.
- A factory injects a **guarded temporary SQLite connection** into the synthetic fixture engine. Allowed SQL is deliberately narrow and explicitly rejects external attach/export/DDL mutation beyond the fixture bootstrap.
- Fake Sheets permits publication of `TEST-` portfolio/action records only. Fake Mail and CRM return synthetic fixtures only; missing/unknown adapter methods fail closed.
- Fake filesystem output writes aggregate numeric/boolean metrics to a disposable `/tmp` directory only; path traversal, symlink targets, and string payload export are rejected.
- A method-count ledger contains only adapter category and operation names, never raw SQL, mail subjects, customer IDs or credentials.
- Container-level `--network none`, readonly filesystem, non-root UID and no capabilities remain required. **Python objects and their private attributes are not a security sandbox.**
- Latest CI: https://github.com/kimtk94/Codex/actions/runs/38892621133 — 15 synthetic pipeline + nine AST scanner + 16 adapter tests PASS (40 total).

**Explicit limitations:** fake Sheets uses in-memory state; rollback is tested only before its publish operation mutates output, not cross-service atomicity after a real API commit. The SQLite adapter exposes an actual fixture connection internally. These adapters have **not** been injected into proprietary CSS source, and they do not cover unregistered direct network/client/file construction in the real engine. G16 remains BLOCKED and G12 has not run. A private OS-isolated runtime and explicit connector interception are required before production-equivalent execution.
