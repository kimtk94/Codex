# Git SSH audit runbook

Status: audit branch only; no LIVE deployments or state changes.

1. Validate an existing GitHub SSH identity locally with `ssh -T git@github.com` (authentication message only).
2. Verify remote before use: `git remote -v` and `git ls-remote git@github.com:kimtk94/Codex.git refs/heads/audit/kalman-control-20261014`.
3. Use a separate checkout for the audit branch, not `/opt/kalman/app` or an active deployment directory.
4. From `audits/2026-10-14/quality`, run `python3 -m unittest -v test_quality_gate.py` then `python3 quality_gate.py --at 2026-10-14T11:35:00Z --output quality_report.json`.
5. Store reports in Drive Kalman_Diagnostics, with run ID and code SHA. Do not upload any private keys, credentials, broker order details, or environment files.

GitHub repository: git@github.com:kimtk94/Codex.git
Audit branch: audit/kalman-control-20261014

Prerequisite: working Git SSH credentials. No claim that server SSH or Drive auto-upload is currently verified.
