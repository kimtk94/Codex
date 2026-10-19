#!/usr/bin/env bash
# Read-only environment check; run under a development account.
set -u
printf 'REA_KALMAN_PREFLIGHT\n'
printf 'date_utc=%s\n' "$(date -u +%FT%TZ)"
printf 'host=%s\n' "$(hostname)"
printf 'user=%s\n' "$(id -un)"
printf 'node=%s\n' "$(node -v 2>/dev/null || echo NOT_FOUND)"
printf 'npm=%s\n' "$(npm -v 2>/dev/null || echo NOT_FOUND)"
printf 'npx=%s\n' "$(command -v npx || echo NOT_FOUND)"
printf 'codex=%s\n' "$(command -v codex || echo NOT_FOUND)"
node -e 'const p=process.versions.node.split(".").map(Number); const ok=(p[0]===22&&p[1]>=19)||(p[0]===24&&p[1]>=11)||(p[0]>=26); console.log("rea_supported_node="+ok); process.exit(ok?0:2)' 2>/dev/null
status=$?
if [ "$status" -ne 0 ]; then
  echo 'RESULT=BLOCKED_NODE_VERSION'
  exit 2
fi
echo 'RESULT=PREFLIGHT_PASS'
