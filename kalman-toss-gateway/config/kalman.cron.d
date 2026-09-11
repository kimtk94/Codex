# /etc/cron.d/kalman - installed by scripts/install_cron.sh
CRON_TZ=Asia/Seoul
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# CRYPTO: hourly, with GLOBAL rebuild.
5 * * * * root /opt/kalman/app/scripts/run_pipeline.sh CRYPTO_GLOBAL >> /opt/kalman/logs/crypto.log 2>&1

# KR: after regular close, Monday-Friday KST.
20 16 * * 1-5 root /opt/kalman/app/scripts/run_pipeline.sh KR_GLOBAL >> /opt/kalman/logs/kr.log 2>&1

# US: cover both DST and standard-time regular sessions in KST.
# Mon-Fri US evening starts map to Mon-Fri late evening KST; overnight maps to Tue-Sat KST.
15 22-23 * * 1-5 root /opt/kalman/app/scripts/run_pipeline.sh US >> /opt/kalman/logs/us.log 2>&1
15 0-6 * * 2-6 root /opt/kalman/app/scripts/run_pipeline.sh US >> /opt/kalman/logs/us.log 2>&1

# Trade worker follows the same US window, 10 minutes after the pipeline.
# It remains inert unless AUTO_TRADE_ENABLED plus both live trading gates are explicitly opened.
25 22-23 * * 1-5 root /opt/kalman/app/scripts/run_auto_trade.sh >> /opt/kalman/logs/auto-trade.log 2>&1
25 0-6 * * 2-6 root /opt/kalman/app/scripts/run_auto_trade.sh >> /opt/kalman/logs/auto-trade.log 2>&1

# SA x US x BTC feature worker (DISABLED BY DEFAULT).
# Enable only after a successful manual run and after confirming SA snapshot timing.
# 45 7 * * * root /opt/kalman/app/scripts/run_sa_us_btc_features.sh >> /opt/kalman/logs/sa-us-btc.log 2>&1
