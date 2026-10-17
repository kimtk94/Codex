# Kalman 37차 감사 — Headless Chromium Desktop/Mobile Demo E2E

일자: 2026-10-17 KST
판정: **CHROMIUM E2E PASS / 231 UNIT TESTS PASS / STAGING HOLD / PRODUCTION P1 HOLD**

## 이번 단계에서 실행한 내용

GitHub 감사 브랜치에 `audits/2026-10-14/quality/demo_browser_e2e.py`를 추가하고 CI에 Playwright 1.56.0 및 Chromium 설치와 전용 E2E 단계를 연결했다.

기존 `build_demo_only_staging.py::create()`가 생성하는 30개 데모 파일만 CI의 임시 디렉터리에 저장하고, `127.0.0.1`의 임시 포트에서 정적 HTTP로 제공한다. 해당 서버는 브로커·DB·운영 API와 연결하지 않는다.

Chromium 테스트는 두 viewport를 각각 검증했다.

- 데스크톱 1365×768, 모바일 390×844
- 실제 렌더링에서 `SYNTHETIC DEMO ONLY` 경고가 보이는지, 데모 DOM 문구가 갱신되는지 확인
- `button`/ `input`이 없고 매수·매도 액션 문구가 없으며 수평 오버플로가 없는지 확인
- 페이지 탐색 중 외부 URL과 `/api/` 요청이 없는지 확인
- 별도의 `https://example.invalid/demo-egress-test` HTTPS egress 시험 요청을 발생시켜 브라우저 라우팅 레벨에서 차단되는지 확인
- Service Worker를 비활성화하고 Node browser context가 `127.0.0.1`에서 벗어나는 요청을 중단시킴

주의: 외부 연결 차단은 **CI 브라우저의 요청 라우팅 안전장치와 데모 코드 자체의 네트워크 호출 제거를 함께 검증**한 것이다. Public Vercel 보안 규칙 또는 일반 브라우저의 완전한 보안을 인증한 결과가 아니다.

## 최종 CI 근거

[GitHub Actions 39041940012](https://github.com/kimtk94/Codex/actions/runs/39041940012) — `COMPLETED/SUCCESS`

- 기존 일반 단위 테스트 207개 PASS
- 일회용 PostgreSQL 실 미러 프로세스 통합 테스트 15개 PASS
- 독립 데모 소스 검증 9개 PASS
- Chromium desktop/mobile E2E 단계 PASS
- 총 `231` unittest methods + `2` Chromium viewport scenarios; 브라우저 2회는 unittest 개수에 중복해서 더하지 않음
- 기존 17건 합성 HTTP 핸들러 시험 및 3,000개 시드 기반 현금흐름 검증은 계속 CI에서 실행됨

## 남은 블로커

1. 실제 Vercel Staging의 SSO/Password 및 DB/자격증명 격리가 미검증이며, 이번에는 배포하지 않았다.
2. 운영 메인 Vercel 배포 소스는 보호되지 않은 구버전 `v7.4.36`과 바이트 해시가 동일하다. 운영 `/api/assets` HTTP 응답은 인증된 브라우저로 검증되지 않았다.
3. Neon Production의 순수익률 과대 계산 5건은 미수정이다.
4. LIVE 서버 실행 SHA 및 Toss 주문별 수수료 통화 근거는 여전히 미확인이다.

**배포 상태: STAGING HOLD / P1 PRODUCTION HOLD. 실제 거래·Neon DML·서버 편집·Vercel 변경은 일절 수행하지 않음.**
