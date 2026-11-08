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
