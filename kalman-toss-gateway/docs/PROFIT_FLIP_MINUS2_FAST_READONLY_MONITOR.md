# Kalman LIVE profit-flip -2.0% and two-minute read-only monitor

## Authorized change
- The user explicitly selected -2.0% instead of -0.2% as the **profit flip trigger**.
- Keep profit-flip **armed at +0.2%**, 2 consecutive risk observations,
  recovery-to-zero behavior, independent hard STOP at **-3.0%**,
  Friday-flat, max 4 canonical model buckets.
- Keep the **5-minute LIVE execution watcher** and hourly model cycle intact.
- Add a **2-minute CHECK ONLY** process: reads local SQLite active positions and
  Toss latest prices, logs threshold crossings but **does not place orders**,
  update exit state/guard confirmation counters, submit sells or buy stocks.
- The 5-minute position manager still owns the actual exit confirmation and
  submission. Faster logging must not be described as a 2-minute trade trigger.
- Research caution: 2026 in-sample 251 trades favored a wider exit threshold,
  but recent real flip exits had larger losses under the relaxed rule.

## Deployment
The authorized remote bridge cannot sudo or access /opt/kalman/app and /opt/kalman/.env.
Run the following command in an **interactive authorized server terminal** only:

```bash
sudo python3 /home/taehoon/KALMAN_FLIP_LIVE_POLICY_20261010/kalman-toss-gateway/scripts/apply_profit_flip_minus2_fast_check.py --apply
```

Preflight checks policy baseline; locks `us-cycle.lock` and
`auto-trade.lock` in the same order as the LIVE watcher, fails closed if
the old trigger has pending exit state, backs up the entire root-only env and
cron to a private `/opt/kalman/state/flip-minus2-fast-monitor-backup-*`
directory, then updates **one** LIVE env key:
`AUTO_TRADE_PROFIT_FLIP_TRIGGER_PCT=-0.02`.
Appends independent 2-minute read-only cron checks and installs
`fast_profit_flip_check.py` without touching the current
`position_manager.py` or other dirty deployed code. Existing cron entries
are retained. Failures after changing a file restore previous bytes.

The fast monitor runs every 2 minutes on weekdays 09:00–23:59 KST and
Tue–Sat 00:00–05:59 KST. It is intentionally off overnight between
06:00–08:59 KST and outside active weekdays, with an extra 5-minute
LIVE execution watch for actual trade management during NY session.
Read-only monitor uses its own `fast-profit-flip-monitor.lock` to avoid overlaps.

## Validation after deployment
```bash
sudo grep -E '^AUTO_TRADE_PROFIT_FLIP_(GUARD_ENABLED|ARM_PCT|TRIGGER_PCT|RECOVERY_PCT|CONFIRM_OBSERVATIONS)=' /opt/kalman/.env
grep 'fast_profit_flip_check.py' /etc/cron.d/kalman
systemctl is-active kalman-toss-gateway.service
sudo tail -n 15 /opt/kalman/logs/fast-profit-flip-check.log
```
No gateway restart is needed: scheduled Python invocations reload the
environment file. The long-lived gateway service's process environment may
remain stale until its next controlled restart if it also uses this variable;
the risk exit manager itself reloads from the environment file every run.

The existing source configuration's `live-canary-5000` preset has been
updated to the -2.0% trigger only; all dry-run/off presets retain their own
defaults. Preset update is **not** deployed to root app source by this
configuration-only installer.

## Rollback
Under administrator authorization, restore `kalman.env.before` and
`kalman.cron.before` from the printed root-only backup directory.
The installer does not silently migrate old pending exits or change
broker orders that were already submitted.

## Provenance
Separate source worktree/branch:
`feat/flip-minus2-fast-monitor-20261010`.
Run `python3 scripts/apply_profit_flip_minus2_fast_check.py` without
`--apply` for source-only contract check without root privileges.
