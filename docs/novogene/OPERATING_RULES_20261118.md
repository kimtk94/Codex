# Novogene CSS · SFDC · Feishu 영업 자동화 운영 규칙집

> 결정 기준: 2026-11-18 KST. 이 문서는 사용자가 합의한 **업무 규칙**, 실제 원천 기반 **검증 조건**, 아직 미완료인 **구현 사항**을 분리한다. 과거 작업 완료율이나 CI 성공만으로 실데이터 최신화를 주장하지 않는다.
>
> 규칙 우선순위: 사용자의 더 최근 명시 결정 > 실제 인증된 SFDC/공식 원천 증거 > 보존된 내부 정책·검증 코드 > QQ Report/과거 사례 > 추정. 충돌·불명확한 경우 HOLD. 가격·매출·수금은 서로 다른 승인 체계로 다룬다.

## 0. 실행 환경·통제

- 영업 자동화 운영 대상: **GitHub Actions, QQ/CRM Mail, 인증된 SFDC, Google Sheets, Feishu Base, 사용자 Windows 노트북**. 별도 상시 서버는 없음. **Vercel 제외**.
- 독립 작업은 병렬 CI 실행 가능, 데이터 종속 순서는 **수집 → 스키마/ID/중복/최신성 QC → 가공 → 승인된 저장 → 원본/목적지 재조회**.
- 업무 데이터의 실제 쓰기는 대상·승인 범위를 명확히 하고 저장 전 Preview Diff, 비중복 ID, 멱등성 키, 원본 시각, 대상 테이블/권한 및 백업을 검증한다. 특정 업무에 대한 “다 저장해”는 그 업무 범위의 승인이지, 모든 향후 SFDC 저장·메일 발송에 대한 영구 포괄 승인은 아니다.
- SFDC Save와 고객 메일 발송은 별도 통제. 저장된 사실을 주장하려면 **실제 생성된 006/a0P/003 Record ID와 필드 재조회**가 필요하다. Save 후 응답 불명확 시 중복 확인 없이 재시도 금지.
- 비밀키·인증 세션·고객 상세·원본 PDF·견적 단가 JSON은 GitHub 코드/공개 로그/Actions 아티팩트/정적 웹에 올리지 않는다. Feishu/Sheets 민감 자료는 인증된 private 저장소만 사용한다.
- 불확실할 때 원본·수동 예외를 보존하고 **PASS / NO_NEW_DATA / STALE / SOURCE_UNAVAILABLE / SINK_LAG / BLOCK** 등으로 구분한다. 원본 발생·수집·저장 반영·최종 검증 시간을 별도로 기록한다.
- 실행 완료를 선언하려면 (1) 원천 최신성·완전성·ID 정합성, (2) 결과 테이블·상태·KPI의 최신 반영을 **각각** 검증한다. CI 초록색이나 시트 수정시각만으로 PASS 선언 금지.
- 반복 “다음”은 승인된 읽기/분석/테스트 등 다음 안전 단계 진행 지시이며, 새로운 범위의 비가역적 쓰기나 고객 발송을 자동 승인하지 않는다.
- 중복되거나 명백히 대체된 PR만 종료한다. 인접하지만 별개 목적의 열린 PR은 검증·대조 없이 일괄 닫지 않는다.

## 1. Salesforce Lead → Account → Contact

