# Kalman 40차 감사 — 독립 Preview Source Preflight

2026-10-18 KST. 판정: **252 TESTS PASS / PREVIEW_SOURCE_READY_NOT_DEPLOYED / STAGING HOLD / P1 PRODUCTION HOLD**.

실제 운영 변수와 미연결인 독립 Preview 구성 여부를 검토했다. 새 Vercel 프로젝트는 생성하지 않았다. 기존 Staging에 권한성 환경변수가 남아 있어 직접 배포를 차단한다.

감사 브랜치에 `audits/2026-10-14/quality/isolated_preview_preflight.py` 및 7개 테스트를 작성. 기존 30파일 Synthetic Demo의 검증 및 SHA-256 지문을 계산하며, 요구되는 독립 프로젝트 이름 `kalman-synthetic-preview-isolated`, 빈 환경변수, 별도 접근 보호, 운영자 승인 조건을 고정한다. 실제 프로젝트 생성, 배포 및 승인은 모두 false로 유지한다. 준비된 데모는 11개 백엔드 API가 비활성화되고 Health만 가상 응답을 제공하며 원래 거래 UI는 제거됐다.

GitHub Actions 최종: https://github.com/kimtk94/Codex/actions/runs/39043757405 (SUCCESS). 207 기본 단위 + 15 PostgreSQL 통합 + 9 데모 + 7 Staging 승인 + 7 환경변수 범위 + 신규 7 Preview = **252개 unittest 메서드**. Chromium 데스크톱/모바일 및 로컬 HTTP 모의 시험도 성공. 결과 `PREVIEW_SOURCE_READY_NOT_DEPLOYED`. 콘텐츠 digest `3c80af7705eef30f0e786b1551e590907a5bbb4dd1602d3433cb7453987efb74`.

**중요:** Source 준비 완료는 Preview 프로젝트의 Vercel 배포 준비 승인과 다르다. Vercel 프로젝트 접근통제, 비밀변수 미상속, 별도 데이터 분리가 실제로 확인되지 않았다. Staging 및 Production 변경 없이 GitHub 감사 브랜치·CI만 변경했다. 과거 P1 순수익률 과대 계산 5건은 Neon Production에 남아 있다.
