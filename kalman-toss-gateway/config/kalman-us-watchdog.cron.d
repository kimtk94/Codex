SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# DST-safe watchdog: dispatcher evaluates America/New_York and runs at
# 10:50-15:50 ET on US weekdays, 15 minutes after each R5.1 cycle.
*/5 * * * * root /opt/kalman/app/scripts/run_us_market_clock.sh watchdog >> /opt/kalman/logs/us-auto-watchdog-cron.log 2>&1