1. 한글 이름으로 검색하고 동명이인이면 **기관(Account)** 선택. Account 선택 시 그 소속 Contact만 표시한다.
2. 확정 관계는 **001(Account), 003(Contact), 006(Opportunity), a0P(Quotation)** Salesforce 실 ID, 링크/Related 필드와 Last Modified Date로 검증. 외부 CP/CMS ID, Display Name, QQ 제목만으로 공식 연결 금지.
3. Lead 전환은 **Don't create an opportunity**. 기존 Account/Contact·메일 중복을 먼저 확인한다.
4. Contact 이름은 한글 전체 이름을 사용하고 영어 표기는 **성+이름, 단어 첫 글자 대문자, 공백 없음**(예: OhJunHyeok). Academic은 PI, Job Function은 사용자가 정한 최상단 옵션.
5. Shipping Address는 Account 주소 복사. Lead 전환 후 Contact ID 검증 → **Sync To CDMS** → CMS Contact ID 확인. 미동기화·전환 실패는 별도 대기 상태.
6. Lead 발송 목록은 **메일 발송 여부**와 **Description 유무**를 분리한다. Description이 있으면 내용 검토 후, 없으면 공통 안내 후보. Lead 생성일과 실제 발송일 모두 기록하고, 확인되지 않은 발송을 “미발송 확정”으로 처리하지 않는다.
7. KAIST·한남대 제외는 과거 특정 **연습/검증 범위**였지 모든 영업 데이터의 전역 제외 규칙이 아니다.

## 2. Opportunity + Quotation 통합 작성

1. 기본 선택지는 **(A) Account/Contact 유지, (B) Account/Contact 변경**. 기존 Oppo 또는 Quote를 참조하면 연결된 값과 Product→Process를 사전 로드해 **변경되는 필드만** 수정한다.
2. 신규 Opportunity와 Quote는 **같은 기본 이름**을 사용하며 날짜 접미사는 붙이지 않는다. 과거 서로 다른 기존 이름은 자동 수정하지 않는다. 특정 Salesforce 화면이 최종 AMEA 접미사를 강제하면 실제 화면/사용자 지시를 재확인한 후 적용한다.
3. 신규 Close Date는 **오늘(KST) + 1개월**. 이미 Closed Won/과거 프로젝트의 일자를 복제하지 않는다.
4. Product 1개에 QC·Library·Sequencing·Analysis·Data release 등 여러 **Process**가 들어갈 수 있다. Process를 Product 개수로 잘못 변환하거나 기존 Product를 중복 추가하지 않는다.
5. 서비스·샘플 수·샘플 유형·생산량/단위(Gb, M reads, Lane, K tags, Cell/sample), 샘플당/전체 구분과 필수 전처리·분석 옵션을 확인한다. **수량과 생산량은 별도**로 관리.
6. 기존 Progress Description 복제 **금지**. 신규 고객·서비스·샘플과 **확인된 현재 단계**를 짧게 기술. 아직 발생하지 않은 Quote Issued, PO 수령, 샘플 입고, 완료 사실을 지어내지 않는다.
7. Opportunity → Related → New Quotation 우선; Quote 이름·Currency=KRW·Country=Korea·GST/VAT=10%와 실제 Product/Process를 확인한다. Opportunity에는 필수 Contact가 연결되어야 한다.
8. 동일 샘플 집합은 적합한 공정끼리 **Pack**, 클라우드 항목은 관련 서비스와 별도 취급. Coop TS 기본 담당 Yoo JiIn 지정 규칙은 해당 업무 범위 내에서만 사용하고 실제 SFDC 사용자 검색 결과 확인.
9. **Alicloud 수량 = ceil(총 Gb/100)**. 150 Gb라면 2개. Gb가 미확정이면 수량 확정 금지.
10. **Amplicon Region**별 서비스 2회 등 서비스 특수 규칙을 적용하되 원본 고객 요청/견적 공정으로 검증한다.
11. SFDC 저장 전: Account/Contact 조회 Pill과 Record ID, Opportunity/Quote 연결, 제품/공정 단가, 수량/단위/Pack/VAT, 중복, 최종 Diff 검증. 실제 Save 후 신규 객체 ID·필드·Quote 총액·Related 연결 재조회. 한쪽만 저장된 경우 PARTIAL/HOLD.

## 3. 단가·견적 근거

