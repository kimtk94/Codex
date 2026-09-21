# /etc/cron.d/kalman-macro-feature
# Macro challenger refresh only. Does not enable live trading.
CRON_TZ=Asia/Seoul
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

*/15 * * * * root /opt/kalman/app/scripts/run_macro_event_features_v1.sh build >> /opt/kalman/logs/macro-feature.log 2>&1
