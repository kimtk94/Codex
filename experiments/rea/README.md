# REA isolated pilot — 2026-10-17

Target: evaluate external project `morluto/rea` as a Codex-adjacent reverse-engineering assistant in a non-LIVE workspace.

## Safety boundaries

- Do not touch `/opt/kalman`, order execution, trading credentials, production env, or LIVE settings.
- Do not automatically run REA `setup`; it changes agent configuration.
- Never run untrusted packages as root.
- Investigate only publicly observable or authorized functionality.
- Report measurements and evidence rather than claiming to recover proprietary internals.

## Execution from a development shell

```bash
git clone -b feat/rea-isolated-pilot-20261017 git@github.com:kimtk94/Codex.git "$HOME/rea-codex-pilot"
cd "$HOME/rea-codex-pilot"
bash experiments/rea/rea_preflight.sh
# only if preflight passes, review the script, then:
bash experiments/rea/rea_doctor_isolated.sh
```

The commands above assume SSH authentication is already installed and configured on that development machine. They **do not** set up SSH credentials.

## Acceptance gates
1. Supported Node.js (22.19+, 24.11+, or 26+).
2. REA doctor passes under non-root development account.
3. Codex MCP integration is reviewed, explicitly approved, and validated.
4. One authorized demo produces an evidence matrix and separate implementation specification.
5. LIVE trading config remains unchanged.

Status: GitHub experiment branch prepared; server SSH/doctor not executed or validated.