- **2026년·원본 KRW Process Unit Price**만 신규 단가 비교에 사용. **과거 USD, USD-converted, 환율 역산, 2025년 단가 금지**. Quote 합계나 VAT 포함 Tax Invoice를 개별 Process 가격으로 분할/역산 금지.
- 가격 참고 순위: (1) 같은 001 Account+003 Contact, (2) 같은 Account·다른 Contact, (3) 다른 고객의 동일 Product fingerprint+Process ID+Data Unit 및 생산량/수량 호환 조건. 다른 고객의 특약/할인 자동 승계 금지.
- 과거 Quote의 **Active=true, 승인 근거, Currency=KRW, native 관계 ID, 프로세스별 단가·수량·합계, VAT basis**를 검증. 기존 가격은 비교 후보이지 신규 견적의 자동 확정 가격이 아니다.
- QQ 25열 Quotation Report의 단가는 USD 표시이며 **native KRW 공정 단가가 없다**. 반면 인증된 SFDC Quotation Detail에서 원본 KRW를 별도로 읽은 **2026-11-16 시점 46개 Quote / 197개 Process / 36 Product fingerprints**의 private 비교 자료는 존재한다. 이는 **2026년 전체 추출이 아니다**. 해당 자료와 신규 견적의 원본/승인 상태는 다시 확인한다.
- 0원 포함 Process는 세트 내 번들일 수 있으므로 일반적으로 무료라고 간주하지 않는다. 미승인·비활성·공정/VAT 불일치·관계 모호한 Quote는 비교 인덱스에서 HOLD.

## 4. Mail 수집·Lead follow-up

- 원본은 QQ INBOX/SENT 및 권한 확인된 CRM 원문. **mailbox + folder + UIDVALIDITY + UID** 또는 안정적인 ingest key로 중복 방지. 수신일, 발신자, 본문, 첨부, Message-ID, 회신 관계와 실제 수집시각을 구별해 보존.
- 사용자의 본인 QQ 메일과 **jiin.yoo@novogene.com** 메일은 소유권이 다르다. Jiin 계정에서는 **발신자 crm@novogene.com 정확 일치** 대상만 별도 수집하며, 이 메일을 본인 Contract 생성의 증거로 쓰지 않는다.
- Follow-up은 Unfollowed Lead와 Unanswered Email 원본을 분리한 후 고객 단위로 합친다. 전송 확인/회신/대리회신/수동 제외/이미 해결된 건을 고려한다. **미확인=미회신 확정 아님**.
- Tax Invoice 원본 메일은 **원 발행 공지**(예: Invoice Issued & Statement Confirmed)를 우선하고, 회신/전달/제목만 비슷한 메일은 발행 증거로 보지 않는다. 한 메일에 여러 Invoice ID가 있을 수 있으므로 **invoice_number 단위**로 별도 색인.
- 신규 메일이 없는 정상 상태와 수집 실패는 다르다: QQ 원본 UID↔Sink 대조로 NO_NEW_DATA와 SINK_LAG 판정. 원문/본문/첨부 수집 완전성과 헤더 수집 성공도 다른 단계.
- 원본 메일 저장소와 SFDC/Feishu 가공 테이블은 분리. 과거 메일 백필은 체크포인트 재개·유실 방지·범위/수집 건수/수신함·보낸함 분리 및 source/sink UID 대조를 요구. **60일/2026 전체 coverage는 추정 금지**.

## 5. Contract / PO / SIF / 프로젝트

