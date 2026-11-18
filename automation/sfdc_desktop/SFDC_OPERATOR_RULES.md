# SFDC 영업 자동화 — 확정 운영 규칙 (Source of truth)

> **범위:** 기존 SFDC Account·Contact로 Opportunity → Quotation 생성, 기존 레코드 수정, 웹 승인·저장. 2026-11-18 이전 사용자 요청을 통합. **이 문서와 자동 회귀 테스트를 확인하지 않고 생성 로직을 변경하지 않는다.**
>
> **우선순위:** 최신 명시적 사용자 결정 > 이전 명시적 규칙 > 기존 Salesforce 원본 관계/가격 > 구현 편의나 추정. 충돌하면 *HOLD*하고, 임의로 이전 규칙을 변경하지 않는다. 이미 승인된 사용자 결정을 반복 질문하지 않는다.
>
> **변경 절차:** (1) 기존 사용자 규칙·실제 SFDC native 화면·관련 소스 확인 → (2) 변경 영향과 충돌, source/target 양쪽 최신성 확인 → (3) 코드 수정 + 합성 회귀 테스트 → (4) GitHub Actions 통과 → (5) 연결된 노트북 read-only 검증 → (6) 해당 단일 건 승인 후 실제 Save / 신규 006·a0P ID 및 관계 재조회. No-Save와 실제 Save를 혼동하지 않는다.

## 불변 필수 규칙

