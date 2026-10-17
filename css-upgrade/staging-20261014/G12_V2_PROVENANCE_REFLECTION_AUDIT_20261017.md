# G12 V2 — receiver provenance and reflective call audit (2026-10-17)

**Decision: P0 ANALYSIS COMPLETE FOR THIS PASS / G12 STRICT RELEASE BLOCKED.**
No operational CSS source, Google Sheet, mailbox, CRM, SQLite database, schedule or service was modified. Actual CSS source SHA-256 `a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840` was read only in the private, no-network Bubblewrap sandbox; AST was parsed/compiled but the operational CSS module and `main()` were not executed.

## Verified changes

- Added staged, read-only `g12_v2_receiver_provenance.py` to distinguish multiple assignments, parameter-derived variables, nested/conditional bindings, literal containers, builtin-named constructors, direct function returns, and subscripts **without exporting original source, private identifiers, user data, or arbitrary literals**.
- Added staged `g12_dynamic_dispatch_audit.py` to inspect reflective access and the extent of the prior 57-site dynamic-call warning.
- Added 10 synthetic provenance tests and 10 synthetic dynamic-dispatch tests. **76/76 staging tests PASS**: 11 Sheet range ownership + 13 mock writer + 12 frozen inventory + 20 V2 receiver guards + 10 provenance + 10 reflection.
- [Staging 76-test workflow](https://github.com/kimtk94/Codex/actions/runs/39036262357) / [actual source private AST audit](https://github.com/kimtk94/Codex/actions/runs/39036246364).

## The 55 still-unclassified calls

| Conservative syntactic classification | Calls |
|---|---:|
| Container literal with single local binding | 10 |
| Builtin-name constructor with single local binding | 2 |
| Local call-result with single binding | 18 |
| Nested, conditional or complex binding | 12 |
| Multiple bindings, rebinding or deletion | 5 |
| Direct call-expression receiver | 4 |
| Subscript-expression receiver | 4 |
| **Total** | **55** |

These are AST evidence classes **not** proven runtime receiver types. A shadowed builtin name, dynamic mutation, branch, late assignment, or external adapter can invalidate a superficial interpretation. No unclassified call is added to a permanent safety allowlist. Any reclassification or release decision needs independent true destination/field-mask evidence.

## Reflective calls: clarify previous 57-site alarm

The previous broad AST scan counted the **last method-name token** for both direct Python builtins and qualified attributes. The current scan separates them:

| Category | Calls | Findings |
|---|---:|---|
| Direct `getattr(...)` | 38 | Known direct literal Sheets writer method names: **0**; immediately invoked `getattr(...)(...)`: **0** |
| Direct `locals()` | 4 | Still requires review of any indirect lookup |
| Qualified `.compile(...)` | 15 | Included in old 57 simply by method spelling; not evidence of Python builtin `compile` execution |
| Total broad spelling matches | 57 | Direct builtin invocation subset: **42** |

This audit does **not** prove that a callable returned by `getattr` cannot be stored, aliased and invoked later. Also, `.compile` call sites were not verified to be solely regex functions; they remain qualified method calls requiring appropriate contextual resolution.

## Current G12 status

- Fixed SHA-pin matches: PASS.
- Protected-row schema/ownership policy and synthetic writer tests: PASS.
- V2 receiver evaluation once, `rows`/`news` false-positive regression: PASS.
- Original 28 static writer candidate inventory: unchanged.
- V2 heuristically instrumented sites in current build: **27/28**; site 19275 `sort()` is no longer instrumented after token-level correction, and remains unreviewed.
- Unclassified `.update`/`.sort`/`.clear` sites: **55**.
- Full G12 engine execution on synthetic-only sinks: NOT RUN.
- Full G16 sink coverage: NOT PROVEN.
- True Sheets/SQLite atomic updates and physical row identity race protection: NOT PROVEN.
- Production deployment / auto-email permission: **NOT APPROVED**.

## Next concrete test gate

1. Generate a **source-line-only review queue** for all 55 AST unclassified sites, prioritized by unknown call results, dynamic access, nested/multiple bindings, subscript receivers and any structural `sort`/`clear`; use the private source without publishing identifiers or customer data.
2. Resolve private receiver-to-worksheet and API field-mask paths for the high-risk queue, especially site 19275. A call with the same function name is not proof of Sheets mutation.
3. Prove field ownership under real isolated patched CSS writer functions and a disposable test-only Sheet (not production). Rerun row-move/edit-after-read, unknown response and crash recovery fixtures.
4. Establish G16 all-sink isolation before G12 full engine E2E, then formal rollout/rollback review.

**Draft PR #168 remains unmerged and non-deployable.**
