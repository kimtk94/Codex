# G12 CSS Sheets writer coverage baseline — 2026-10-17

**Verdict: STAGING CHECKS PASS / RELEASE REMAINS BLOCKED.** No operational CSS, database, mail, CRM, Google Sheet, cron or deployment modifications.

## Verified evidence

The live CSS source fingerprint remains `a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840`.

- [20/20 static AST regression assertions PASS](https://github.com/kimtk94/Codex/actions/runs/39025177832): 9 writer classifier + 11 context/alias tests.
- [Latest static G12 writer source inspection](https://github.com/kimtk94/Codex/actions/runs/39025200696) identified 28 candidate writer call sites: 8 destructive or full-frame candidates, 19 unknown-effect API candidates and 1 append candidate. 26 occur in helpers, 2 in `main()`.
- All four known operator-control tab titles occur as module constants. The `main()` 20921 `clear()` and 22107 `batch_update()` calls are **contextually associated** with a function referencing the known tabs, but neither is proven to write those tabs. A conservative worksheet-alias analyzer found **no syntactically resolved direct worksheet alias** for the 10 highlighted calls; this is an unresolved proof gap, not a negative finding.
- [Staging protection and coverage CI 36/36 PASS](https://github.com/kimtk94/Codex/actions/runs/39025321253): 11 range ownership tests + 13 synthetic gspread-shaped adapter tests + 12 new 28-site inventory freeze tests.

## New release-blocking inventory gate

`g12_writer_coverage_gate.py` records the exact 28 `(source line, observed API method, static risk category)` signatures from the source-SHA-pinned audit. It deliberately yields `BLOCKED_MISSING_WRITER_ISOLATION_EVIDENCE` even when the current baseline matches. A changed source fingerprint, altered or added write site, truncated report, fabricated SAFE status or malformed risk class also blocks.

This is an **accounting requirement**, not a deployment readiness proof. Any code refactor may naturally shift line numbers; if so, repeat SHA-pinned AST inventory and independently review the change rather than silently updating the baseline. The gate does not have production credentials, cannot change Sheets/SQLite, and intentionally cannot itself authorize a release.

## Priority write-site review (source lines are not durable IDs)

1. `main():20921 clear()` — examine receiver object and condition, discriminate system-owned scratch tabs from operator-owned four tabs. Never remove it or infer a target from same-function title references without review.
2. `helper():1871 batch_clear()`, `helper():1891 set_with_dataframe()` — verify full-row replacements, physical column masks, header/start-row behavior and exact caller-to-tab dataflow.
3. `helper():17648 set_with_dataframe()`, `helper():1673/2835/6453 resize()`, `helper():19275 sort()` — verify structural effects and whether user-entered checkbox/reason data can be dropped or reindexed.
4. All 19 unknown-effect APIs plus one append — resolve exact request destinations, field masks, record-key behavior, pagination and exception paths.

## Next acceptance contract

- Inspect actual private source call receivers, helper parameter binding and call graph in a source-protected environment; connect all relevant paths to a dedicated system-output surface that **never writes to operator input cells**.
- Prove row identity and manual-edit-after-snapshot handling in an actual isolated test-only Sheet; avoid assuming multiple reads create Sheets/SQLite CAS.
- Under G16 Bubblewrap no-network and no production credential mounts, run the **actual isolated writer function bodies** with synthetic fixtures and assert no bypass of the field-ownership policy.
- Run G12 complete patched CSS `main()` only after exhaustive G16 sink interception is demonstrated. Explicit rollout and rollback approval separate.

**Production deployment remains unauthorized; Draft PR #168 stays unmerged.**
