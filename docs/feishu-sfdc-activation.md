# Feishu Base → SFDC 실행 기능 활성화

## 현재 Health Check (2026-11-09 KST)
- GitHub Feishu 기존 읽기 동기화: PASS
- SFDC 요청 큐 코드 및 테스트: PASS
- PC 로컬 소비자 및 100Gb AliCloud 검증 테스트: PASS
- 신규 Base 테이블 생성: BLOCK, HTTP 403 (앱 쓰기 권한/해당 Base 접근 확인 필요)
- Feishu 웹앱 메뉴/폼 게시: NOT DEPLOYED
- Feishu → 실제 Salesforce 저장 → Feishu 회신 E2E: NOT VERIFIED

## Feishu 관리자가 허용할 작업
1. 기존 Feishu Open Platform 앱에 **View, comment, edit and manage Base** (`bitable:app`) 쓰기 범위를 허용하고 필요한 앱 버전을 승인/게시.
2. 앱이 기존 업무 Base를 편집할 수 있도록 문서/데이터 테이블 권한 부여. 일반적인 읽기 권한만으로는 신규 테이블/레코드 작성 불가.
3. GitHub workflow `Feishu SFDC Command Queue Bridge`를 수동 `bootstrap`으로 실행. `SFDC_COMMAND_QUEUE` 테이블 및 필드 생성, 1회 재조회 검증.
4. Feishu Base App 편집 화면에 `SFDC_COMMAND_QUEUE` 테이블의 요청 입력 뷰/상태 뷰를 추가. 일반 사용자에게 필요한 요청 필드만 보이고, 상태/생성 ID/오류/타임스탬프 필드는 읽기 전용으로 분리.
5. 인증·쓰기·값 재조회가 PASS이면 GitHub Environment/Repository variable `FEISHU_SFDC_BRIDGE_ENABLED=true`로 10분 주기 동기화 활성화.

## 요청 데이터 계약
- `Action`: `LEAD_CONVERT` 또는 `OPPO_QUOTE_PAIR`.
- `Source Oppo ID`, `Source Quote ID`, `Lead ID`: 기존 Salesforce 레코드 ID.
- `New Opportunity Name`, `New Samples`, `Data Size Gb`: 변경값.
- `Approval=PREFLIGHT`, `Run Mode=CHECK`: 저장 없이 사전 검증.
- `Approval=APPROVED`, `Duplicate Checked=YES`, `Price Checked=YES`, `Run Mode=SAVE`: 사용자 승인 요청.
- `Status`: NEW/QUEUED → RUNNING → PREFLIGHT_PASS/PREFLIGHT_BLOCK/PASS/PARTIAL/BLOCK.
- `New Oppo ID`, `New Quote ID`, `New Contact ID`: 실제 저장 후 재조회로 확인된 경우에만 기록.

## 보안 및 정확성 경계
- GitHub Actions는 Salesforce에 로그인하거나 저장하지 않음. 기존 Feishu 비밀키는 환경 Secret으로만 사용.
- PC의 SFDC CDP 인증은 외부로 반출하지 않음. 로컬 소비자는 private Sheet를 통해 큐를 조회하고 결과를 회신.
- 로컬 소비자는 자동 재시도를 하지 않으며, `RUNNING` 클레임을 남겨 중복 저장 방지.
- `OPPO_QUOTE_PAIR`의 실제 SAVE는 **Cloud 공정 수량 쓰기 + 새 Quote 금액 재조회**가 구현/검증되기 전까지 차단. 잘못된 Cloud 수량을 가진 Quote나 고아 Opportunity를 생성하지 않음.
- 기존 Quote의 검증된 공정 단가만 사용하고, Cloud 수량은 `ceil(samples × per_sample_Gb / 100)`.
- Feishu 외부 공개, Vercel, Salesforce 로그인 정보/고객 원문 로그 노출 없음.

## 코드 경로
- `automation/feishu/sfdc_command_queue.py`
- `masteros/web/scripts/feishu_sfdc_local_worker.py`
- `.github/workflows/feishu-sfdc-command-queue.yml`

## 다음 확인
수동 bootstrap이 성공한 뒤에만 PC 로컬 소비자를 반복 실행하도록 등록. 요청 1건을 `CHECK` 모드로 먼저 검증하고, 반드시 결과가 Feishu 행으로 돌아오는지 확인.