| 규칙 ID | 반드시 유지할 계약 | 위반 시 처리 |
|---|---|---|
| SFDC-001 | **기존 Contact를 찾아 native 003 ID로 선택한 상태에서 Opportunity 생성 흐름을 시작.** Opportunity List의 전역 New를 대신 쓰지 않음. 기존 Contact·Account 새로 생성하지 않음 | CONTACT_FIRST_ENTRY_REQUIRED |
| SFDC-002 | Contact.AccountId와 선택 Account 001 ID가 정확히 같아야 함. Account가 지정됐다면 소속 Contact만 선택. 동명이인 기관은 native ID로 구분 | CONTACT_ACCOUNT_NATIVE_RELATION_UNVERIFIED |
| SFDC-003 | Opportunity 이름 = Quotation 이름 = 사용자가 정한 이름. **날짜·-02·임의 suffix 부착 금지.** 동일 이름 허용, 기존·신규 006/a0P ID로 구별 | APPROVED_NAME_CHANGED |
| SFDC-004 | 새 Quotation은 **새로 저장하고 읽어온 Opportunity의 Related → New Quotation**에서 생성. 자동 연결된 Account/Contact/Opportunity는 중복 입력하지 않고, 선택된 부모 006 ID를 검증 | QUOTE_MUST_START_FROM_OPPO_RELATED |
| SFDC-005 | 기존 Oppo/Quote 선택은 *template* / 복제 후 변경값 반영 목적. Account/Contact 유지와 변경 2가지 모드 제공. 기존에 이미 연결된 Quote를 재사용/수정할 때 중복 새로 만들지 않음 | TEMPLATE_RELATION_OR_WRITE_MODE_UNVERIFIED |
| SFDC-006 | 단가는 **2026년 KRW SFDC 원본** 최우선, 같은 Account+Contact → 과거 거래, 없으면 비교 가능한 고객 Quote의 승인된 Product·Process 선택. USD 변환·2025 기본 단가·임의 추정 금지 | CURRENT_KRW_PRICE_UNVERIFIED |
| SFDC-007 | Product/Process는 기존 Salesforce 마스터 native ID 사용. Quote Product와 Process 실측·수량·Pack·단위·세부 금액 확인. Product를 새로 생성하지 않음 | PRODUCT_PROCESS_MASTER_ID_UNVERIFIED |
| SFDC-008 | 샘플 수와 생산량 Gb는 별도 필드. Pack은 같은 biological sample 수 기준, 공정별 Process 수량은 별도 검증. Amplicon Region 2개 시 동일 샘플 2서비스 적용 | QTY_PACK_DATA_UNVERIFIED |
| SFDC-009 | AliCloud 추가 라인은 요청 시 총 Gb / 100을 올림. **Data release와 별도 추가 AliCloud를 구분**. 충돌하는 이름/Type/고객 승인 조건은 임의 제거·포함하지 않고 HOLD | ALICLOUD_DATA_RELEASE_CONFLICT |
| SFDC-010 | Opportunity Amount 및 Quote Total Price는 **VAT 제외**. Quote GST/VAT 10%, VAT 포함 총액을 별도 재계산. 원본 Oppo 금액이 Quote와 다르면 새 건에서는 승인된 공정 합계 기준으로 재검토 | NET_VAT_TOTAL_MISMATCH |
| SFDC-011 | Opportunity Close Date는 생성일(KST) 기준 **정확히 한 달 뒤**. Forecast는 실제 Revenue가 아니며, Stage/Forecast/Service Line은 현재 생성 목적에 맞춰 선택 | CLOSE_STAGE_UNVERIFIED |
| SFDC-012 | 신규 Oppo–Quote **Progress Description 상태는 `Quote Issued`**를 사용하고 `Quote Draft`를 기본값/출력값으로 사용하지 않음. 짧은 양식 `MMDD Quote Issued 서비스 수량 * 단가`에 현재 프로젝트·가격 정보를 반영. 이전 Opportunity 문구 복사 금지. `Quote Issued`는 사용자가 지정한 **SFDC 진행 단계 문구**이며 고객에게 실제 메일 발송이 확인됐다는 증거는 아님. 미확인 샘플 접수·PO·Contract·SIF·실제 견적 발송은 완료로 주장 금지 | PROGRESS_DESCRIPTION_OR_ISSUED_STATUS_UNVERIFIED |
| SFDC-013 | 통화 KRW, 국가 Korea, GST/VAT 10%, Coop TS는 Yoo JiIn. Contact는 필수 연결. 견적 Product별·Process별 KRW 단가 및 수량을 미리 보여줌 | STANDARD_FIELD_UNVERIFIED |
| SFDC-014 | 검증은 **원본 접근 최신성·동일성**과 **목적지 반영 최신성·정합성** 두 곳에서 실시. 소스 2026 Quote, native ID, Account/Contact, Price/Process·Pack 확인 없이 PASS 선언 금지 | SOURCE_OR_SINK_UNVERIFIED |
| SFDC-015 | 기본 No-Save, **건별 정확한 최종 검토와 명시적 승인 후에만 Save**. 1회 승인번호/중복 클릭 차단. 저장 후 새 Opportunity 006와 Quotation a0P는 *기존 ID와 달라야* 함 | PER_RECORD_APPROVAL_REQUIRED |
| SFDC-016 | Opportunity가 먼저 저장되고 006 ID를 확인한 후 Quotation 저장. Quote 부모 ID 확인·Product/Process 행 readback; 불명확한 저장 결과는 UNKNOWN/HOLD, 자동 재시도 금지 | PARENT_OR_READBACK_UNVERIFIED |
| SFDC-017 | GitHub Actions에는 **합성 CI / read-only 작업만**. 실제 고객 데이터·비밀번호·SFDC 쓰기는 연결된 노트북 인증 브라우저에서만 수행. Vercel 제외, 서버 없는 운영 | LAPTOP_ONLY_SAVE |
| SFDC-018 | 실제 확인한 것이 아닌 내용·추정 가격·추정 레코드 ID를 입력하지 않음. UI 단계가 기존 규칙과 다르면 임의의 우회 경로로 생성하지 않고 HOLD, 검증 가능한 오류를 표시 | FAIL_CLOSED_ON_UNKNOWN |
| SFDC-019 | Lead 전환은 별도 작업: 중복 방지, 확인된 한글명과 영문명 규칙, Account 주소를 Shipping Address에, Job Function 최상단, Academic PI, 이후 Sync To CDMS. Opportunity 생성 시 Lead 변환 규칙과 혼동 금지 | LEAD_CONVERSION_RULES_SEPARATE |
| SFDC-020 | 단일 UI의 조회·검증은 필요 시 병렬 처리 가능. **같은 레코드 생성·수정·Save는 순차 처리**, 동시 편집·중복 실행 방지 | NO_PARALLEL_CRM_WRITES |

