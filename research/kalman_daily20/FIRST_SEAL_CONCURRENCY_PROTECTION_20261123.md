# Daily20 2026-11-24 first-seal collision isolation — research HOLD

**Implementation 7/10 (70%). Scientific acceptance still 3 gates; independent regular close 0/26, issuer factors 0/25, pending first real prospective/replay OOS evidence.** No broker, trading rule, market price, signed historical event or Google Drive file changed.

## Verified queue collision

Before this patch the entire `.github/workflows/kalman-daily20.yml` used one static `concurrency.group: kalman-daily20-research` with `cancel-in-progress: false`. GitHub allows at most one running plus one pending per group; a newly queued PR or main push may **replace** the previously pending scheduled 02:40/04:40 UTC run even though `cancel-in-progress` is false. The separate 06:25/07:25 watchdog can report missing slots *after* the fact but cannot recover an unarchived first seal.

The workflow runs the full 26-market-asset PR matrix for every related PR and repeatedly runs protected-main push checks on code edits. Thus this is a material, source-verified risk on the evening before Monday 2026-11-23 U.S. trading session, which ends before Tue 2026-11-24 11:40 KST first scheduled seal.

## Group policy

Use a Github expression:
`kalman-daily20-research-${{ github.event_name == 'pull_request' && format('pr-{0}', github.event.pull_request.number) || 'protected-main' }}`

- **Each PR** gets an independent test-only queue and never consumes the pending scheduled seal's group.
- **Protected `main`** push, manual dispatch, **02:40 first** and **04:40 replay** continue to share one serialized group. This is essential: they can all access the same pinned results ZIP. The patch does not create parallel Drive writers or remove the existing post-save independent readback.
- GitHub `cancel-in-progress: false` retained. Main pushes can still cause pending replacement inside the one protected-main group; this change reduces the exposure but does **not** guarantee scheduler delivery. Dedicated heartbeat and external ChatGPT monitor remain necessary.

## Enforce first-seal provenance before forward writers

The immutable two-pass read-only preflight now receives both GitHub-native values `--event-name "${{ github.event_name }}"` and `--schedule-slot "${{ github.event.schedule }}"` in its **pre** and **post** phases. Fail-closed checks:

- A true scheduled run **must** state an exact known first/replay cron slot; a push/manual run **must not** claim a scheduled cron.
- For a genuinely new, unsealed XNYS session, a protected-main **`push` now fails before Bull/Bear forward writers** with `TWO_PASS_MAIN_PUSH_MUST_NOT_PREEMPT_SCHEDULED_FIRST_SEAL`, avoiding accidental 60-event first creation on a code change between the U.S. close and planned first scheduled slot.
- A true **02:40 UTC schedule** is still the expected automatic initial 20 Bull + 40 Bear seal, and **04:40** is only a replay of its frozen original 26 price/420 feature/40 model/60 event anchors.
- A **manual `workflow_dispatch` remains available** for a deliberately started research-only first seal if required to recover from a missed schedule. It must not be counted as the scheduled original by the independent two-slot watchdog. No automatic “recovery” or backdating occurs.
- An existing Nov 20 legacy journal and an already complete Nov 23 prospective journal may be replayed by a main push with exactly **0 new signal events**. No change to the original historical HOLD.
- A changed `event_name` or cron slot between preflight/postflight fails; the prior source ZIP SHA, original journal bytes, first snapshot SHA, source-provider finality HOLD and trading shutdown remain separately checked.

## Tests and limitations

Nine new offline event-type cases (push cannot auto-seal, real first scheduled still seals, deliberate manual first retains only research evidence, old/complete forward replay allowed, forged cron and unknown event rejected) and five static workflow contract tests (PR queue separation, main writer queue serialization, 02:40/04:40 cron retention and exact event_name propagation, no live promotion). All tests are synthetic fixtures, never counted as actual prospective outcomes.

**First observable real acceptance**: Tue 2026-11-24 11:40 KST schedule must create a genuine signed 20+40 cohort with original 21-feature inputs. Tue 13:40 KST schedule must report 0 new events and preserve the same original SHA; Tue 15:25/16:25 KST the independent watchdog must verify both. Failure of a GitHub schedule means scientific HOLD rather than a fabricated replay or green certification. The 2026-11-20 cohort first 4-XNYS-session settlement is only after Fri Nov 27 U.S. session; the first Nov23 cohort after Mon Nov30 U.S. session.

### Existing external CSV access limitation unaffected
The legacy QLD/QQQ file `exports/QLD_QQQ_daily_alignment.csv` remains a separate 2017–2026-09 historical source. Its file-scoped viewer IAM issue [#1018](https://github.com/kimtk94/Codex/issues/1018) is **not resolved by this PR**, and it is not required by the new genuine daily first-seal pipeline. Do not broaden Drive sharing or make it public. The historical source's existing SHA audit stays HOLD until IAM is fixed.
