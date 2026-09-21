# /etc/cron.d/kalman-shadow-portfolio-ranking
CRON_TZ=Asia/Seoul
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Research-only A/B/C ranking after the KR V2 SHADOW refresh.
# V2 refresh 16:50 KST -> ranking 17:05 KST, Monday-Friday.
5 17 * * 1-5 root KALMAN_ENV_FILE=/opt/kalman/.env KALMAN_CODE_SHA=e01c27223b47847ff0e4640de3d491bd8ebed7fd /opt/kalman/app/scripts/run_shadow_portfolio_ranking_v2.sh --mirror-neon >> /opt/kalman/logs/shadow-portfolio-ranking.log 2>&1

# Research-only A/B/C ranking after the US V2 SHADOW refresh.
# V2 refresh 07:30 KST -> ranking 07:45 KST, Tuesday-Saturday.
45 7 * * 2-6 root KALMAN_ENV_FILE=/opt/kalman/.env KALMAN_CODE_SHA=e01c27223b47847ff0e4640de3d491bd8ebed7fd /opt/kalman/app/scripts/run_shadow_portfolio_ranking_v2.sh --mirror-neon >> /opt/kalman/logs/shadow-portfolio-ranking.log 2>&1
