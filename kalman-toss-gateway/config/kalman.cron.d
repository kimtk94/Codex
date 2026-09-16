# /etc/cron.d/kalman - installed by scripts/install_cron.sh
CRON_TZ=Asia/Seoul
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# CRYPTO: hourly, with GLOBAL rebuild.
5 * * * * root /opt/kalman/app/scripts/run_pipeline.sh CRYPTO_GLOBAL >> /opt/kalman/logs/crypto.log 2>&1

# KR: after regular close, Monday-Friday KST.
20 16 * * 1-5 root /opt/kalman/app/scripts/run_pipeline.sh KR_GLOBAL >> /opt/kalman/logs/kr.log 2>&1

# US: cover both DST and standard-time regular sessions in KST.
# R5.1 uses regular-session hourly bars aligned to :30 KST boundaries.
# Run at :35 so a newly completed :30 bar is available before scoring.
# The broad data window is kept through 06:35 so post-close data is refreshed
# under both DST (22:30-05:00 KST) and standard time (23:30-06:00 KST).
35 22-23 * * 1-5 root /opt/kalman/app/scripts/run_pipeline.sh US >> /opt/kalman/logs/us.log 2>&1
35 0-6 * * 2-6 root /opt/kalman/app/scripts/run_pipeline.sh US >> /opt/kalman/logs/us.log 2>&1

# US Top-6 trade worker runs 10 minutes after the :35 scoring cycle.
# Toss fractional/amount-order eligibility is determined dynamically by
# app.market_guard from the Toss US market calendar; stale R5.1 (>90m) also
# fails closed. The 04:45 KST run is useful in standard time and is safely
# rejected by market_guard during DST after the fractional window closes.
45 22-23 * * 1-5 root /opt/kalman/app/scripts/run_auto_trade.sh >> /opt/kalman/logs/auto-trade.log 2>&1
45 0-4 * * 2-6 root /opt/kalman/app/scripts/run_auto_trade.sh >> /opt/kalman/logs/auto-trade.log 2>&1

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