## 2026-11-18 추가 확정: Quote Issued 표기

- `Quote Draft`는 새 Oppo–Quote 생성의 기본 상태 또는 Progress Description에 쓰지 않는다. **`Quote Issued`를 사용한다.** 실제 고객 발송·발행 메일 증빙은 별도 이벤트/로그로 판단한다.
- 단순 텍스트 치환만 하지 않고 **draft 생성 기본값 → preflight → 승인 요청 스키마 → UI 문구 → GitHub Actions 회귀 테스트**까지 동일하게 적용한다. 이미 생성된 불변 요청의 원문을 조용히 고치지 말고, 필요하면 동일 조건의 새 요청번호로 재제출한다.
- Quote Status와 Opportunity Stage는 실제 Salesforce 필드 선택지와 사용자 지시를 구분하며 검증한다. 필드에서 해당 값이 확인되지 않으면 임의 매핑하지 않는다.

## 이미 승인된 이화여대 PMP 단일 건 (구현에 하드코딩하지 말 것)

- Opportunity/Quotation **동일 이름 유지**: `Korea-Ehwa Univ.-4-PMP-5Gb-Prof. RohTaeYoung`.
- 기존 native Contact·Account를 그대로 사용하며 기존 레코드 006/a0P는 원본 참고로만 사용. 신규 006/a0P ID는 Save 후 별도 기록.
- 샘플 4개, 각 5 Gb. **원본 2026 KRW 공정**: Library QC 4×20,000 = 80,000 / Sequencing 4×37,500 = 150,000 / Analysis 4×0 = 0 / Data release 1×30,000 = 30,000.
- 공급가액 **260,000 KRW**, VAT **26,000 KRW**, 총 **286,000 KRW**는 승인됨.
- 별도 추가 AliCloud 제외가 사용자 의도에 부합하는 듯하나, *Salesforce 기존 Data release의 Process Type도 AliCloud*로 나타나므로 **동일 건의 Data release 유지/추가 저장 세부 관계는 보류 상태**. 질문/확인을 가장 최신 승인과 구분. 금액 재계산·조건 조용히 변경 금지.
- 기존 Oppo는 이미 Closed Won / Amount 240,000: 새 건에 그대로 복사 금지. 실제 진행 Stage·Forecast와 신규 공급가액 다시 확인.
- 현재는 SFDC 신규 Opportunity·Quotation **실제 저장 0건**. read-only 원본 확인은 신규 저장이 아니다.

## 개발·PR 시작 전 점검 계약

1. `SFDC-001…020` 전체를 체크하고 충돌/예외를 기록한다. 실수로 다른 entrypoint를 택한 경우 PR을 BLOCK한다.
2. 변경 파일이 기존 `sfdc_paired_native_create.py`, `sfdc_prepare_unsaved_opportunity.py`, `sfdc_native_approved_save.py`를 우회하거나 기존 규칙을 파괴하지 않는지 확인한다.
3. `python3 -m unittest discover -s automation/sfdc_desktop -p 'test_sfdc_operator_contract.py'`를 다른 합성 회귀 테스트와 함께 GitHub Actions에서 실행한다.
4. **원본 Contact-first New UI가 미검증이면 안전한 HOLD**를 반환한다. 잘못된 Opportunity List-New를 우회 수단으로 실행하지 않는다.
5. 변경 후 실제 노트북에서 사용자 승인 없이 Save하지 않고, 새 ID/readback이 없는 상황에서 완료라고 보고하지 않는다.
