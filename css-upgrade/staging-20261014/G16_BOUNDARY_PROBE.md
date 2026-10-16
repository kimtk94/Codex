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
