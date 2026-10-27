# Novogene CSS P0 Evidence Ledger — 2026-10-18

Status: **HOLD — no production deployment authorization**.

## Historical verified GitHub Actions
| Gate | Run ID | Job conclusion | Scope |
|---|---|---|---|
| OS container negative controls | 39051111730 | success | No network, read-only container; no production CSS execution |
| Large SIF real-function regression | 38640063806 | success | 1,200 synthetic projects, selected extracted CSS functions |
| Exact main AST branch regression | 38644452604 | success | Real main branch extracted, not main invocation |
| Real Action/Review generator regression | 38658186666 | success | Selected real output generator functions, not full pipeline |

All runs above are historical evidence only, not validation of the current branch head.

## Current P0 synthetic gate
- Workflow: `.github/workflows/novogene-css-p0-synthetic-gate.yml`
- Runner: `css-upgrade/staging-20261014/run_p0_synthetic_gate.py`
- Inputs: `os_sandbox_negative_controls.py`, `css_source_admission.py`, `synthetic_adapter_contract.py`
- Status: **UNVERIFIED**. The available GitHub integration has not returned a push-triggered workflow run ID; no claim of passing current CI is authorized.
- Contract script is a synthetic behavioral model and does **not** import/exercise actual CSS functions.

## Blocking conditions for any full-main CSS integration
1. Obtain the current gate run URL, log, and matching head SHA; require all tests successful.
2. Check real CSS source SHA-256 against expected pinned `a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840` on an authorized host. Do not copy source into GitHub.
3. Treat import-time execution and network, DB, Sheets, mail, Drive, Salesforce, subprocess sinks as **fail closed** until all are intercepted inside an OS-enforced sandbox.
4. Never mount production SQLite, API credentials, SSH keys, or customer Sheets; use only independently generated fixtures and temporary synthetic resources.
5. Explicitly verify no production side effects, and test manual Hold/Skip precedence, Prepayment attention suppression, QC reentry, independent Action Center work, and idempotent writes.
6. Do not merge, schedule, deploy, or run CSS `main()` until all above gates pass and separate production approval is granted.

This ledger documents evidence and outstanding gates. It does not itself run a test.
