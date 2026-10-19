# G12 V2 — SHA-pinned 55-call review queue (2026-10-17)

**Outcome:** a complete read-only line-number review queue was generated against the pinned real CSS source. All 55 candidate calls are unresolved; **zero calls are proven safe**, and no Sheets writer was executed. The full machine-readable queue is in the CI audit JSON rather than copied into this document.

- [Read-only actual-source review queue](https://github.com/kimtk94/Codex/actions/runs/39037287897)
- [88/88 synthetic offline tests PASS](https://github.com/kimtk94/Codex/actions/runs/39037301054)
- Source SHA-256: `a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840`
- Staged scanner: `g12_v2_review_queue.py`. No production source imports, `main()` execution, credentials, mailbox, SQLite or live Sheets calls.

## Reviewer queue priority

| Priority | Calls | Basis | Automatic safety decisions |
| --- | ---: | --- | --- |
| P0 structural receiver (`sort`/`clear`) | 10 | Potentially destructive or row-reordering API spelling | None |
| P0 indirect receiver (`.update()` on call/subscript result) | 6 | Receiver identity cannot be statically resolved | None |
| P1 ambiguous bindings/reassignment | 15 | Multiple/nested/conditional assignment, unknown provenance | None |
| P1 saved call result | 18 | Receiver originates from another helper/factory | None |
| P2 unverified container or other | 6 | Only syntactic clues of an ordinary Python container | None |
| **Total** | **55** | **All destinations unresolved** | **0** |

## P0 — first 16 line-number entries

| Line | Method | Why prioritize |
| ---: | --- | --- |
| 5052 | sort | structural; possible local-container hint only |
| 5108 | update | call-expression receiver |
| 5116 | update | call-expression receiver |
| 7613 | update | indexed/subscript receiver |
| 8417 | update | call-expression receiver |
| 8420 | update | call-expression receiver |
| 9641 | sort | structural; indexed/subscript receiver |
| 9643 | sort | structural; indexed/subscript receiver |
| 12935 | sort | structural; multiple assignments |
| 13429 | sort | structural; possible local-container hint |
| 13716 | update | indexed/subscript receiver |
| 14747 | sort | structural; possible local-container hint |
| 15890 | sort | structural; possible local-container hint |
| 16109 | clear | structural; possible local-container hint |
| 16989 | clear | structural; possible local-container hint |
| **19275** | **sort** | frozen 28-call prior baseline; nested or complex binding, **must not be silently omitted** |

The source's sheet/control fields, destinations, exact request masks, and underlying runtime object types are **not** established by these line-number and AST-shape observations. P0 is review order, not evidence of harmful mutation. A local-list or dict hint does not establish that a receiver can never be rebound.

## Reviewer checklist and completion conditions

1. Inspect the actual receiver provenance for each P0 call in an isolated source-protected environment; separately identify ordinary Python list/dict mutation vs actual gspread/Sheet method, with evidence. Never print private source or customer literals to CI logs.
2. For any Sheets write, resolve **the exact target sheetId/title**, the A1/range/field mask, and the effect on operator controls and record IDs. Specifically inspect `19275 sort` for physical row movement and potential loss of key associations.
3. Extend the same evidence process to P1 (33) and P2 (6) calls; no category may be bulk-whitelisted based on static name or constructor inference.
4. Require a future complete, independently reviewed inventory of actual Sheets writer paths, isolated writer function tests, G16 sink protection and G12 end-to-end before any promotion.

## Operational safety

G12 strict mode and release remain **BLOCKED**. Staging source and CI were changed; operational service, CSS source, Sheets, mail, SQLite, CRM and schedules were **not** modified.
