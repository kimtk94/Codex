# Genixcure PCR 11개 — 재분석 현황 및 방향성 검증
작성일: 2026-11-04

## 실측 완료
- 원본 FASTQ 재분석: **11/11 완료**, 요약에 오류 0건
- 총 raw paired reads: **122,503,246**
- QC 후 병합 reads: **121,054,807**
- 이전 병합 reads: **121,171,826**
- 이전 대비 병합 read 차이: **-117,019** (필터, merge 판단 차이 등 복합)
- 각 샘플 Primer 분류별 read_count 합계 = QC 병합 read_count: **11/11 PASS**
- 기존 Unique CSV 11개 백업 사본 및 별도 backup manifest 존재

## 샘플별 재분석 통계
| 샘플 | Raw pairs | QC merged | Both-end reads | Single-end reads | Single-end unique | 오류 |
|---|---:|---:|---:|---:|---:|---|
| PCR_6_13 | 15,313,314 | 14,538,899 | 13,481,009 | 1,034,099 | 817,878 | - |
| Brain_1 | 11,797,745 | 11,654,039 | 0 | 10,898,997 | 120,938 | - |
| Brain_2 | 8,994,002 | 8,871,284 | 0 | 8,315,535 | 114,240 | - |
| Brain_3 | 10,168,710 | 10,094,883 | 0 | 9,584,968 | 57,091 | - |
| Motor_1 | 11,316,426 | 11,272,084 | 0 | 10,728,321 | 67,269 | - |
| Motor_2 | 11,667,503 | 11,624,777 | 0 | 11,058,258 | 91,115 | - |
| Motor_3 | 11,892,569 | 11,844,009 | 0 | 11,205,422 | 104,121 | - |
| SH_SY5Y_1 | 10,006,137 | 9,958,764 | 0 | 9,479,127 | 94,257 | - |
| SH_SY5Y_2 | 10,157,495 | 10,103,856 | 0 | 9,661,598 | 67,470 | - |
| SH_SY5Y_3 | 10,378,410 | 10,322,913 | 0 | 9,783,882 | 97,893 | - |
| Input | 10,810,935 | 10,769,299 | 0 | 10,389,126 | 48,243 | - |

## 10개 일반 PCR 샘플의 정확한 역상보 중복 검사
- 검사한 single_end reads: **101,105,234**
- 합산 unique 전/후: **862,637 → 751,161**
- 감소: **111,476 (12.92%)**
- 읽기 가중 20-mer 말단 A...RC(B) / B...RC(A) 패턴: **89,130,744 (88.16%)**
- Count 보존 검증: **PASS**
- 샘플별 분리 집계; 샘플 간 unique 통합하지 않음

## 해석상 주의
1. PCR_6_13은 QC 병합 read 중 양쪽 제공 AAV primer가 92.7% 검출되며, 나머지 10개는 두 primer 동시 검출이 0%. **라이브러리 설계 차이 검증 전 동일한 trimmed subset으로 비교하지 말 것.**
2. PCR_6_13 `both_end`에서 여전히 **3,788,424 unique / 1,486,271 singleton** 관측. Primer 제거만으로 과도한 다양성이 해소된 것은 아님.
3. `merged_qc_failed=0`은 **fastp를 통과해 병합된 read에 추가 적용한 품질검사 탈락이 0**이라는 뜻. 원본 모든 read의 품질 문제가 없다는 뜻이 아님.
4. Exact reverse-complement normalization은 동일 읽기 서열의 방향 중복만 줄이고 PCR·시퀀싱 오류, UMI 부재, 생물학적 변이 여부를 해결하지 않음.
5. 실제 primer/adapter/index 및 construct 설계 검증과 저빈도 singleton 오류 분석은 **미완료**.

## 검증 자료
- Google Drive: `Genixcure_PCR_Merge_Analysis/PCR_11_Reanalysis_QC_v2/PCR_11_reanalysis_summary.csv`
- Primer 방향 검증: `Genixcure_10_Sample_Orientation_Audit_v3.json`
- 기존 결과 백업: `Genixcure_PCR_Merge_Analysis/Backup_PreReanalysis_2026-11-03`
