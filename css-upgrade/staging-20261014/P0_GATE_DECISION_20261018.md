# P0 CSS isolation gate — evidence-based release decision (2026-10-18)

**Decision: NO-GO for live deployment or full CSS `main()` execution.**

## Independently established
- OS Docker isolation negative controls were successful in GitHub Actions [run 39051111730](https://github.com/kimtk94/Codex/actions/runs/39051111730). Container had no network, a read-only root and no mounted production source/database. This was *not* real CSS integration.
- Local environment executed saved synthetic adapter and source-admission test copies with PASS strings, but these copies alone do not attest to the latest commit, CI success, or Docker sandbox success.
- Source-admission and synthetic adapter contracts are committed in the staging branch. The combined P0 workflow now also calls the preexisting isolation-policy regression and the selected-function static admission selftest.

## Remaining independent evidence required before advancement
1. Provide the **actual workflow run ID and successful job logs** for `novogene-css-p0-synthetic-gate.yml`; a push commit is not itself a successful run.
2. Validate server-side production CSS source SHA-256 against the expected `a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840` **without transferring the raw source to GitHub**.
3. For selected real-function tests, only use SHA-verified source in disposable sandbox and synthetic databases. No production credentials, no outbound network, no production mounts.
4. Verify a meaningful oracle: Prepayment SIF attention suppression; portfolio visibility; manual Hold/Skip preservation; QC stage re-entry; idempotence; independent Action Center/Review tasks; zero send/Sheet writes to production.
5. Maintain full-main NO-GO until every direct and indirect effect sink is isolated and egress-restricted and a separate full-engine approval gate passes.

## Operational guardrails
- Do not merge PR #163 automatically or deploy staging patch bundle based on unit-test success alone.
- Do not change live CSS sources, production SQLite, Sheets, mail delivery, service timers or secrets.
- New tests must distinguish **unit / synthetic contract**, **selected real function**, **full CSS main**, and **production rollout** evidence.
- Failure/unknown => FAIL-CLOSED. CI logs, not assertions in markdown, determine PASS.