- **본인 Contract 생성 확인은 본인 메일만**: 신뢰된 CSS/CRM 발신자, 원본 Contract Ready/Created 공지, 제목 내 유일 프로젝트 ID로 확인. 타 영업 담당이 혼합된 CRM mail은 PO/Final Report 등 **후속 증거**로만 활용 가능.
- Contract 확인 이후 PO follow-up 시작. PO 메일은 복수 수신될 수 있고 본문 검토도 필요하지만, 관계 연결은 정확한 프로젝트 ID로 검증.
- 실제 PO 파일 확인은 검증 상태·파일 참조·검증일시·검증자를 모두 기록. **PO Status(메일)와 PO Document Verification(파일)을 분리**한다.
- Contract 후 **Final Report 또는 Statement 원본 공지**가 있으면 PO가 제출된 것으로 **follow-up상 추정**하여 PO 미제출 목록에서 제외하되, 실제 파일 검증 완료와 동일하게 표기하지 않는다. 이후 모순된 PO 미수령 증거는 REVIEW.
- **Prepayment 목록에서는 SIF 제출이 필수가 아님.** SIF 미제출만으로 반복 알림 금지. SIF 제출이 확인되면 기록하고 Sample Received → QC → Library → Sequencing → Data Ready → Final Report 등 실제 후속 단계로 이동한다.
- 프로젝트 식별은 **X/SAM/AMEA/H 관계를 검증**해 키 충돌·복수 프로젝트를 방지한다. 하나의 AMEA 번호만으로 일대일 프로젝트를 가정하지 않는다.
- 진행 중 프로젝트와 완료/결제 프로젝트는 별도 관리. Quote Full Name은 사용자-facing 주요 검색 키. 프로젝트 진행률·상태는 원본 단계와 근거 시각으로 계산.
- 2026-11-18 검증 스냅샷: **Lifecycle 111 프로젝트(유일 ID 111), 주요 원본/저장 필드 차이 0**, 11월 Statement 금액 미확인 2건. 이 수치는 **고정 운영 규칙이 아닌 당시 실측 상태**.
- Feishu Project Progress Board의 **405 원본 프로젝트**와 위 **111개 lifecycle**은 별개 데이터 범위. Active 66 / Billing 112 / 본인 Scope의 Archived 0 / 범위 밖 227은 당시 **Payment Owner Scope 보기 필터** 결과이며, 원본 삭제/전사 결제완료 0건이라는 뜻이 아니다.

## 6. Invoice / Payment / Revenue

- **확정 Actual Revenue는 원본 Tax Invoice 발행 증거만** 기준으로 인정. **Revenue=VAT 제외 공급가액**, **Tax Invoice=VAT 포함 청구금액**. 세금계산서 건별 공급가액 산정 후 월별 합계; 역산 오차·중복 Invoice ID 검사.
- Quote 승인/금액, Opportunity Amount, Forecast, Pending, Statement, Contract, PO, 입금/Payment는 각각 다른 의미. **Invoice Issued ≠ Paid**, **Statement ≠ 확정 Invoice**, **Pending ≠ Actual**.
- Confirmed Invoice는 원 공지·invoice_number·원본 첨부파일명·실제 발행일·KRW 금액·중복/정합성을 검증한 후 월별로 귀속. 회신/전달/예측/수동 ERP/eTax 근거는 원본 QQ Tax Invoice 확정 KPI에 섞지 않는다.
- Pending은 Statement 금액 근거와 VAT 기준을 검증한 경우에만 Verified Pending으로 별도 표시. **금액 없는 Statement는 UNKNOWN/PENDING으로 남기며 0원 발행·수금 처리하지 않는다.** 발행 예정(예: Confirmation 이후 5일)과 발행 완료를 혼동하지 않는다.
- Actual, Verified Pending, Forecast, Unknown Statement를 구분하고 각 월별 **Invoice 건수, VAT 포함 실제, VAT 제외 Revenue, Open Statement, Forecast**를 별도로 표시한다.
- 과거 매출 월 원본/증빙·수동 데이터는 무조건 삭제 금지. 확정 Actual/Statement 근거가 없는 **오래된 Forecast-only 월**은 원본 검증 후 0원 퇴역 이력으로 보존할 수 있다.
- 2026-11-18 실제 대사 스냅샷: 10월 **48건 / VAT 포함 158,541,900 KRW / VAT 제외 144,129,000 KRW**, 11월 **25건 / VAT 포함 84,216,550 KRW / VAT 제외 76,560,500 KRW**; 11월 확인되지 않은 Statement **2건**은 제외. Feishu canonical 2개월 2/2 일치, 기존 다른 11개월 기록 보존. **수시로 재검증할 실측치이며, 고정 룰이 아님.**
- Payment는 **본인 담당만 표시**, 독립된 은행/ERP 수금 증거가 없는 항목은 Paid로 확정 금지. 유효한 Invoice만으로 Outstanding/입금완료를 추정하지 않는다.

