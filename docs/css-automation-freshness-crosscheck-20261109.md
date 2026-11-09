# Novogene CSS 자동화·최신화 교차점검 운영 기준 (2026-11-09)
 
**범위:** GitHub Actions, QQ/CRM 메일, SFDC, Feishu. **Vercel은 제외.** 이후 기능 추가·업데이트·데이터 갱신 전후 이 기준과 `automation/ops/css_freshness_policy.json`을 재확인한다.

## 완료율을 구분하는 5개 단계
1. 구현: 코드 존재/단위 테스트.
2. 자동 실행: GitHub Actions 트리거·실행.
3. 원천 최신화: 실제 원천 조회 성공과 신규/변경 이벤트·완전성 확인.
4. 목적지 반영: 결과 시트/Feishu/SFDC readback과 ID·건수·금액 정합성.
5. 업무 수용: 필요한 경우 실제 SFDC 저장, 고객 발송, 입금 확인을 권한과 증빙으로 확정.

**CI SUCCESS 또는 시트 동기화 시각만으로 3~5단계를 PASS 처리하지 않는다.** 각 기능마다 독립된 **원천 체크 A + 목적지 체크 B** 두 포인트를 유지한다.

## 9개 기능 × 교차 검증 2개 = 18개
| 기능 | 자동화 상태(코드/증빙 기준) | A. 원천 최신화 | B. 반영 최신화 | 참고 Workflow |
|---|---|---|---|---|
| 메일 수집 | 운영 경로 존재; 원본 전체 커버리지 별도 검증 | QQ/CRM 원본 UID·Message-ID·MIME 본문과 수신 시각을 커서/해시·누락 건수와 비교 | 목적지 Ledger 마지막 UID·본문 준비/오류 카운트와 원본 집합 비교 | `css-raw-mail-checkpoint-health.yml` |
| Lead·Contact | 부분 자동화; SFDC 실저장 별도 검증 | 본인 메일·SFDC Leads/Contacts 최신 Report 원본 ID·기관·성명·수신 시각 검증 | Lead/Contact 고유 ID와 전환·Sync To CDMS readback, 동명이인/기관 중복 검증 | `lead-sent-audit-validation.yml` |
| Opportunity·Quote | 부분 자동화; Save 미확인 건 HOLD | SFDC Oppo·Quote Report 최신 원본 ID·승인시각·기존 Product Catalog 검증 | Contact–Oppo–Quote 연결, 서비스·샘플수·단가·KRW/USD 및 Weekly Quote 원천 합계 대조 | `quote-weekly-source-parity.yml` |
| Contract·PO | 자동 추적; 원본 PO 파일은 구분 | 본인 QQ의 계약 생성 메일만 소유권 인정, 프로젝트 식별자 및 이벤트 순서 교차 확인 | PO_REQUIRED/FILE_VERIFIED/INFERRED 분리, 계약 후 Final Report·Statement 추정과 실제 파일 readback 분리 | `contract-po-tracker.yml` |
| SIF·프로젝트 단계/TAT | 부분 자동화; 단계별 확인 필수 | CRM 공정/샘플/SIF 알림과 Online Project 날짜·ID 검증, Prepayment SIF 미제출 독촉 금지 | 프로젝트 공정·진행률·예상월/override를 원본과 비교, AMEA 다중 프로젝트는 SAM/계약 보조키 대조 | `feishu-project-sync.yml` |
| Tax Invoice | 원본 메일 증빙 기반 집계 자동화 | 본인 QQ 원본 Tax Invoice UID·첨부 파일명·발행일·계약·VAT 포함 금액 검증 | Invoice 고유키·원본 금액·세액·중복·상대 계약 확인, 타 고객 연결 시 BLOCK | `css-qq-tax-invoice-mail-only-audit.yml` |
| Payment·Monthly Revenue | 월별 매출 자동 집계; 입금 확정은 별도 | 발행 Invoice 원본과 Payment Receipt/Outstanding 원천 날짜 확인, Invoice≠입금증빙 | 월별 VAT 제외 Revenue·Invoice 수량과 VAT 포함 원본 대조, Pending/Forecast/입금 분리 | `feishu-canonical-monthly-revenue.yml` |
| Feishu BI·Weekly KPI | 자동 대시보드 갱신; 실데이터 정합성 필요 | Quote 승인·Invoice·프로젝트 원천별 이벤트 watermark/원본 집합 및 주간 기준 확인 | Feishu 카드·주간 건수/금액·월별 매출 readback, KRW M/USD K·정수 표시·누락 확인 | `feishu-native-kpi-dashboard.yml` |
| GitHub Actions 운영 | 정기 CI와 상태 ledger 운영 | 최신 main run/job 단계별 결론·검증 대상 원천 이벤트 시각 확인, 이전 SUCCESS로 실패 덮지 않기 | 원천 조회/수집/목적지 readback/검증 시각 및 상태를 ledger에 분리 기록 | `css-central-workflow-health.yml` |

