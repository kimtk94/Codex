# G12 P0 receiver origin audit — 2026-10-17

**Status: 16/16 P0 receiver origin hints enumerated; 0 actual worksheet targets proven; G12/G16 release remains blocked.**

The live CSS SHA-256-pinned source was read only inside the private isolated compile job. No import, CSS main invocation, production Sheet write, SQLite, email, or service edits occurred.

[Actual-source P0 receiver audit](https://github.com/kimtk94/Codex/actions/runs/39037584997)

| Source line(s) | AST evidence | Count | Runtime target confirmed? |
| --- | --- | ---: | --- |
| 5052, 13429, 14747, 15890, 16109 | single local list literal assignment | 5 | No |
| 16989 | single local dict literal assignment | 1 | No |
| 5108, 5116, 8417, 8420 | direct call-return object | 4 | No |
| 7613, 9641, 9643, 13716 | indexed/subscript object | 4 | No |
| 12935 | multiple local assignments | 1 | No |
| **19275** | unresolved binding for sort receiver | **1** | **No** |
| **Total** | | **16** | **0 proven** |

This is **not** a runtime type audit. The local literal assignments imply ordinary list/dict operations may be involved but do not prove objects are not overwritten, aliased, passed through unknown helpers, or that actual Sheets writes cannot occur. The prior 28-call baseline and all 55 unclassified calls remain under review.

## Recommended next focus

1. **19275 `sort`**: inspect receiver binding and actual sort destination with a private review of surrounding AST and dataflow, never infer safety from `sort` method alone.
2. **Call-return receivers (5108/5116/8417/8420)**: trace called function return types and aliases.
3. **Indexed objects (7613/9641/9643/13716)**: establish actual container source, element type and effect on Sheet write paths.
4. **Multiple bindings (12935)**: check branch-dependent rebinding and runtime alias targets.
5. **Local literal six sites**: add negative/rebinding tests before qualifying as ordinary Python containers, and avoid whitelisting the whole category.

Only after actual writer destinations and exact field masks are determined should G16 all-sink isolated real function tests and G12 full engine E2E be attempted.

**No production deployment authorized.**