## 7. Feishu BI 및 표시

- 숫자는 의미에 따라 형식 통일: **Quote/Invoice 건수 정수(.0 없음)**, KRW 금액은 **M KRW**, USD 금액은 **K USD**. **신규 견적 단가는 KRW만**; 보고서의 USD K 표시와 혼동 금지.
- 데이터 자체가 없는 값은 **0이 아니라 ‘-’/No value**; 실제 0은 0.
- Weekly Quote는 승인 기준 명세와 원본 목록을 함께 제공. **‘합산 제외’ 체크 시 화면/합계에서 즉시 제외**, 원본 행이나 감사 이력은 삭제하지 않는다. 계산 예외와 승인 건수/금액을 분리.
- Monthly Revenue 그래프 아래 개별 실측 리스트도 표시하고 Invoice VAT gross와 VAT net Actual을 분리. Payment/Online/Monthly 등 원본별 처리 workflow/상태·마지막/다음 실행 시각을 표시.
- 완료 프로젝트는 진행 중 보기에서 숨기고 Payment 관리로 이동; 원본은 보존. 본인 Payment Owner Scope 필터를 유지. 전체 405건이 본인 보기로 보이지 않는 것은 누락 증거가 아님.
- 영업 홈의 모든 바로가기는 실제 유효 링크로, 실행 가능한 테이블은 수정·팝업·재검증이 가능하게. 숨긴 시트/뷰는 백업·원본 로그를 삭제하지 않는다.
- Feishu Base에서 **운영 테이블 스키마 PASS**와 실제 업무 값/Freshness PASS를 분리. 과거 Bootstrap 테이블 6개가 보이지 않는 현상만으로 현재 운영 테이블을 삭제되었다고 단정하지 않는다.

## 8. Actions·품질 게이트·알림

- 9개 업무 흐름을 독립적으로 점검: **Mail / Lead·Contact / Oppo·Quote / Contract·PO / SIF·Project / Tax Invoice / Payment·Revenue / Feishu BI / 운영 모니터링**. 각 흐름에 원천 검사와 결과 검사 **2개의 독립 게이트**.
- GitHub Actions는 가능한 한 독립 파이프라인으로 분리. 동일 시트·월·테이블을 두 Writer가 동시 수정하면 안 되며, **공유 Lease/멱등성/중복 방지**를 사용한다. 서로 다른 workflow의 concurrency group은 상호 배타를 자동 보장하지 않는다.
- 원본 Read 실패는 SOURCE_UNAVAILABLE, 최신성 임계 초과는 STALE, 원본에는 있지만 목적지 누락은 SINK_LAG, 변화 없는 정상 상태는 NO_NEW_DATA, 확인 불가/금액 모호는 BLOCK. **SUCCESS는 source/sink parity 확인 후**.
- 운영 대시보드/로그는 시작 → 수집/정리 → 저장 → 재검증 → 완료/차단 및 **원본 이벤트시각, 수집시각, 목적지 반영시각, 검증시각, 미반영 건수와 증거 링크**를 구별.
- 독립적 read-only GET은 제한 재시도 가능. **POST/PUT/PATCH/DELETE는 맹목적 재시도 금지**, 기록 존재 여부를 먼저 확인한다.
- 대규모 수정 전 원본 백업, 검증 가능한 aggregate diff와 정확한 실측 Snapshot. 고객/금액·시크릿을 공개 Actions 로그에 인쇄하지 않는다.
- 테스트 단계는 **소스 점검 → 오프라인 단위 테스트 → 원본 읽기 및 비교 → 승인된 Save → 재조회 → BI 검증**. No-Save CI만 통과하면 실제 SFDC Save가 되었다고 표시하지 않는다.

