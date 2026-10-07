# /etc/cron.d/kalman - installed by scripts/install_cron.sh
CRON_TZ=Asia/Seoul
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# CRYPTO: hourly, with GLOBAL rebuild.
5 * * * * root /opt/kalman/app/scripts/run_pipeline.sh CRYPTO_GLOBAL >> /opt/kalman/logs/crypto.log 2>&1

# KR: after regular close, Monday-Friday KST.
20 16 * * 1-5 root /opt/kalman/app/scripts/run_pipeline.sh KR_GLOBAL >> /opt/kalman/logs/kr.log 2>&1

# US R5.1 / execution automation: DST-safe New York market clock.
# Cron wakes dispatchers every 5 minutes in KST; each dispatcher evaluates
# America/New_York and only acts in its ET window. No manual EDT/EST shift.
*/5 * * * * root bash /opt/kalman/app/scripts/run_us_market_clock.sh cycle >> /opt/kalman/logs/us-cycle.log 2>&1
*/5 * * * * root bash /opt/kalman/app/scripts/run_us_market_clock.sh execution >> /opt/kalman/logs/execution-watch.log 2>&1

# US daytime managed-position watch: monitor P/L only, no BUY/model rebuild.
# This catches profit -> loss deterioration while Toss fractional orders are closed.
*/30 9-21 * * 1-5 root bash /opt/kalman/app/scripts/run_position_watch.sh >> /opt/kalman/logs/position-watch.log 2>&1
0 22 * * 1-5 root bash /opt/kalman/app/scripts/run_position_watch.sh >> /opt/kalman/logs/position-watch.log 2>&1

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