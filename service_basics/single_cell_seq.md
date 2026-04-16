# Single Cell Sequencing 기본 정보

## 중요 우선 참고 (tissue type별 권장)
- `service_basics/single_cell_tissue_recommendation.md`를 Single Cell 서비스의 tissue type별 Single Cell/Single Nuclei 선택 기준으로 우선 참고합니다.
- 기존 single cell manual과 충돌 시, tissue type 선택 관련 내용은 위 권장 가이드를 우선 적용합니다.

## 1) Sample Requirement (manual)
- ## Sample Requirements (SG/Japan lab)7
- Single Cell or Nuclei Concentration and Cell Recovery Target8
- GEM Generation and Library Construction Strategy8
- Sequencing Strategy and Turnaround Time8
- Analysis Contents9
- Cell Ranger9
- Standard Analysis9
- Tested Sample Types10
- 10x Genomics User Manual11

## 2) BI content / Analysis (manual)
- 해당 서비스 블록에서 명확한 BI/Analysis 섹션을 찾지 못함 (수동 확인 필요).

## 3) 권장 output (Gb or M reads)
- | 10x Single Cell with Nanopore sequencing- Singapore + China lab | 10x single cell capture | 4050000 | 3750000 | 1 Need inquiry case by case, and 1 month advance notice before sample collection, as we don't have kit stock. / 2 Only available for 10x 3' expression; / 3 Only available for human and mouse samples; / 4 Nanopore recommends using 1 Flow Cell for target capture 5000 cells. However, if the goal is to analyze low expression of transcripts or quantify genes, increasing the number of cells for sequencing is recommended for clients. |
- |  | NovaSeq Sequencing / Mb reads | 12000 | 10500 | Recommend 25000 read paris per nuclei for sequencing. |

## 4) 금액 (Sales Price, WON)
| 10x Single Cell Gene Expression Sequencing / (PE150)-Singapore lab | Tissue dissociation | 225000 | 180000 |  |
|  | Nuclei isolation | 825000 | 660000 |  |
|  | 10x single cell capture and 3' gene expression library | 4050000 | 3750000 | Both GEM-X and NextGEM |
|  | Sequencing NovaSeq X plus / Gb | 9750 | 7500 |  |
|  | Standard analysis / Sample | 375000 | 330000 | If premade library sequencing with data analysis, additional 30 USD per sample is required. |
|  | Cellranger report / Sample | 150000 | 120000 | If premade library sequencing with data analysis, additional 30 USD per sample is required. |
| 10x Single Cell Universal 5' Gene Expression Sequencing / (PE150)-Singapore lab | Tissue dissociation | 225000 | 180000 |  |
|  | 10x single cell capture and 5' gene expression library plus TCR or BCR library | 4950000 | 4500000 | Both GEM-X and NextGEM |
|  | Additional TCR or BCR library prep | 495000 | 450000 | 1. If client requires both TCR and BCR library, please use row 11 plus row 12 pricing to quote. / 2. If client requires only 5' expression library, please use row 11 minus 50 USD per sample to quote. |
|  | Sequencing NovaSeq X plus / Gb | 9750 | 7500 |  |
|  | Standard analysis for 5'+ TCR or 5'+BCR / Sample | 450000 | 405000 |  |
| 10x Single Cell with Nanopore sequencing- Singapore + China lab | 10x single cell capture | 4050000 | 3750000 | 1 Need inquiry case by case, and 1 month advance notice before sample collection, as we don't have kit stock. / 2 Only available for 10x 3' expression; / 3 Only available for human and mouse samples; / 4 Nanopore recommends using 1 Flow Cell for target capture 5000 cells. However, if the goal is to analyze low expression of transcripts or quantify genes, increasing the number of cells for sequencing is recommended for clients. |

---
- Manual source block: `Novogene Product Manual –Single Cell Sequencing`
- Price source section keyword: `Single Cell`