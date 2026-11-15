# SFDC Opportunity–Quotation 공통 패턴 학습 (2026-11-15)

## 데이터 출처와 범위
- 원천: `SFDC_Automation_Followup_2026` / `SFDC Email Opportunities Raw`, `SFDC Email Quotation Raw`, `SFDC Email Ingest Audit`.
- QQ CRM 구독 Report 수신: 2026-11-15 12:00 KST; 수집 감사 확인: 2026-11-15 16:55 KST.
- 실제 분석: **Opportunity 712개**, **Quote ID 854개**, **Quote Product ID 940개**, **Quote Process 3,949행**.
- Quotation 프로세스 행을 견적 건수로 잘못 집계하지 않도록 `QID -> QD Product -> Process` 계층으로 그룹화.
- Quote ID 중 Opportunity ID를 최신 Report 내에서 확인할 수 있는 건 797개. 나머지 57개(연결 ID 부재 1건, Report 범위 밖 56건)는 **절대 무조건 연결하거나 자동 선택하지 않음**.
- Salesforce 인증 화면 전체 최신 상태를 증명하는 것이 아닌 QQ Report 수집본의 요약. 감사된 메일 스냅샷과 SFDC 실제 UI/레코드의 권위는 다름.

## 전체 Quote 기준 빈도 (예외 포함 분모 854)

| 항목 | Quote 수 | 비율 |
|---|---:|---:|
| Product ID 1개 | 789 | 92.4% |
| Product ID 2개 이상 | 65 | 7.6% |
| Active=1 | 785 | 91.9% |
| Active=0 | 69 | 8.1% |

대표 프로세스 조합(`Quotation Process Name`, Quote ID 기준; 실제 공정 순서는 원천 원문으로 유지):

| 조합 | Quote 수 | 전체 비율 |
|---|---:|---:|
| Library preparation + Sequencing by data amount + Analysis by sample + Data release | 402 | 47.1% |
| Extraction and sample QC + Library preparation + Sequencing by data amount + Analysis by sample + Data release | 107 | 12.5% |
| Sample QC + Library preparation + Sequencing by data amount + Analysis by sample + Data release | 57 | 6.7% |
| Library QC + Sequencing by data amount + Analysis by sample + Data release | 56 | 6.6% |
| Sequencing by data amount + Analysis by sample + Data release | 51 | 6.0% |
| Library QC + Sequencing by lane + Analysis by sample + Data release | 26 | 3.0% |

**중요:** 각 공정은 Quote Product 내부의 구성 요소임. 한 Product가 4개 프로세스라면 Product 4개로 Clone하지 않는다. 단일 Product 안에서도 QC, Library, Sequencing, Analysis, Data release의 단가·수량·데이터 단위가 서로 다르다.

## Opportunity 현황
- Closed Won 489 / Closed Lost 57 / Prospective 52 / Quotation Issued 48 / PO Received 31 / Negotiation 20 / Proposal Sent 15.
- 화폐: KRW 558 / USD 106 / 값 없음 48.
- 1 Opportunity에 여러 Quote 개정/발행 이력이 있을 수 있으므로, Quote를 임의로 한 개 선택하지 않는다. 현재 Report 기준 **199개 Opportunity**에 복수 Quote ID가 연결됨.

## 일반적인 신규 Oppo–Quote 작성 규칙

1. **기본 분류:** Account → Contact → Opportunity → Quote → Product → Process. 고객 이름 문자열과 기관 이름만으로 SFDC의 001/003/006/a0P 관계를 추론하지 않는다.
2. **Oppo와 Quote 동시 진행:** Oppo 또는 Quote를 기존 템플릿으로 지정하면 서로 대응하는 필드를 **사전 로드**, 선택한 수정사항만 반영한다. 새 Oppo와 Quote의 **기본 이름은 동일**하게 한다. 다만 역사적 Report의 두 이름이 달라졌다고 자동 동일화하지 않는다.
3. **단일 Product 기본 패턴:** 위 상위 6개의 실제 조합을 우선 추천한다. 고객별 할인, 과거 견적의 Unit Price, Process Quantity, Pack, 특이 옵션은 불러오기만 하고 신규 가격으로 확정하지 않는다.
4. **생산량 중심 선택:** 같은 Product라도 데이터 생산량(Gb), Lane, M raw reads 등 단위를 구분한다. **Gb 수치만으로** Sample Quantity, Process Qty를 복제하지 않는다. `Alicloud` 100 Gb당 1개(올림)는 별도로 승인된 작성 규칙이며 학습된 Quote 공정의 일반 가격 규칙과 다르다.
5. **Description:** 현재 25열 Quote Report에는 `Progress Description`이 없어 과거 문구를 실제로 학습/검증했다고 볼 수 없다. 새 건은 현재 고객·연구서비스·샘플·확인된 단계로 새로 작성한다. 아직 발행되지 않은 Quote/PO/샘플 접수 여부를 단정하지 않는다.
6. **정체성/가격 안전:** Quote Report의 `Unit Price USD` 및 `Sales Price USD (converted)`는 과거 USD 환산값으로 **현재 KRW 승인 단가가 아니다**. 비어 있거나 외부 CMS `CP...`만 있는 Contact는 실제 SFDC 003 ID와 001 Account 관계를 재확인한다.
7. **저장 정책:** SFDC 실제 저장 기본 `No-Save`. 건별 검증 이후 명시적인 사용자 승인까지 자동 저장하지 않는다. Vercel은 운영 범위에서 제외.

## 자동 학습 로직 및 예외 격리
- Script: `automation/sfdc/oppo_quote_popular_patterns.py`
- 전수 읽기 → QQ 수신 감사의 SHA256/행수/Unique ID 검증 → QID별 Product/Process 묶기 → 관계/Active/Account 검증 → 인기 프로세스 조합 추출.
- 자동 추천 후보: Active=1, 정확히 하나의 Product ID, 한 Opportunity ID가 해당 수집본에 존재, Account ID가 일치, Product 원문과 Process 행 일치, **해당 조합이 10개 Quote 이상 & 적격 Quote의 1% 이상**.
- 이외 모든 자료는 **학습/집계 범위엔 포함되나 자동 추천 템플릿 승격에서 제외**; 이력과 예외율을 추적할 수 있도록 집계만 남김.
- 학습 결과 공개 GitHub 로그/아티팩트에는 고객명·Contact·QID·견적가격을 내보내지 않음. Actions는 일일 read-only 검증, 실제 SFDC 저장 0회.

## 다음 통합 경계
- 자동 학습 결과를 Oppo–Quote 웹의 기본 템플릿으로 연결하려면 **실제 SFDC 001/003/006/a0P ID를 인증 브라우저에서 재검증하는 입력 게이트**가 별도로 필요하다.
- 이 문서는 **공통 구조 학습**이며 제품별 승인 가격·완전한 Salesforce 실시간 필드 학습·Description 원문 학습을 완료했다는 의미가 아니다.