## 상태 판정
| 상태 | 판정 규칙 |
|---|---|
| `PASS` | 인증된 원천 조회 성공, 변화분 식별, 목적지 readback 성공, ID/금액/건수 차이 0 |
| `NO_NEW_DATA` | 인증된 조회 성공, 신규 0건, 누적 차이 0, 목적지 readback 성공 |
| `STALE` | 기능별 원천 조회 기대 주기 초과. 이벤트일이 오래됐다는 이유만으로 확정하지 않음 |
| `SOURCE_UNAVAILABLE` | 원천 접근·인증·응답 장애. 빈 결과/0건으로 변환 금지 |
| `SINK_LAG` | 원천 확인됐지만 목적지 누락·반영 지연·readback 실패 |
| `BLOCK` | ID·소유권·계약·VAT/금액 충돌, 증빙 누락 또는 최신성 판정 불능 |

### 필수 로그
각 체크마다 `source_event_at`, `source_probe_at`, `ingest_at`, `sink_readback_at`, `verified_at`, `source_identity`, `source_count`, `sink_count`, `gap_count`, `source_ref`, `sink_ref`, `run_url` 기록. 민감한 본문·계정 비밀번호는 제외하고 원본 식별자는 필요시 해시·집계로 보관. **기능별 cron/송신 빈도에 따른 최신화 허용 시간**을 명시하며 임의의 공통 24시간 기준을 적용하지 않음.

### 업무별 중요한 경계
- Revenue=실제 발행 Tax Invoice 근거의 VAT **제외** 금액, 원본 Invoice=VAT **포함**. 입금 Payment / Pending / Forecast / Quote는 별개. KRW는 M, USD는 K 단위; 정수에 .0 제거.
- PO는 본인 QQ 메일로 확인된 Contract 생성 이후 대상. Jiin 공용 CRM의 Contract는 본인 소유 확증 아님.
- PO 원본 파일 검증은 `FILE_VERIFIED`로, Contract 후 확정된 Final Report/Statement는 `INFERRED`로 구분. 문서 제출을 추정하더라도 증빙 없는 파일 검증으로 승격하지 않음.
- Prepayment 프로젝트의 SIF 미제출은 자동 반복 팔로업 금지. SIF가 접수되었으면 이후 공정 단계로 진행.
- AMEA 단독 식별이 중복 가능하면 SAM·계약번호·서비스/시료 보조키를 추가하고, 미해결시 REVIEW.
- 웹 Production/Preview, 고객 메일 발송, SFDC Save, 입금 확정은 CI 통과만으로 수행/승인했다고 표시하지 않음.

