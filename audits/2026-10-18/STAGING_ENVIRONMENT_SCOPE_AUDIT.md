# Kalman 39차 — Vercel Staging 환경변수 범위 및 격리 감사

일자: 2026-10-18 KST
상태: **STAGING ENVIRONMENT HOLD / LIVE P1 HOLD**

## 실제 연결 프로젝트 확인

Vercel GET-only `get_project`, `filter_project_envs(decrypt=false)`, `list_project_connector_connections`을 사용했다. 변수 이름·타깃·보호 유형만 확인했으며 **비밀값은 읽지 않았다**.

- Staging `kalman-investment-hub-v2-staging`: SSO disabled, password protection disabled.
- Staging 프로젝트 변수 4개: `INVESTMENT_HUB_RUNTIME_KEY_SUFFIX` (plain), `INVESTMENT_HUB_CACHE_NAMESPACE` (plain), `BLOB_READ_WRITE_TOKEN` (encrypted), `INVESTMENT_HUB_INGEST_SECRET` (sensitive).
- 네 변수 모두 target = `production,preview,development`. 특히 Blob 쓰기 토큰과 ingest secret의 **운영과의 실제 자격증명 분리가 확인되지 않았다**.
- Main에는 8개 변수: `TOSS_GATEWAY_URL`, `DATABASE_URL_READER`, `HUB_GATEWAY_SECRET`, `INVESTMENT_HUB_RUNTIME_KEY_SUFFIX`, `BLOB_READ_WRITE_TOKEN`, `INVESTMENT_HUB_INGEST_SECRET` (production/preview 별도 레코드), `OPENAI_API_KEY`.
- Staging 및 Main Vercel connector connections = 0. 환경변수의 중복 이름만으로 동일한 실값을 사용한다고 단정할 수 없음.
- Staging에서 DATABASE_URL_READER/TOSS_GATEWAY_URL 이름이 없다고 해서 공개 Staging 환경이 완전히 안전하다고 보증할 수 없음: Blob 및 간접 API 접근, 외부 서비스 경유 가능성 별도 검증 필요.

## 구현

감사 브랜치 전용 파일:
- `audits/2026-10-18/staging_env_scope_snapshot.json`: 복호화하지 않은 변수 이름·타깃과 미확인 조건만 포함.
- `audits/2026-10-14/quality/staging_env_scope_gate.py`: 승인 이전에 권한성 환경변수가 프로젝트에 남아 있으면 무조건 STAGING_HOLD. 별도 SSO/password 및 저장소/ingest 격리 근거까지 필수. 모든 체크 통과를 가정해도 `deployment_authorized:false`.
- `test_staging_env_scope_gate.py`: 미허용 변수, 잘못된 프로젝트, 인벤토리 부재, 보호/격리 부재, 비허가 성공 등 7개 회귀 검증.
- GitHub Actions 기존 PostgreSQL·Chromium E2E와 함께 통합.

## 운영 안전판

**기존 Staging의 환경변수를 삭제하거나 이름을 바꾸지 않았다.** 비밀값을 조회하거나 비교하지 않았다. 기존 Staging에 테스트 앱을 배포하면 공통 타깃의 변수가 제공될 수 있으므로 별도 격리가 확인되기 전까지 배포하지 않는다.

다음 안전 단계는 별도 승인된 독립 Preview 프로젝트를 이용하고 **처음부터 어떤 기존 환경변수/통합도 상속하지 않는 것**, 접근 보호가 실제로 활성화되어 있는지 확인하는 것, 합성 데모 패키지로만 Preview에 배포하는 것이다. Vercel 프로젝트 생성 또는 배포는 명시적 승인 전까지 수행하지 않는다.

기존 MAIN 업로드 웹 소스는 원장 검증 전 `net_return`을 노출하는 구버전과 해시가 동일하며, Neon Production 오류 5건 역시 아직 수정되지 않았다.

**No LIVE 거래·서버 수정·Neon DML·Vercel 설정 변경·배포·GitHub main 병합.**
