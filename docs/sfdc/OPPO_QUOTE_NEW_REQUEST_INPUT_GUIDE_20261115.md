# 신규 Oppo·Quote 작성: 최소 사용자 입력과 자동 확인 경계 (2026-11-15)

## 역사적 근거
- QQ CRM 감사 원천: Opportunity 712개, Quote 854개, Quote process 3,949행.
- 공통 템플릿 검증 후보 567건; 예외 287건(비활성, 관계 불일치, 다중 Product, 공정 불일치 등)은 자동 추천 제외.
- 이 화면은 현재 Salesforce 실시간 Report가 아닌 2026-11-15 집계 기반 **관측된 공정만** 표시한다. 실제 Product ID/가격표는 자동 로딩되지 않는다.

## 신규 견적을 만들 때 가장 필요한 정보
| 필드 | 사용자 제공 | 시스템 수행/검증 |
|---|---|---|
| 소속기관 및 고객 한글 이름 | 필수, 동명이인은 기관 지정 | SFDC 001 Account / 003 Contact / 소속 관계 readback |
| 서비스 및 샘플 수 | 필수 | 히스토리 공정 후보 표시, 공식 Product는 별도 조회 |
| 생산량의 양·단위·범위 | 필수: Gb/M reads/Lane/K tags/Cell/sample, 샘플당 또는 전체 | 샘플 수와 수량을 분리, 임의 단위 환산 금지 |
| 기존 Oppo/Quote 번호 또는 이름 | 있으면 제공, 없어도 됨 | 원본 006/a0P 조회 후 유지/수정 항목 차이 비교 |
| 샘플 유형·전처리/QC/분석 | 있으면 제공 | Product 공정별 Pack·수량·필요 옵션 추가 확인 |
| Cloud/Alicloud 사용 여부 | 필요/불필요/미확인 | 총 Gb 확인 후 ceil(Gb/100); 단위가 다르면 계산 보류 |
| 현재 확인된 상태 | 샘플 접수 예정, 견적 요청, 실제 접수 등 | Progress Description 새로 작성; 과거 문구 복제 금지 |
| 특별단가·할인·견적통화 | 필요시 승인 근거 | 과거 USD converted 값은 현재 승인 KRW 가격이 아님 |

## 구현 상태
- 신규 화면: masteros/web/app/sales/oppo-quote/new/page.jsx (원래 PMP 시범 화면과 분리).
- Pure local validator: masteros/web/lib/sfdc-new-oppo-quote.mjs.
- 검증: masteros/web/tests/sfdc-new-oppo-quote.test.mjs 및 기존 CI 웹 빌드.
- Opportunity Name과 Quotation Name은 같은 제안값을 쓰며, 신규 Close Date는 오늘(KST 기준) +1개월.
- 참고 Quote를 입력하더라도 원본을 가져오거나 Price/Product/Description을 복제하지 않는다.
- Single-cell/Spatial 또는 기타/복합 서비스는 공정 자동 추천을 하지 않는다.
- 모든 작성 요청은 HOLD_REQUIRED_INPUT 또는 HOLD_SFDC_ID_PRODUCT_PRICE_APPROVAL 상태이고 crmWrites=0 / salesforceSaveAllowed=false.
- 브라우저 안에서만 작성/복사한다. 사용자가 명시적으로 복사하지 않는 한 민감한 데이터 전송·저장 없음.

## 실무 다음 단계
1. 인증된 Salesforce에서 고객별 001/003 ID, Oppo 006, Quote a0P, 기존 Quote Product 및 공정 ID를 직접 확인.
2. 현행 제품·서비스별 Process 가격, 할인, Pack, Alicloud, 샘플 전처리 상태를 건별 검증.
3. 비교 원본과 다른 필드만 신규 작성 UI에 반영하고 Save 이전 readback 테스트. SFDC 실제 Save는 건별 명시적 승인 필요.