## 9. 현재 미완료 / 별도 증거가 필요한 항목

- 2026 QQ 전체 INBOX/SENT의 **과거 UID/본문/첨부 수집 완전성** 및 모든 과거 Invoice 발행 증거. 최근 Source→Sink PASS가 전체 역사적 coverage를 의미하지는 않음.
- **Statement 2건**의 정확한 금액·VAT 기준·발행/결제 상태 확인.
- 전체 2026 SFDC **승인 KRW 공정 단가** 커버리지, Account–Contact·Oppo–Quote 관계와 SFDC 실제 Save의 건별 실행 결과.
- 고객 메일 **실제 자동 발송** 및 Salesforce Save는 별도 승인·ID 재조회·권한 E2E가 필요.
- 월별 VAT net Revenue 갱신 순서를 **lifecycle → VAT net → Revenue Source Authority → Feishu canonical → 독립 검증**으로 오케스트레이션해 원천 시각이 어긋나지 않게 할 것. 현재는 각 단계의 수동 실행 PASS가 확인됐다고 해서 전체 영구 자동 연동이 검증된 것은 아님.

## 10. 규칙 충돌 해결 메모

1. **Quote 이름:** 최근 사용자 결정 “Oppo=Quote 같은 기본 이름, 날짜 없음” 우선. 초기 로컬 설계의 “Quote 이름에 AMEA suffix”는 **최종 AMEA가 필수인 특정 화면에서만 검토**, 기본 자동 접미사 아님.
2. **KRW 가격:** “QQ Report에는 native KRW가 없음”은 참이지만 “2026 KRW 가격 원본 전체가 없음”은 아님. 검증된 Salesforce local KRW 일부 코퍼스는 존재. **전체 가격표로 확정 금지**.
3. **USD:** 새 **가격단가 재사용 금지**와 KPI의 **K USD 보고 표시**는 별개.
4. **111 vs 405:** 서로 다른 테이블 범위와 owner scope. 강제로 합산하거나 프로젝트 삭제·완료로 해석하지 않음.
5. **승인 상태:** 특정 수집/정합성 복구의 실제 저장 허가가 있었더라도, 이후 새로운 고객·Quote 생성이나 메일 발송은 별도 승인 게이트 유지.

## 11. 근거 문서·감사

- [2026 KRW Process pricing](../sfdc/QUOTE_2026_KRW_PROCESS_PRICE_REUSE.md)
- [인증 SFDC KRW 가격 부분 검증](../sfdc/2026_KRW_NATIVE_READBACK_PILOT.md)
- [Oppo–Quote 공통 패턴](../sfdc/OPPO_QUOTE_POPULAR_PATTERN_LEARNING_20261115.md)
- [신규 작성 최소 입력](../sfdc/OPPO_QUOTE_NEW_REQUEST_INPUT_GUIDE_20261115.md)
- [원본 Mail 단일 소스](../../automation/css_mail/MAIL_SINGLE_SOURCE_POLICY.md)
- [PO 증빙 판정](../../automation/feishu/PO_FILE_VERIFICATION_GUIDE.md)
- [쓰기 안전 정책](../automation-architecture-20261026/WRITE_SAFETY_POLICY.md)
- [Workflow 의존성](../automation-architecture-20261026/WORKFLOW_DEPENDENCIES.md)
- 2026-11-18 프로젝트+Revenue 독립 검증: https://github.com/kimtk94/Codex/actions/runs/44240176652
- Source→Sink 최신화 incident / 후속 설명: https://github.com/kimtk94/Codex/issues/834

> 사용 지침: 향후 자동화나 웹 기능을 변경할 때 이 규칙집을 사전 체크리스트로 사용하되, 실시간 원본·사용자 최신 지시·인증된 CRM 필드와 충돌하면 **자동 적용 금지 / HOLD**. 이 문서 자체는 쓰기 승인 또는 모든 파이프라인의 구현 완료 증거가 아니다.