## 실측 스냅샷 — 2026-11-09 00:20 KST 근방 (이후 재조회 필요)
- Feishu Source Manifest: Online-Project 원천 날짜 2026-11-09 / Payment Outstanding 2026-11-01 / eTax Invoice, Payment Receipt 2026-10-31. 모두 11/09 00:19에 동기화돼도 원천에 그동안 변화가 없었는지는 추가 점검 필요.
- SFDC 3 Reports: 11/08 17:00 원본, 22:22 수집 감사; Leads 515개 unique 515, Opportunity 706 unique 706, Quotation 3883 rows/838 unique. `STAGED_NOT_PROMOTED`이므로 실 SFDC 객체 상태 확정 아님.
- Revenue Source Authority: 2026-10 VAT 제외 ₩144,129,000 / 48 Invoice, 2026-11 ₩45,040,500 / 7 Invoice (11/08 22:21 감사 시점). 최신 값이라는 보증 아님.
- 11/08 22:53 Body cache: body_ready=4176, remaining=0, errors=0. 전체 QQ 메일함 커버리지 증거와는 별개.
- [CSS P0 Parallel run 42494201108](https://github.com/kimtk94/Codex/actions/runs/42494201108): **FAILURE**. 2c(Invoice owner/receipt)·2d(source evidence exceptions) job 실패. 독립 작업 성공으로 실패를 숨기지 말 것.

## 이후 모든 업데이트에서 재사용할 절차
1. 이번 변경 대상 기능을 9개 중 선택, 최근 원천 조회 ID와 이벤트 날짜·수집 상태를 확인.
2. A(원천 최신화)와 B(목적지 readback)를 **각각 실제 증빙**으로 검사. 원천 접근 실패와 신규 0건 구분.
3. ID·건수·금액·기준 월·VAT·중복을 교차대조. 지연/불일치 건을 고유 ID별로 분리하고 삭제·임의 보정 금지.
4. GitHub Actions를 통한 정적 회귀검사와 원천 워크플로를 확인하고, **job별 실행 결과·원본 시각·증빙 링크** 기록.
5. 구현·자동 실행·원천 최신화·목적지 반영·업무 수용을 별개 진척도로 갱신. 9개 기능×18개 포인트의 PASS/REVIEW/BLOCK/미검증 건수와 남은 작업 수 기록.

**정적 정책 검사:** `.github/workflows/css-freshness-policy-check.yml` — 9개 기능과 18개 검증 포인트·상태 계약이 유지되는지 검사. **실제 최신 원천 데이터 검사까지 했다는 의미는 아님.**

참고: [SFDC_Automation_Followup_2026](https://docs.google.com/spreadsheets/d/1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI/edit) / [Novogene_All_Emails](https://docs.google.com/spreadsheets/d/1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY/edit).


## 2026-11-09 08:38 KST: 실제 원본 최신화 교차검증 (PR #643–#645)

- **직접 조회 구현:** `automation/ops/css_authenticated_original_probes.py`. 로그인된 QQ IMAP INBOX/SENT UIDVALIDITY 및 UID 집합을 별도 조회해 Google `CSS Git Ingest`의 고유키 집합과 비교. Feishu 원본 4종 dated Sheet도 직접 읽어 source sheet ID/일자, 모든 투영 행·셀과 Google mirror를 비교. **고객 내용·개별 UID는 로그/증거에 기록하지 않는다.**
- **실행 증거:** [GitHub Actions #42536011134](https://github.com/kimtk94/Codex/actions/runs/42536011134) (main, 오프라인 테스트·mirror·original job 성공, 단 업무 전체 PASS 아님). 원본 인증은 QQ 및 Feishu 모두 성공.
- **QQ 전체 메일함 차이:** IMAP UID 기준 미적재 **34,558건**, 이 중 **최근 3일 6건**, **최근 60일 6건**, **60일 이전 역사적 미적재 34,552건**. 원본 대비 staging 범위 차이로, 이 34,552건을 현재 3일 최신화 장애로 잘못 표시하지 않는다. 다만 60일 범위의 6건은 실제 해당 시점의 `SINK_LAG`이며 다음 CSS QQ Mail 원본 수집 실행·readback 후 0건인지 재검증한다.
- **Feishu 원본 대조:** dated Payment Outstanding, Payment Receipt, Prepayments, eTax Invoice의 원본 전체 투영 내용과 Google mirror의 ID·일자·행 수·컬럼·값 대조 `PASS`. **eTax 최신 dated 원천일은 여전히 2026-10-31.** 11월 eTax 발행 증빙·실제 bank paid 확정은 불가.
- **SFDC:** 3 Report QQ 메일 적재는 별도 검증되지만 Salesforce 객체의 Save/readback은 이 직접 프로브 범위가 아니므로 미인증으로 남는다.
- **자동 실행:** `.github/workflows/css-live-freshness-evidence.yml`에서 PR 테스트 + main push/매일 KST 04:12, 10:12, 16:12, 22:12 원본 읽기·증거 artifact. PR #645에서 원본 프로브 파일 변경도 main push 트리거에 포함하도록 수정.

### 이후 운영 점검 순서
1. 우선 최근 3일 IMAP↔Google staging UID 누락 건수와 메일 본문 캐시 별도 점검. 6건이 다음 수집 후에도 남으면 UIDVALIDITY/폴더/실제 원본 수집 실패 원인 추적.
2. 최근 60일 차이와 60일 이전 **역사적 백필**을 별도 KPI로 보고. Feishu 2026 백필과 Google 60일 수집은 서로 다른 수집 경로이므로 수치를 합치지 않는다.
3. Feishu dated 원본 원본↔미러 전체 콘텐츠 PASS와 **최신 발행 Invoice/입금증빙 PASS는 별도**. 최신 eTax source date가 10/31이어도 원본 자체에 신규 데이터가 없는 정상 상태인지 확인 전에는 임의로 STALE/PASS 확정하지 않는다.
4. SFDC 실제 Save와 Quote 승인·KPI readback은 독립 확인. Monthly Revenue는 VAT 제외 발행 QQ Tax Invoice만 authoritative actual로 취급.


## 2026-11-09 09:03 KST: QQ 신규 메일 재수집 후 직접 검증

- [PR #647](https://github.com/kimtk94/Codex/pull/647): QQ 최근 3일 누락 UID를 `INTERNALDATE`와 `CSS Git Ingest.fetched_at_utc`로 교차검증. 09:00의 최근 3일 누락은 **9건 전부 마지막 수집 체크포인트 이후 도착**, 이전 수집이 놓친 메일 **0건**으로 판정. 이 판정은 제목·본문·개별 UID를 출력하지 않고 집계만 공개함.
- QQ 수집 GitHub Actions [#42529997566](https://github.com/kimtk94/Codex/actions/runs/42529997566)의 **css-mail job 재실행** 성공. 기존 `CSS Git Ingest`에 신규 9행이 append된 것을 직접 readback 확인 (UID 원문 비공개 운영 증거로 유지).
- [original source 재검증 #42537764294](https://github.com/kimtk94/Codex/actions/runs/42537764294): 2026-11-09 09:03 KST 원본 QQ IMAP INBOX/SENT 재조회 성공, 최근 **3일 gap=0**, 최근 **60일 gap=0**, 60일 이전 과거 backlog **34,552** 유지. 마지막 수집 `2026-11-09T00:01:15.188389Z`. 상태 `PASS_UID_ONLY`이며 MIME/body/첨부·전체 역사적 백필의 PASS는 아님.
- Feishu 원본 4종 dated Sheets와 Google mirror 대조는 재검증에서 PASS. 최신 eTax dated 원천은 **2026-10-31**로 11월 eTax issuance/Payment 입금 증빙은 여전히 미인증. SFDC 실제 객체 Save/readback도 미검증.
- 이 지표에서 **신규 9건은 수집 시각 이후 대기분**이었음. GitHub 스케줄 누락/지연 여부는 반복 모니터링하되, 0건 재검증만으로 cron 지연 원인이 확정되지는 않음. 60일 이전 34,552건은 역사적 별도 backfill로 관리.


## 2026-11-09 09:24 KST: SFDC 3 Report source→generated view 실측 검증

- [PR #649](https://github.com/kimtk94/Codex/pull/649) 병합 및 [GitHub Actions #42539946801](https://github.com/kimtk94/Codex/actions/runs/42539946801) main live read-only PASS.
- **원천은 실제 Salesforce 객체 직접 조회가 아니라 QQ 메일 첨부를 검증해 보관한 3종 Report staging.** 원천 수신일은 2026-11-08 17:00 KST; 이번 검사에서는 각 stage 상태가 `PRESERVED_NO_NEW_REPORT`. 후속 SFDC 객체 저장이나 `NO_NEW_DATA`를 인증하지 않는다.
- Staging Leads **515 unique/515 rows**, Opportunities **706 unique/706 rows**, Quotation **3,883 process rows / 838 unique Quote IDs**; 차이 3,045행은 동일 Quote의 공정 행으로, 오류 중복 Quote가 아니다.
- 별도로 계산한 Quote→Opportunity 관계: `SFDC Verified Relations` **781개**, `SFDC Quote Link Review` **57개**. **56개는 Opportunity export scope 밖**, **1개는 Opportunity ID 누락** (후자는 `MULTIPLE_OR_ZERO_OPPORTUNITY_IDS` 이유도 함께 가지며 별개의 Quote 1건임). `MISSING_OPPORTUNITY_ID:1, OPPORTUNITY_NOT_IN_EXPORT:56`.
- 독립 readback에서 **838/838 Quote IDs 커버, source ID missing=0, sink unexpected=0, relation value mismatch=0**. 판정 `PASS_STAGE_TO_GENERATED_ONLY`.
- **SFDC 실제 객체 Save/readback, CRM Contact 연결, 본인 소유 관계, CDMS 동기화와 고객 발송은 인증되지 않았다.** 56개 out-of-export를 객체 삭제·부재라고 단정하거나 자동 생성해서는 안 된다.
- `.github/workflows/css-sfdc-report-sink-parity.yml` cron KST **09:55, 13:55, 18:55**; 누락·연결값 오류·원천 ID 불완전 시 fail closed. Vercel 제외.
- 다음 수용 검증: 본인 소유 Opportunity만 별도 집계한 후, 권한이 있는 SFDC 실제 객체 read-only 조회 경로를 확보해 Quote/Opportunity 18자리 실제 Salesforce ID와 report ID 매핑을 검증. Desktop Commander NGKR-SAL-TH는 본 검사 당시 **오프라인**, 직접 Save 인증 불가.


## 2026-11-09 09:38 KST: SFDC 내 Owner 보고서 기준 Quote/Oppo 범위와 우선 확인 항목

- [PR #651](https://github.com/kimtk94/Codex/pull/651): 독립 SFDC stage→sink 파이프라인에 Opportunity ID 기반 Owner, Stage, Quote Active 직접 비교 추가. [GitHub Actions #42540953825](https://github.com/kimtk94/Codex/actions/runs/42540953825) SUCCESS. **원천 보고서와 생성 결과 테이블 간** Owner 불일치 0, Stage 불일치 0, Quote Active 불일치 0. `PASS_REPORT_OWNER_TO_SINK_ONLY`.
- 수신된 **2026-11-08 17:00 KST** SFDC 3종 Report 기준 Opportunities 706 중 Owner exact `Kim Taehoon` **559개**, 기타 147개. 정상 연결 Quote 781개 중 **772개 본인**, 기타 9개. 연결 검토 57개는 Opportunity Owner 검증 불가로 **자동 본인 할당 금지**.
- 본인 소유 Opportunity 559개 중 Quote 연결 확인 Opportunity **436개**, Quote 연결 미확인 Opportunity **123개**. 후자는 절대로 SFDC 실제 Quote가 없다고 확정하지 않는다.
- 본인 고유 Quote **772개**, 이중 Active 보고값 `1` **712개**, `0` **60개**. Stage별 Quote: Closed Won **675**, Closed Lost **12**, Negotiation **16**, PO Received **29**, Quotation Issued **40**. 공정 원본 행 **3,582**개이며 3,582개 Quote라는 의미가 아니다.
- [PR #652](https://github.com/kimtk94/Codex/pull/652), [GitHub Actions #42541273776](https://github.com/kimtk94/Codex/actions/runs/42541273776): 123개 Quote 연결 미확인 Opportunity를 **Quotation Issued 7, Proposal Sent 12, Closed Won 28, Prospective 39, Closed Lost 37**로 원천 Stage에 맞게 100% 분류. `owner_unlinked_quote_absence_certified=false` 유지. 
- 실무 우선순위: **Quotation Issued 7, Proposal Sent 12, Closed Won 28**은 원본 Quote가 보이지 않는 이유(보고서 범위, 추출 기준, 실제 객체) 검증 대상으로 분리. Prospective 39는 Quote 의무 단계 아님. Closed Lost 37은 자동 고객 팔로업 대상 아님.
- **인증 범위 주의:** QQ-delivered SFDC Report staging→Google generated mirror의 Owner/Stage/Active 및 연결 ID 대조만 PASS. 실제 Salesforce 객체 Save/조회는 데스크톱 오프라인 및 연결 제한으로 `NOT_CHECKED`; 이 결과를 Salesforce 객체 최신성 PASS로 승격시키지 않는다. 매일 09:55/13:55/18:55 KST Actions 읽기 전용 점검 지속. 고객 발송/재견적 생성/SFDC 쓰기 작업은 없음.
