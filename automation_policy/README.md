# Master Automation OS — phase 1 policy gate

This is an **isolated, non-executing** authorization evaluator. No LIVE order, mail, database, SSH, deployment or server API is called.

## Evaluate

```bash
python3 -m unittest automation_policy.test_gate -v
python3 -m automation_policy.gate '{"action":"kalman.live_order"}'
python3 -m automation_policy.gate '{"action":"research.analysis_qc"}'
```

Exit codes: 0 allowed, 3 denied, 2 malformed CLI usage.

## Mandatory integration rules

- Enforce this gate **server-side at the executor**, not only in an AI prompt or dashboard.
- Never treat the caller's `approved=true` flag as approval. Protected actions require a separately authenticated and auditable approval system **not implemented here**; therefore they are currently denied.
- Production deploy may be allowed only with all five attested controls, verified target and immutable commit SHA; current checks consume supplied evidence and **do not independently attest its authenticity**. Production executors must verify evidence against CI and deployment systems before using this gate.
- Use explicit allowlists for repository, deployment project, environment and scope; no wildcard execution.
- Keep DB/SSH credentials outside agent context. The gate has no access to secrets.
- Fail closed on unknown actions, parse errors and missing evidence.
- No change to existing production workflows until a separate integration audit and isolated E2E tests have passed.
