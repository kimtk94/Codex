# G12 V2 receiver audit — 2026-10-17

**Decision: READ-ONLY PRIVATE AUDIT PASS / G12 PRODUCTION RELEASE BLOCKED**

## Inputs and boundaries

- SHA-256-pinned live CSS source `a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840`
- Source read within private, rootless Bubblewrap (no outbound networking, operational credentials, SQLite, mail or Google Sheet mounts). The CSS module, Collector and `main()` are **not imported or executed**.
- Staging branch `audit/css-g16-boundary-20261016`, draft PR #168. No production CSS file, service, sheet, database or schedule changes.

## Key new finding: V2 heuristic false positive

The first V2 heuristic used **substring** detection for `ws`, thereby also matching ordinary identifiers ending in `ws` such as `rows` or `news`. This could misclassify non-Sheets `.sort()` and `.update()` calls as worksheet writes and interrupt normal CSS logic. The staged guard now matches **complete underscore/dot-separated identifier tokens** (`ws`, `worksheet`, `sheet`, `sheets`, `spreadsheet`, `gspread`, `gsheet`) rather than any substring. Synthetic tests prove `rows.sort()` and `news.update()` are no longer rewritten, while `contract_ws.clear()` remains a guard candidate.

That fix moved exactly **one** call from previously wrapped to unclassified relative to the frozen 28-call writer candidate inventory:

| Check | Before | After |
|---|---:|---:|
| Frozen AST writer candidate inventory | 28 | 28 |
| V2 *heuristically* wrapped calls | 28 | **27** |
| Baseline unwrapped site | 0 | **19275 / sort** |
| Other heuristic-wrapped sites outside frozen inventory | not separately shown | **0** |
| Unclassified `update/sort/clear` candidates | 54 | **55** |
| V2 strict unclassified gate | BLOCKED | **BLOCKED** |

The line 19275 call is **not proven benign**, and was not removed from the immutable 28-site review inventory. The one identified false-positive *matching pattern* does not prove that call's concrete receiver type.

[Isolated actual-source delta CI](https://github.com/kimtk94/Codex/actions/runs/39035475268)

## Receiver-shape analysis of 55 unclassified calls

Method distribution: `update=45`, `sort=8`, `clear=2`. Syntactic receiver forms are `Name=47`, `Call=4`, `Subscript=4`.

| Static hint (not runtime proof) | Count |
|---|---:|
| Direct local dictionary or list literal assignment | 8 |
| Local `dict()`/`list()`/`set()` constructor call | 2 |
| Other locally assigned call results | 18 |
| Name lacking a unique immediate assignment | 17 |
| Direct call-expression receiver | 4 |
| Subscript-expression receiver | 4 |
| Other direct assignment forms | 2 |
| **Total** | **55** |

These 10 local-container/constructor cases are only *likely ordinary operations*. They must not be reclassified as safe based on names or shapes; constructors can be shadowed and local variables can be rebound indirectly. **Confirmed safe: 0; confirmed Sheets sinks: 0.** This scan deliberately does not output private names, literals, or source text.

## Regression and next gate

[Staging regression 56/56 PASS](https://github.com/kimtk94/Codex/actions/runs/39035434069): 11 protected range tests, 13 mocked writer tests, 12 coverage freeze tests and 20 V2 guard tests. The change also adds two targeted synthetic classifier tests verifying false-positive removal.

Still required for release: establish actual receiver types and worksheet destinations for all 55 ambiguous method calls and 27 wrapped calls; independently audit the 57 previously observed dynamic builtin call sites for any indirect Sheets write; validate true per-cell ownership and stable keyed row identity in disposable Sheets; complete actual isolated G12 engine E2E and G16 all-sink containment. No production release without explicit human approval and a reversible rollout.

**Do not equate successful CI or compilation with proof that user-control cells are protected in production.**
