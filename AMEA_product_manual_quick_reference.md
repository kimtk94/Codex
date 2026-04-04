# AMEA Product Manual 정리본 (고객 메일 답변용)

- 원문: `AMEA Product Manual.docx`
- 목적: 고객 문의 이메일 답변 시 빠르게 근거를 찾기 위한 내부 요약본
- 주의: 본 문서는 **내부 참고용**이며, 외부 전달 전 원문 재확인 필요

---

## 1. 문서 기본 정보
- 문서명: **Novogene Product Manual – Metabolomics Service**
- 버전: **2026 V1.0**
- 발행: **2026-02**
- 핵심 개정 사항
  - SG Lab 추출 범위 업데이트: **2026-04-15부터 all sample types 처리 가능(untargeted / quasi-targeted 관련 안내 반영)**
  - Untargeted standard DB: **15,000 → 18,000 standards**
  - FAQ 업데이트

---

## 2. 서비스별 한눈에 보기 (메일 1차 회신용)

| 서비스 | 주요 특징 | 최소 샘플/권장 | 장비 | 기본 데이터 | TAT |
|---|---|---|---|---|---|
| Untargeted Metabolomics Plus | C18 기반 untargeted | 프로젝트 최소 기준은 문의 조건별 확인 필요(일반적으로 최소 6 total 언급) | Orbitrap Exploris 120 | `.mzXML` | 20 working days (<100) |
| Untargeted Metabolomics Pro | C18 + HILIC, 더 높은 식별 수 | **batch당 최소 6**, **replicate 6 이상 권장** | Orbitrap Exploris 120 | `.mzXML` | 25 working days (<100) |
| Lipidomics | 지질체 중심 | 별도 확인 | (문서 표 기준) | - | 30 working days (<100) |
| Quasi-targeted Metabolomics | MRM 기반, 상대정량 | 프로젝트 디자인별 확인 | SCIEX QTRAP 6500+ | - | 32 working days (<30) |
| Targeted Metabolomics | 패널 기반 정량 | **panel당 최소 8 samples** | SCIEX QTRAP 6500+, Thermo TSQ Altis(SCFA) | - | 35 working days (<30) |

> 메일 작성 팁: TAT/최소 샘플 수는 프로젝트 크기, 패널, 배치 조건에 따라 달라질 수 있으므로 “현재 매뉴얼 기준” 문구와 함께 안내.

---

## 3. Untargeted 샘플 요구사항 (문서 명시 수치)

### 3-1. 기본 입력량
- Human & Animal tissue: **200 mg**
- Plasma/Serum: **200 μL**
- Feces/Intestinal contents: **200 mg**
- Saliva: **200 μL**
- Urine: **200 μL**

### 3-2. replicate 권장
- Clinical: 그룹당 **최소 30**
- Animal model: 그룹당 **최소 10**
- Plant: 그룹당 **최소 6**

### 3-3. 샘플 전처리/랩 위치 관련 포인트
- SG 추출 가능 범위가 2026-04-15 기준 확대됨
- 일부 샘플(예: cell, swab/skin tape 등)은 submission 시 추가 조건/특수 handling 필요
- Cell 샘플은 cell count 정보가 중요하며, 비교 가능성을 위해 extraction volume 일관성 필요

---

## 4. QC/데이터 품질 관련 핵심 문구

### 4-1. QC 구성
- QC는 고객 샘플에서 equal-volume pooling으로 준비
- 초기 QC 3개는 장비 평형화 목적
- 이후 QC는 run 중간 삽입으로 안정성 모니터링

### 4-2. 고객 커뮤니케이션 시 주의
- **개별 샘플 QC report를 별도로 제공하지 않음**
- 최종 보고서에서 QC correlation 형태로 확인
- Metabolomics에서 QC는 주로 **장비/데이터 품질 모니터링 목적**

### 4-3. 분석 제한 조건
- biological replicate가 3 미만이면 일부 분석(PCA/PLS-DA) 미수행

---

## 5. 식별/DB/결과 해석 포인트
- In-house untargeted DB (NovoMetDB-UM) 고도화
  - reference standards: **18,000+**
  - secondary spectral library 포함 시 **170,000+ compounds**
- MSI identification level 기반 설명 가능
  - Level 1: RT + MS1 + MS/MS 일치 기반 최고 신뢰 수준
- 문서 요약 예시값
  - Plus: Level 1 평균 900+, total 4000+
  - Pro: Level 1 평균 1200+, total 5000+

---

## 6. FAQ 기반 답변 포인트 (자주 물어보는 질문)

### Q1) Untargeted에서 metabolite의 절대적 presence/absence 판정 가능?
- 권장 답변: **엄밀한 의미의 절대 존재/부재 판정은 어려움**
- 이유: missing value 처리, DDA 특성, low-abundance 및 S/N cutoff 영향

### Q2) 관심 물질이 결과에서 안 보이는 이유?
- 가능한 원인
  - S/N cutoff 미충족
  - DDA top-N 선정 특성으로 저농도 이온 미포착
  - m/z 스캔 범위(예: 100–1500) 밖 물질
  - 특정 물질에 최적화되지 않은 범용 추출 조건

### Q3) Untargeted 최소 샘플 수/권장 replicate?
- 일반 최소 total sample 수는 프로젝트별 확인 필요하나, 문서 FAQ에서 **최소 6 샘플** 언급
- replicate는 clinical/animal/plant 권장 수를 함께 안내

### Q4) QC 없이 진행 가능한지?
- 샘플의 “사전 QC”로 detectability를 완전 보장할 수는 없음
- 실험 중 QC는 장비 안정성/데이터 품질 모니터링 용도로 수행

### Q5) 추출된 metabolite 샘플 접수 가능?
- **가능할 수 있으나 사전 평가 필요**
- 고객이 extraction reagent/조건/투입량 등 상세 정보를 제공해야 승인 여부 판단 가능

### Q6) Quasi-targeted 정량 방식?
- 기본적으로 **relative quantification**

---

## 7. 이메일 답변 템플릿 (바로 복붙용)

안녕하세요, [고객명]님.

문의 주신 내용은 현재 제공된 AMEA Product Manual(2026 V1.0) 기준으로 아래와 같이 안내드립니다.

- [핵심 답변 1]
- [핵심 답변 2]
- [조건/주의사항]

정확한 확인을 위해 아래 정보를 함께 공유 부탁드립니다.
- Sample type
- Sample amount (mg/μL)
- Number of samples / biological replicates
- Storage / shipping condition
- Species 및 연구 목적
- 희망 서비스(untargeted plus/pro, quasi-targeted, targeted)

자료를 확인하는 즉시 가능한 옵션과 권장 진행안을 상세히 안내드리겠습니다.

감사합니다.
[담당자명]

---

## 8. 내부 사용 체크리스트
- [ ] 답변 수치(TAT, sample amount, replicate) 문서 기준으로 기재했는가?
- [ ] 문서에 없는 성능/보장/일정을 임의로 단정하지 않았는가?
- [ ] 고객에게 추가 확인이 필요한 항목을 요청했는가?
- [ ] 예외 케이스는 “추가 confirm 필요”로 처리했는가?

---

## 9. 운영 가이드
- 본 정리본은 메일 응대 속도를 위한 레퍼런스이며, 계약/견적/실행 확정 전에는 원문(표/FAQ/노트) 재확인 필요.
- 고객 요청이 매뉴얼 범위를 벗어나면 APM/실험실 confirm 후 회신.
