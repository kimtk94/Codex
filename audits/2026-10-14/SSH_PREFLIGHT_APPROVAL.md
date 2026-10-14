# SSH preflight — approval boundary (2026-10-14)

Existing workflow `.github/workflows/server-readonly-audit.yml` authenticates successfully using environment `TaehoonServer`, but only probes host/disk/memory/uptime.

## Exact next step (not executed)
The operator may run the following *on the authorized host* in a separate audit checkout after validating the checkout commit:

```bash
cd /home/taehoon/Codex/audits/2026-10-14/quality
python3 -m unittest -v test_quality_gate.py test_reconcile_offline.py test_broker_snapshot_contract.py test_broker_cache_preflight.py test_broker_audit_get.py
```

For **cache-only preflight**, do not log credentials or cached token. The audit should report only READY/BLOCKED and remaining token lifetime. Do not use `engine/execution_telemetry_sync.py`: it mutates local telemetry state. Never dump `.env` or token cache file into GitHub Actions output or Drive.

The existing server-readonly workflow does not contain this cache preflight. A successful historical SSH run is not evidence that a cache-only probe or broker GET has actually executed.

## Explicit boundaries
- No change to `main`, LIVE or Vercel/Neon deployments.
- No secrets committed to Git, artifacts, or Drive.
- Separate 'broker probe approval' from infrastructure read-only checks.
- Keep broker reconciliation UNKNOWN until independently verified broker holdings/orders are obtained and checked.
