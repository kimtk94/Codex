# Kalman 36차 — Synthetic-only Staging 독립 화면 강화

일자: 2026-10-17 KST
판정: **231 TESTS PASS / ISOLATED DEMO BOOT PASS / STAGING HOLD / P1 PRODUCTION HOLD**

## 이번 단계에서 실제 확인·수정한 내용

기존 35차 데모는 11개 API를 차단하고 Health를 모의 구현했지만 원래 거래 화면의 `app.js`를 계속 포함했다. 외부 네트워크 차단 및 비활성 API만으로 잘못된 거래 화면 표시를 완전히 배제할 수 없으므로, 감사 브랜치의 `audits/2026-10-14/quality/build_demo_only_staging.py`를 강화했다.

- 기존 거래 화면 `index.html`, `app.js`, `style.css`를 자체적인 가상 데모 진입점으로 완전히 교체했다.
- 데모 화면에는 계좌/거래/시장 연결이 **DISABLED**, 순수익은 **UNVERIFIED — HIDDEN**으로 명시되어 있다. 화면에 매수/매도 버튼이나 계좌 인증 입력이 없다.
- 독립 `app.js`는 데모 DOM의 상태 문구만 갱신하며 `fetch`, XHR, WebSocket, EventSource, 브라우저 저장소 또는 거래용 모듈을 실행하지 않는다.
- 11개 기존 백엔드 API는 비활성 응답을 반환하며 1개는 가상 Health GET만 허용한다. 10개 라이브러리를 비활성화하고 정적 JSON 3개를 가상 마커로 교체한다.
- CSP, noindex/no-store, 동일 출처 rewrite 제한은 유지한다. 생성물의 전체 30개 파일과 정확한 HTML/JS/CSS 문자열을 검증해 보호 로직이 변경되면 실패하도록 했다.
- 별도 Node.js VM 테스트에서는 실제 생성된 데모 `app.js`가 가상 DOM의 상태를 갱신하는지, 비활성 API와 모의 Health 핸들러가 올바른 상태를 돌려주는지 검증한다. 이는 **실제 Chromium/browser E2E 또는 운영 HTTP 스모크가 아니다.**
- 데모 패키지는 GitHub CI 내부 임시 디렉터리에만 생성했다. Vercel 업로드/프리뷰·환경변수 설정 변경·API 호출·거래 실행·Neon DML은 없다.

## 검증 기록

GitHub Actions: https://github.com/kimtk94/Codex/actions/runs/39041598219
- 207 기존 단위 테스트: PASS
- 15회 일회용 PostgreSQL 미러 통합 테스트: PASS
- 독립 데모 9개 테스트: PASS
- 총 231개 unittest 메서드: PASS
- 전체 v7.4.36 보호 후보 빌드: `OFFLINE_BUILD_PASS_RELEASE_HOLD`
- 독립 데모: `DEMO_ONLY_SOURCE_VERIFIED_NOT_DEPLOYED`
- 독립 데모 SHA-256 content digest: `3c80af7705eef30f0e786b1551e590907a5bbb4dd1602d3433cb7453987efb74`
- CI 첫 시도는 원래 테스트의 이전 성공 메시지 기대값이 남아 실패했으며, 테스트 기대값을 수정한 뒤 위 최종 CI에서 전체 PASS를 확인했다.

## 남은 블로커
1. 기존 Staging의 SSO/password 보호가 비활성화되어 있고 자격증명·DB 격리가 검증되지 않았음.
2. 실제 브라우저 렌더링과 CSP 네트워크 동작, Vercel 프리뷰 런타임은 아직 실행 검증되지 않았음.
3. 현재 MAIN 운영 웹 업로드 소스는 과거 보호되지 않은 `v7.4.36`과 SHA-1 동일하며, 실제 브라우저/HTTP 응답은 미확인.
4. Neon Production 과대 계산 순수익률 5건을 정정하지 않았음.
5. 안전한 Staging 배포는 명시적 별도 승인 이후 진행.

**배포·LIVE 서버·실거래 설정은 변경하지 않았다.**
