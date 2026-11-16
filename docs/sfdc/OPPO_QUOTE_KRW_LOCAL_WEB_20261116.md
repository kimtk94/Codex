# 2026 KRW Quote Product–Process 가격 비교 로컬 웹 (2026-11-16)

## 경로 및 주요 동작
- Next.js 경로: `/sales/oppo-quote/new` (기존 PMP 시험 화면 `/sales/oppo-quote` 유지).
- 요청서 영역은 신규 Opportunity/Quote의 공통 이름과 Close Date, 샘플 수·생산량을 미리보기만 한다. Salesforce Save는 No-Save.
- `2026 KRW 공정별 가격 비교` 패널은 인증 SFDC에서 **별도로 추출·검증된** 원본 KRW Process Unit Price 자료가 있을 때 로컬 브라우저에서 읽는다.
- JSON 파일은 브라우저 메모리 안에서만 파싱하며 업로드·서버 저장·GitHub Actions 업로드를 하지 않는다.
- 동일 **001 Account + 003 Contact** 우선, 동일 Account의 다른 Contact 다음, 다른 고객의 동일 **Product fingerprint + Process ID + 단위** 순으로 과거 견적 비교 후보 제시.
- 후보마다 과거 Quote 번호, 날짜, KRW 단가, 생산량/샘플 수를 표시한다. `비교 견적으로 선택`은 로컬 참고 선택일 뿐 신규 SFDC의 단가·프로세스 수량을 채우지 않는다.
- **2026년 / KRW 원본 / VAT 제외 / 승인 & Active / native 001,003 검증 형식**을 모두 만족하는 공정행만 파싱.
- 2025, USD, USD converted, 인보이스 VAT 포함 합계, 미승인, CP Contact 외부 ID, 다른 공정 또는 단위는 자동 제외.
- 2026년 최신 QQ Quote Report 25열에는 **원본 KRW 공정 단가 컬럼이 없기 때문에** 실제 파일은 별도로 확보해야 한다. 소스가 없으면 가격 검색은 HOLD.

## 로컬 근거파일 JSON 규격
파일은 클라이언트가 제공하며 `source_verified=true` 같은 내용 자체는 **SFDC 인증을 증명하지 않는다**. 실제 CRM 원본과 승인 상태를 다시 확인하기 전엔 가격 적용 불가.

```json
{
  "version": "sfdc-2026-krw-process-prices-v1",
  "source": "SFDC_AUTHENTICATED_READ_ONLY_KRW_PROCESS_LINES",
  "generated_at": "<ISO UTC time within the last 24 hours>",
  "salesforce_write_performed": false,
  "records": [
    {
      "source_kind": "VERIFIED_SFDC_KRW_PROCESS_PRICE",
      "source_verified": true, "created_date": "2026-10-01",
      "quote_id": "QID-2026-10-01-123456", "active": true,
      "approval_status": "APPROVED", "currency": "KRW",
      "was_usd_converted": false, "vat_basis": "VAT_EXCLUDED",
      "account_id": "001000000000AAA", "contact_id": "003000000000AAA",
      "process_id": "Process-2026-01-01-00001",
      "product_signature": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "unit_price_krw": "300000", "data_unit": "G raw data",
      "data_size": "6", "sample_quantity": 48
    }
  ]
}
```

위 값과 ID는 **완전한 합성 예시**이며 실제 견적이나 고객 가격이 아니다. 공개 GitHub에는 합성 예시만 넣는다.

## 내부 QA
- `npm run test:sfdc`: 기존 고객/Contact 테스트 및 2026 원본 KRW 가격 파일·선택 로직을 모두 합성 데이터로 검증.
- `npm run build`: Next.js 신규 패널 포함 컴파일 확인.
- `node --test tests/sfdc-oppo-quote.e2e.mjs`: 브라우저에서 파일 선택 → Product/Process 선택 → 다른 고객/동일 고객 가격 비교 → 참고 견적 선택 → CRM 쓰기 요청 **0건** 확인.
- 기존 `.github/workflows/sfdc-oppo-quote-web-preview.yml`을 통해 GitHub Actions CI 사용.

## 로컬 개발 실행
- `masteros/web` 디렉터리에서 `npm install` 후 `npm run build`.
- 기존 서비스가 3000번 포트를 사용 중이라면, 다른 로컬 포트 예: `node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3001`.
- 해당 PC의 브라우저 주소: `http://127.0.0.1:3001/sales/oppo-quote/new` (해당 포트의 실행이 실제 확인된 경우에만 사용).
- 로컬 PC 외부에서는 `127.0.0.1` 주소에 접속할 수 없다.
