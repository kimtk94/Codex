# 2026년 KRW Quote Product–Process 단가 재사용 기준

## 확정 범위 (2026-11-16)
- 현재 연도 **2026년 Quote만** 후보에 포함한다.
- **USD 단가, USD converted, 이전 연도(2025 등), 환율 역산 금지**.
- 기준 원천은 `SFDC Email Quotation Raw`의 2026 행이지만, 이 보고서의 25개 열에는 **Unit Price USD만 존재하고 KRW 공정별 단가가 없다**. 원천 감사가 PASS여도 가격 재사용은 HOLD.
- 실제 조사 범위: 전체 Quote 공정행 3,949개, 2026년 작성 공정행 2,648개. 이는 매출/Quote 건수나 승인 KRW 단가 개수가 아니다.
- `Quotation Approvals` 승인 메일이나 `Quote Approval Dedup`의 KRW 금액(있는 경우)은 Quote/정산 단위일 수 있다. **각 Process의 KRW unit price로 분배/역산하지 않는다**.
- `SFDC Quote Export` 2025년·USD 보고서나 세금계산서 VAT 포함 합계 역시 Price Line 원천이 아니다.
- QQ Report의 Contact ID는 `CP...` 외부 CMS 식별자가 주로 등장하며, `003...` SFDC Contact와 동일하다고 가정하지 않는다.

## 사전 인덱스의 최소 필드
KRW 행 원천이 확보되면 인증된 private source에서 아래 필드만 읽고, 출처의 원본 증빙과 맞는지 검증한다.

`quote_id, created_date, active, approval_status, currency=KRW, was_usd_converted=false, vat_basis=VAT_EXCLUDED, account_id (001), contact_id (003), process_id, product_signature, data_unit, data_size, sample_quantity, unit_price_krw, source_kind=VERIFIED_SFDC_KRW_PROCESS_PRICE, source_verified=true`.

- `product_signature`는 공정 묶음의 검증된 fingerprint이며 개별 `QD...` Quotation Product 인스턴스 ID와 같지 않다.
- 각각의 `Process` 단가를 별도 행으로 보존하고 `Product` 전체 금액과 섞지 않는다.
- 동일 서비스라도 생산량, Unit, 샘플 수, 포함 공정에 따라 가격이 달라질 수 있으므로 단가를 바로 적용하지 않는다.

## 재사용 순위
1. **1순위: 같은 Account(001) + Contact(003)**, Product fingerprint + Process ID + Data Unit 매칭, 2026 승인 KRW. 생산량과 샘플 수까지 같으면 역사적 원본을 가장 높은 추천 후보로 둔다. **자동 적용은 금지**.
2. **2순위: 같은 Account, 다른 Contact**는 비교용 Quote로만 표시한다.
3. **3순위: 다른 Account**라도 같은 Product fingerprint + Process ID + Data Unit이면 비교용 Quote로 제시한다. 고객별 특약/할인을 재사용하지 않는다.
4. 생산량 또는 샘플 수가 다르면 같은 고객이라도 `COMPARISON_ONLY`로 표시하고 가격을 다시 정한다.
5. 미승인, 비활성, 2025, USD, VAT 포함/미확인, native Salesforce ID 미검증, 타 Process/Unit은 제외한다.

## 적용 현황
- 재사용 후보 정렬 코드: `automation/sfdc/quote_2026_krw_price_reuse.py`.
- 자동 검증: `.github/workflows/sfdc-2026-krw-price-candidates.yml`. 매일 21:25 KST, GitHub Actions.
- 코드는 인가된 KRW 단가가 제공될 때만 추천 리스트를 만들며 **실제 SFDC/Feishu 쓰기와 고객 데이터 로깅이 없다**.
- 현재 25열 SFDC Quote 원본 기반의 KRW 가격 재사용 상태: **HOLD_NO_NATIVE_KRW_PROCESS_SOURCE**.
- 이 단계에서 중요한 다음 작업은 2026년에 승인된 원본 KRW **Quote Product Process별 Unit Price** 보고서나 SFDC 인증 Quote Line readback을 확보해 private index로 연결하는 것이다. 단, 가격 승계/저장은 건별 승인 후에만 수행한다.
