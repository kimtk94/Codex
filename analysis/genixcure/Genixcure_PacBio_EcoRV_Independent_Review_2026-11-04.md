# Genixcure PacBio HiFi — EcoRV 선형 플라스미드 파일럿 독립 검증

검토일: 2026-11-04  
**확인 단계: 12,000개 대표 Unique의 기존 minimap2 정렬 + 27-mer 고유 Anchor 재검증**  
**주의: CIGAR 재정렬 검증 및 원본 BAM 전체 분석은 아직 수행하지 않음**

## 1. 제공된 원본 플라스미드 (SnapGene .dna)

- 염기서열 길이 **6,848 bp**; SnapGene 내 topology **circular**.
- EcoRV `GAT|ATC` 부위 1개; 원본 좌표 **4,716|4,717**. 선형 FASTA는 원본 4,717번부터 시작하며, 전체 길이를 보존함.
- 애매한 IUPAC `W` 3개는 원본 51–53에 존재; 정렬용 FASTA에서는 정확히 이 3개만 `N`으로 대체.
- 원본 feature의 `ITR`은 원본 1–123bp (EcoRV 회전 Reference의 0-based 2132–2255 부근) 및 `AAV2 ITR` 원본 4,726–4,855bp에 표기됨.
- `UMI 12mer` 라벨의 **실제 feature 범위는 306–307bp (2bp)**, `Barcode 12mer`도 **314–315bp (2bp)** 뿐임. 이름만 보고 실제 12-mer 서열 두 개가 존재하거나 정상 도입됐다고 **확정할 수 없음**.

## 2. 기존 Alignment_Pilot_v1 (실제 저장 파일로 검증)

- 원본 unique CSV: **4,629,432 unique / 5,140,518 HiFi reads** (기존 집계). 
- 분석한 weighted unique 파일럿: **12,000 unique**. 포함된 원본 count 합계는 **19,858 reads**; 전체 read-level 무작위 추출이 아니므로 결과를 전체 빈도로 환산하면 안 됨.
- minimap2에 정렬된 unique: **11,946/12,000 (99.55%)**.
- 기존 분류에서 `divergent_or_error_candidate`: **10,081/12,000 (84.01%)**; 기준은 PAF match/block **98.5% 미만**.
- 기존 `near_full_length_linear_plasmid`: **1,335/12,000 (11.12%)**.
- 그러나 identity 필터를 분리하면, **10,611/12,000 (88.42%)**가 Full-span 기준(Ref >=90%, query >=90%, 양끝 <=150bp, 길이 0.8–1.25배)을 만족함.
- 이 Full-span 중 **9,276개**가 identity 우선 분류 때문에 기존 Full-length에서 제외됨.
- 파일럿 전체 median read length **6,776 bp**, alignment identity **98.17%**. 주요 길이 peak는 6,764/6,776/6,785/6,797bp 부근.

## 3. 추가 재검증: k-mer Anchor 참조 좌표 변화

실제 `weighted_pilot_reads.fasta` 전체 12,000개를 6,848bp 선형 Reference에 대해 **고유 27-mer, 13bp 간격**으로 정방향/역상보 양쪽 비교하여 세 구간의 상대 좌표 차이를 추출함. 다중 매핑 k-mer는 제외.

- ITR 전(Ref 300–2000), ITR 후·barcode 전(Ref 2260–2400) anchor가 모두 있는 unique **11,492개** 중 **9,595개 (83.5%)**에서 Reference 대비 **93–99bp**의 좌표 이동 관측. 이 중 **정확히 +96bp: 7,303개**.
- Barcode/UMI 전후(Ref 2260–2400 vs Ref 2600–4200) anchor가 있는 unique **11,497개** 중 **8,670개 (75.4%)**에서 **-12±2 또는 -24±2bp**의 상대 좌표 이동 관측. 정확한 -12bp **2,832개**, -24bp **2,012개**.
- 기존 divergent **10,081개 중 9,515개**에서 ITR 인접 상대 좌표 이동 관측.

**해석:** 유사도 차이가 무작위·전장 균등하지 않고 ITR, UMI/Barcode 라벨 인접 구간에서 반복되는 구조 차이와 관련될 가능성이 높음. 단, **k-mer 간격의 변화는 실제 indel을 증명하지 않음**. 특히 ITR의 역반복·2차 구조로 인해 정렬 위치가 불안정할 수 있으므로 `minimap2 -c --eqx`의 상세 CIGAR 및 raw BAM 재검증 필요.

## 4. 기존 코드의 해석상 문제와 개선점

1. **유사도 필터를 Full-span 판정보다 먼저 적용**해 구조적으로 Full-length인 상당수 Reads를 divergent로 분류함. 정렬 범위와 sequence identity를 독립적으로 보고해야 함.
2. 과거 `map-hifi` PAF identity는 전체 블록에서 계산됨. ITR나 barcode 구간에서 발생하는 큰 indel은 총 유사도를 낮추므로 `identity <98.5%`만으로 오류/오염을 판정할 수 없음.
3. 기존 PAF에서 최고 score alignment 하나만 사용해 **supplementary/split alignment를 놓칠 수 있음**. CIGAR와 전체 segment 기록 필요.
4. Weighted reservoir unique 표본을 다시 read_count로 가중한 수치는 전체 분자/Read 모집단 비율에 대한 불편 추정량이 아님.
5. SnapGene의 annotation은 가변 UMI/Barcode **실제 12bp+12bp 주입을 입증하지 않음**. 해당 레이블의 실제 annotation span은 각각 2 bp임.

## 5. 다음 검증 순서

1. 동일 12,000개 Read를 CIGAR 상세 출력으로 재정렬하고 ITR ref 2110–2280 및 Barcode/UMI ref 2360–2530의 indel 크기와 위치 집계.
2. 주요 96bp 및 12/24bp 패턴에 대해 전후 고정 anchor로 서열 위치 확인; ITR 반복은 복수 정렬/수동 검증.
3. 정상 backbone (가변 구조·UMI/Barcode 제외) 기반 error rate, coverage, true SNV/indel 그리고 이중 ITR 구조 검증.
4. 실제 raw BAM의 **Read 단위 무작위 표본**으로 유병률/비율 재추정. 최종적으로 전체 5,140,518 HiFi Reads 분석 여부 판단.

**현재 결론:** 플라스미드 전장과 호환되는 HiFi Reads가 파일럿에서 다수 확인됐다. 하지만 기존 84% divergent 판정은 플라스미드가 다르거나 sequencing failure라는 증거가 아니다. 전체 plasmid sequence accuracy나 분자별 intact 비율은 아직 확정할 수 없다.
