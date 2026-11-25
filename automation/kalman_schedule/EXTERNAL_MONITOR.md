# External KALMAN schedule delivery probe (proposal; not deployed)

Reuses schedule_delivery_audit.py and its strict read-only GitHub API checks.
This is not a new trading workflow, an automatic dispatch mechanism, or an
assertion of independent scientific validation.

## Host deployment acceptance (separate approval)

- Run from an independently scheduled host (not GitHub Actions), ideally an
  existing authorized always-on monitoring environment. No host was selected
  or provisioned by this PR. A host and its schedule/alert path must be verified.
- Proposed check window: Tue-Sat at 17:20 KST (08:20 UTC), after the existing
  08:15 UTC delivery grace. Use the host scheduler; no new Actions cron.
- The host supplies a read-only, repository-scoped GitHub credential with
  Actions read permission, using its existing secret store. Never place
  credentials in the repo, command line, report, or notification.
- From a reviewed checkout, invoke:
  python3 automation/kalman_schedule/external_schedule_probe.py --out /approved/local/path/kalman-delivery.json
- Exit 0 means four successful registrations, exactly one in each proposed
  UTC slot window (02:40, 04:40, 06:25, 07:25, inclusive 50-minute grace).
  Count-only success, out-of-window runs and duplicate window occupancy
  cannot pass. Registration timestamps are not exact cron identity,
  completion deadlines or original first/replay seal proof. Exit 2 means missing, invalid, or unavailable
  evidence; exit 3 means today's UTC audit is not due. Never reuse a prior
  day's result as today's pass. Retry only incomplete API evidence, with 5s
  and 15s waits and at most three attempts. A valid missing-delivery report
  alerts without retrying. Report generation or host failure also needs an
  alert (nonzero exit or stale report). Set a bounded host task timeout.
- Host must independently verify freshness of the target UTC date, successful
  delivery of a synthetic failure alert, and absence of source/writer
  mutations. A stale or missing heartbeat is UNKNOWN/HOLD. Keep the local
  output private and retain dated evidence per host policy.
- Do not configure recovery dispatch, credential expansion, Drive access,
  source changes, model promotion, broker or LIVE writes. Report
  host_independence_verified remains false until independent deployment
  evidence is reviewed outside this code.

## Verification

The existing schedule-delivery audit offline test suite includes synthetic
wrapper tests (including late successes, duplicate window occupancy, early
registration and exact grace boundaries). No external host/network credential
is used by those tests.
Existing GitHub audit workflow, schedule, and writer code are unchanged.
Related issue: #1045.
