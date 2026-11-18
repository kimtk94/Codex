# Oppo–Quote 자동 가격 규칙 (2026-11-18)

적용 범위: 로컬 /sales/commands/pair 및 Salesforce 신규 Opportunity+Quotation 생성.

1. 기존 Opportunity를 선택하면 연결된 Quote의 Account, Contact, Product, Process, KRW/sample, AliCloud KRW/100Gb, Pack을 원본 기준으로 자동 불러온다. 입력값이 확실하게 검증된 경우에만 원본 가격으로 취급한다.
2. 샘플당 단가와 AliCloud 단가를 사용자에게 매번 새로 입력하도록 강제하지 않는다. 원본 가격이 확보되면 선입력하여 보여주고, 사용자가 변경할 수 있도록 한다. 직접 변경한 KRW 단가는 원본 검증과 별개의 승인 및 재검증 대상이다.
3. AliCloud 수량 = ceil(실제 생물학적 샘플 수 × 샘플당 생산량 Gb / 100). 예: 3개 × 50Gb = 총 150Gb → 2개. 샘플 또는 Gb 수정 즉시 재계산한다.
4. AliCloud 금액(VAT 제외) = 청구 대상 AliCloud 수량 × 검증된 100Gb당 KRW 단가. 원본에 AliCloud Process가 있는데 단가 미검증이면 저장을 HOLD한다. 반면 정확히 매칭된 원본 Process에 독립적인 Data release 1회 고정비만 존재하고 AliCloud Process가 없다면 Data release를 AliCloud로 바꿔 추가하지 않는다. 이 경우 100Gb 기준 수량은 계산 참고값이며 Cloud는 별도 청구하지 않는다.
5. Quote 공급가액(VAT 제외)에 샘플별 공정 금액, 별도 고정 Process, AliCloud 금액을 각각 정확히 한 번만 반영한다. VAT 10%는 별도 계산한다. 별도 배송·반송 Quotation Fee는 기본 제외한다.
6. 원본 Product / Process / Pack / AliCloud에 대해 저장 전과 저장 후 같은 공정별 단가·수량 매트릭스를 검증한다. 원본과 다른 경우 자동 Save하지 않고, 부분 실패에 대해 자동 재실행하지 않는다.
7. 고정 Data release Process는 AliCloud와 혼동하거나 이중 합산하지 않는다.
8. 정해진 값은 보여주고 수정할 부분만 편집한다. 별도 승인 웹을 사용하지 않고 동일 편집 웹에서 검증 및 최종 확인을 처리한다.

검증 실행: `cd masteros/web && node --test tests/sfdc-pair-cloud-policy.test.mjs`. 실제 CRM 저장은 CI에서 실행하지 않는다.
