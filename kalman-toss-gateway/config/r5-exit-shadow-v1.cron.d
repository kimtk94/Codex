CRON_TZ=Asia/Seoul
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# R5-EXIT-V1 prospective research ledger.
# Runs after the US session and after the 07:45 SHADOW portfolio ranking.
# No orders, no strategy_signal writes, no LIVE exit changes.
15 8 * * 2-6 root KALMAN_ENV_FILE=/opt/kalman/.env KALMAN_APP_ROOT=/opt/kalman/app KALMAN_DATA_ROOT=/mnt/gdrive /bin/bash /opt/kalman/app/scripts/run_r5_exit_shadow_v1.sh >> /opt/kalman/logs/r5-exit-shadow-v1.log 2>&1
