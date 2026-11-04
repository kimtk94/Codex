# Genixcure PacBio EcoRV Linear Plasmid — CIGAR 독립 검증 v3

**검토일:** 2026-11-04  
**자료:** EcoRV 6,848bp linear reference; 12,000개 HiFi 고유서열 파일럿 FASTA; minimap2 v2.26 `-x map-hifi -c --eqx` PAF; read_count metadata.  
**상태:** 독립 재집계 / CIGAR·FASTA 교차 검증 PASS. 원본 BAM의 Read-단위 모집단 검증은 아직 미실시.

## 1. 검증 범위와 주요 수치

- 원본 HiFi 데이터 규모(기존 확인): 5,140,518 reads / 4,629,432 exact unique.
- 파일럿: **12,000 unique**; 파일럿 대상의 기존 read_count 합계 **19,858**. 이는 read-level 무작위 추출이 아니라 read_count 가중 unique 추출이므로 전체 빈도로 외삽하지 않음.
- 참조서열 매핑 성공: **11,946/12,000 (99.55%)**.
- 전장 범위 정렬 후보: **10,611/12,000 (88.42%)**. 이는 intact molecule 확정이 아님.
- `=` 염기 **77,402,663 bp**, `X` 염기 **17,657 bp**. 일치율 = **99.9772%**, 삽입·결실은 분모에서 제외. 실제 FASTA와 `=` CIGAR 77,402,663bp를 전수 대조해 불일치 0.

## 2. 주요 구조적 차이 (동일 서열에서 여러 이벤트가 중복 검출될 수 있음)

| 구간 | Linear ref (0-based, 대략) | 원본 plasmid 좌표 (1-based, 대략) | 정의 | 후보 Unique | 파일럿 대비 |
|---|---:|---:|---|---:|---:|
| ITR | 2,144 | 13 | 90–102 bp 결실 | 10,071 | 83.93% |
| UMI 인접 A | 2,438 | 307 | 10–14 bp 삽입 | 5,113 | 42.61% |
| Barcode 인접 B | 2,446 | 315 | 10–14 bp 삽입 | 9,267 | 77.22% |
| 7mer insertion 주석 인접 | 6,079 | 3,948 | 19–23 bp 삽입 | 5,161 | 43.01% |

- 두 개의 10–14bp 가변 위치에서 **동시에** 삽입이 검출된 Unique는 **4,221개**. 과거 v2의 `22–26 bp net extra` 분류는 독립적인 24-mer 하나로 해석하면 안 됨.
- ITR 96bp 결실의 가장 흔한 CIGAR 표시 위치는 0-based **2144 (8,963개)**. 같은 크기의 결실이 2147 (607개) 및 2138 (327개)에도 배치되므로 ITR 반복 구조에서 breakpoint는 모호할 수 있음.
- 추가 21bp 삽입의 가장 흔한 CIGAR 표시 위치는 0-based **6079 (4,570개)**. SnapGene `7mer insertion` 라벨은 2bp의 feature span이므로 7-mer 세 번이라고 확정할 수 없음.
- 삽입 서열 자체가 매우 다양함. 이를 전체 플라스미드 변이 개수로 취급하거나 UMI/barcode를 설계 확인 없이 제거해서는 안 됨.

## 3. 기존 CIGAR v2와 비교해 수정해야 할 해석

1. 전체 alignment identity가 낮은 이유를 단순 염기 치환 오류로 판단하면 안 됨. **반복적인 긴 gap**이 크게 기여하고, 대응염기 `=`/`X` 일치율은 99.9772%였음.
2. v2의 `Barcode_net_extra_22_26`은 순삽입량만 집계해 **서로 다른 두 위치의 12-mer 삽입**을 구분하지 못함.
3. v2에서 **Ref 6079 부근 21bp 삽입**을 별도로 분류하지 않아 구조 패턴을 누락함.
4. ITR 정렬에서는 gap 좌표가 좌우로 이동할 수 있어, 동일 길이만으로 특정 96bp 결실의 정확한 기점을 확정할 수 없음.
5. `full_span`은 query/reference coverage, 말단 정렬, 길이 조건을 충족하는 후보이지 정상 플라스미드의 완전성·기능이 검증된 집계가 아님.

## 4. 완료/미완료 판정

| 검증 단계 | 판정 |
|---|---|
| SnapGene 원본 EcoRV single-cut, 6,848bp reference | PASS |
| Pilot FASTA/PAF/metadata 12,000 Unique 확인 | PASS |
| minimap2 CIGAR 기반 구조 이벤트 재집계 | PASS |
| CIGAR `=` 염기 실제 FASTA 일치 검증 | PASS |
| 전체 5,140,518 raw HiFi Reads 기반 구조 비율 | NOT DONE |
| 실제 UMI/Barcode 길이 및 분자 수준 정규화 | NOT DONE |
| ITR 변이 경계·두 ITR 구조 독립 확인 | NOT DONE |
| Reference backbone SNV/indel의 오류보정·Consensus | NOT DONE |

**다음 실행:** 원본 PacBio BAM에서 Read-단위 무작위 표본을 추출해 길이/QV/정렬/구조 이벤트를 계산하고, 전체 분석으로 확장할지 판단. 설계 정보로 UMI 및 Barcode 가변 경계를 승인받기 전에는 무리하게 deduplication하지 않음.
