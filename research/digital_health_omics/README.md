# Digital Health Omics Research Scout

PubMed-based research topic scouting for **Digital Health × Genomics/Proteomics** with two parallel routes:

1. **Global route** — scans PubMed broadly for Digital Health + omics papers.
2. **SKKU route** — scans the same research space but restricts papers to Sungkyunkwan University affiliations.

The outputs are compared to identify topics that are growing globally but underrepresented at SKKU.

## MVP workflow

```text
PubMed
  ├─ Global query
  └─ SKKU affiliation query
        ↓
Title / abstract / metadata extraction
        ↓
Digital-health axis tagging
        ×
Omics axis tagging
        ×
Disease axis tagging
        ↓
Topic counts + publication growth
        ↓
Global vs SKKU coverage comparison
        ↓
Research opportunity ranking
```

## Current scope

Digital-health axes:
- wearable / sensor
- digital biomarker / phenotype
- EHR / real-world data
- remote monitoring / telemedicine
- AI / machine learning
- mobile health

Omics axes:
- genomics / GWAS / PRS
- transcriptomics / RNA-seq / single-cell
- proteomics / pQTL
- metabolomics
- multi-omics

Disease axes currently include stroke, cardiovascular disease, diabetes/metabolic disease, cancer, neurodegeneration, aging/frailty, and an "other" bucket.

## SKKU definition

The first version uses PubMed affiliation matching based on:

- `"Sungkyunkwan University"[Affiliation]`
- `"Sungkyunkwan University School of Medicine"[Affiliation]`
- `"Sungkyunkwan Univ"[Affiliation]`

Samsung Medical Center alone is **not** treated as SKKU, which reduces false-positive institutional attribution.

## Install

```bash
cd research/digital_health_omics
pip install -r requirements.txt
```

## Run

Run both routes and the comparison:

```bash
python scout.py --route both --start-year 2020 --end-year 2026 --max-records 3000
```

Run only Global:

```bash
python scout.py --route global --start-year 2020 --end-year 2026 --max-records 3000
```

Run only SKKU:

```bash
python scout.py --route skku --start-year 2020 --end-year 2026 --max-records 3000
```

Optional NCBI identity settings:

```bash
export NCBI_EMAIL="your_email@example.com"
export NCBI_API_KEY="..."
```

The script works without an API key, but NCBI rate limits apply.

## Outputs

Each run creates a timestamped folder under `outputs/`.

Typical files:

```text
outputs/<timestamp>/
├─ global_papers.csv
├─ global_topics.csv
├─ skku_papers.csv
├─ skku_topics.csv
├─ global_vs_skku_opportunities.csv
└─ run_summary.json
```

### Main comparison metric

`opportunity_score` is intentionally transparent in the MVP. It rewards:

- high global publication volume,
- strong recent global growth,
- low SKKU topic coverage,
- sufficient evidence size.

It is a scouting score, not a statistical significance measure.

## Planned V2

- PubTator3 entity extraction for genes, proteins, diseases, chemicals
- BERTopic / biomedical embeddings for unsupervised topic discovery
- OpenAlex citation and institution metadata
- gene/protein ↔ disease knowledge graph
- review saturation detection
- LLM-generated research questions constrained by evidence
- PI / department mapping inside SKKU
- automatic weekly refresh and trend alerts

## Intended use

The tool is designed to answer questions such as:

- Which Digital Health + proteomics topics are growing fastest?
- Which genomics-based digital phenotype studies are underrepresented at SKKU?
- What globally emerging omics topics could be suitable for an SKKU master's thesis?
- Where does SKKU already have a strong publication footprint versus a clear research gap?


## Thesis proposal package

The 2026 thesis-planning layer is available under `proposals/`:

- `proposals/top3_thesis_proposals_2026.md` — ranked All of Us-first thesis designs
- `proposals/allofus_cdrv9_stage0.md` — Stage 0 multimodal overlap / go-pivot feasibility plan

The recommended sequence is:

1. confirm All of Us Controlled Tier access,
2. calculate Fitbit × proteomics × WGS × EHR overlap,
3. proceed with the wearable–proteomics project when overlap is sufficient,
4. otherwise pivot to wearable × genomics × ADRD while retaining the same digital phenotype pipeline.


### All of Us CDRv9 Stage 0

Run `notebooks/AoU_CDRv9_Stage0.ipynb` inside an All of Us Researcher Workbench 2.0 **Controlled Tier** workspace.

It is intentionally a one-run-cell notebook and performs:

- Fitbit / EHR BigQuery table discovery
- WGS and proteomics sample-resource discovery
- Fitbit × Proteomics × WGS × EHR overlap counts
- >=21 / >=30 day wearable sleep QC
- first-pass mean/SD sleep duration, efficiency, activity and steps phenotypes
- automatic GO / CONDITIONAL / PIVOT decision for Proposal 1 vs Proposal 2
- aggregate-only output export

CDRv9 already includes Olink proteomics plus cis-pQTL and fine-mapped pQTL resources, so the recommended causal layer is to reuse those pQTL results rather than estimate de novo pQTLs in the ~10k proteomics subset.
