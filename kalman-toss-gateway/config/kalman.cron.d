# /etc/cron.d/kalman - installed by scripts/install_cron.sh
CRON_TZ=Asia/Seoul
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# CRYPTO: hourly, with GLOBAL rebuild.
5 * * * * root /opt/kalman/app/scripts/run_pipeline.sh CRYPTO_GLOBAL >> /opt/kalman/logs/crypto.log 2>&1

# KR: after regular close, Monday-Friday KST.
20 16 * * 1-5 root /opt/kalman/app/scripts/run_pipeline.sh KR_GLOBAL >> /opt/kalman/logs/kr.log 2>&1

# US R5.1: each cycle starts after the :30 canonical hourly boundary.
# run_us_cycle.sh serializes: US pipeline commit -> position/ledger sync -> auto-trade.
# This avoids evaluating the previous signal while the ~40m US pipeline is still running.
# R5.1 freshness uses bar completion (stored as_of is the immutable 60m BAR START).
35 23 * * 1-5 root /opt/kalman/app/scripts/run_us_cycle.sh >> /opt/kalman/logs/us-cycle.log 2>&1
35 0-4 * * 2-6 root /opt/kalman/app/scripts/run_us_cycle.sh >> /opt/kalman/logs/us-cycle.log 2>&1

# US daytime managed-position watch: monitor P/L only, no BUY/model rebuild.
# This catches profit -> loss deterioration while Toss fractional orders are closed.
*/30 9-21 * * 1-5 root bash /opt/kalman/app/scripts/run_position_watch.sh >> /opt/kalman/logs/position-watch.log 2>&1
0 22 * * 1-5 root bash /opt/kalman/app/scripts/run_position_watch.sh >> /opt/kalman/logs/position-watch.log 2>&1

# US execution watcher: begin before the earliest regular open and rely on the
# Toss market calendar to fail closed until fractional execution is actually allowed.
# This provides opening revalidation at 22:25+ KST during DST and remains safe
# when standard time shifts the executable window later.
25-55/5 22 * * 1-5 root /opt/kalman/app/scripts/run_execution_watch.sh >> /opt/kalman/logs/execution-watch.log 2>&1
0,5,10,15,20,25,30,40,45,55 23 * * 1-5 root /opt/kalman/app/scripts/run_execution_watch.sh >> /opt/kalman/logs/execution-watch.log 2>&1
0,5,10,15,20,25,30,40,45,55 0-4 * * 2-6 root /opt/kalman/app/scripts/run_execution_watch.sh >> /opt/kalman/logs/execution-watch.log 2>&1
*/5 5 * * 2-6 root /opt/kalman/app/scripts/run_execution_watch.sh >> /opt/kalman/logs/execution-watch.log 2>&1

# Seeking Alpha collector -> US/BTC feature refresh (DISABLED BY DEFAULT).
# Enable only after the authorized SA input method and snapshot timing are verified.
# 45 7 * * * root /opt/kalman/app/scripts/run_sa_us_btc_refresh.sh >> /opt/kalman/logs/sa-us-btc.log 2>&1


# Market Tools V2 fixed-model SHADOW refresh.
# KR close: refresh KR/BTC/common data, score fixed Model V2, mirror Neon SHADOW.
# Finviz is skipped here because the US point-in-time snapshot is captured after the US close.
50 16 * * 1-5 root /opt/kalman/app/scripts/run_v2_shadow_refresh.sh --mirror-neon --skip-finviz >> /opt/kalman/logs/v2-shadow-kr.log 2>&1

# US close: 07:30 KST safely follows both DST and standard-time US closes.
# Refresh all V2 data/features, capture Finviz PIT, fixed-model score, mirror Neon SHADOW.
30 7 * * 2-6 root /opt/kalman/app/scripts/run_v2_shadow_refresh.sh --mirror-neon >> /opt/kalman/logs/v2-shadow-us.log 2>&1
