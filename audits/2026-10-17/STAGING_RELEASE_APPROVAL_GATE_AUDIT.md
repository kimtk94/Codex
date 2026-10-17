# Kalman 38차 감사 — Staging 독립 승인 및 운영 격리 게이트

일시: 2026-10-17 KST
최종 판정: **238 TESTS PASS / CHROMIUM E2E PASS / STAGING_HOLD / PRODUCTION_P1_HOLD**

## 실행 작업
연결된 Vercel 프로젝트를 GET-only 조회해 `kalman-investment-hub-v2-staging` 프로젝트의 SSO가 여전히 disabled이고 비밀번호 보호도 비활성화인 상태를 재확인했다. MAIN 프로젝트의 SSO는 활성화되어 있다. Staging 실제 런타임 HTTP 접근 가능성이나 credential, DB 분리를 증명한 것은 아니다.

감사 브랜치의 `audits/2026-10-14/quality/staging_release_approval_gate.py` 추가:
- 정확한 Staging 프로젝트 ID를 고정
- SSO 또는 비밀번호 보호가 반드시 활성화된 증거 요구
- 계정·DB·alias·30-file 패키지 무결성·백엔드 API 비활성화·롤백 대상의 독립 attestation 요구
- 사용자별 Staging-only 승인 별도 요구
- 현재 GET-only snapshot을 입력하면 `STAGING_HOLD / STAGING_ACCESS_PROTECTION_MISSING` 반환
- 전체 조건을 synthetic으로 true 처리하더라도 `PREFLIGHT_REVIEW_COMPLETE`만 반환, `deployment_authorized=false` 유지
- 이는 source contract 검사이지 실제 Vercel 설정을 바꾸는 도구가 아님

`test_staging_release_approval_gate.py`에 7개 회귀 테스트 추가, CI 재실행 통과.

GitHub Actions https://github.com/kimtk94/Codex/actions/runs/39043065720 COMPLETED SUCCESS:
- 207개 기존 단위 테스트
- 15개 일회용 PostgreSQL 실제 미러 프로세스 통합 테스트
- 9개 데모 격리 테스트
- 7개 신규 Staging 승인 게이트 테스트
- 총 238 unittest methods PASS
- Headless Chromium desktop/mobile 데모 렌더링 E2E PASS
- 전체 보호 웹 빌드 및 실제 배포 파일 소스 fingerprint 대조 PASS

## 블로커
1. 기존 Staging 접근 보호 비활성화. 운영 자격증명·DB 독립성, 공개 HTTP 접근/민감 API 여부 미검증.
2. 실제 MAIN 배포 소스는 보호 전 v7.4.36과 동일하며 순수익률 표시 P1 오류 경로가 존재. 실제 사용자 HTTP 응답 검증은 미완료.
3. 과거 Neon Production 순수익 과대 계산 5건 미정정.
4. LIVE 서버 SHA 및 증권사 실제 수수료 통화, 주문별 원장 독립 대조 미완료.

**변경 범위: GitHub 감사 브랜치와 CI 문서만. Vercel 배포·설정 변경, Neon Production DML, 실제 계좌·LIVE 서버·거래 작업 없음.**
