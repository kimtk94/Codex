#!/usr/bin/env python3
"""V2 thesis-topic ranker for Digital Health × Omics Scout.

Consumes one scout output directory and produces:
- original-article-only topic summaries and Global-vs-SKKU gaps
- review/protocol saturation diagnostics
- PubTator gene/disease/chemical/variant annotations for priority papers
- SKKU researcher matching
- evidence-constrained master's thesis candidate questions

The ranker intentionally keeps scoring transparent and deterministic.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd
import requests

from scout import compare_global_skku, summarize_topics

HERE = Path(__file__).resolve().parent
PUBTATOR_URL = "https://www.ncbi.nlm.nih.gov/research/pubtator-api/publications/export/pubtator"

EXCLUDED_PUBLICATION_TYPES = {
    "review",
    "systematic review",
    "meta-analysis",
    "editorial",
    "comment",
    "letter",
    "news",
    "guideline",
    "practice guideline",
    "consensus development conference",
    "published erratum",
    "retracted publication",
    "retraction of publication",
}

TITLE_EXCLUDE_PATTERNS = [
    r"\bprotocol\b",
    r"\bstudy protocol\b",
    r"\bconference\b",
    r"\bcongress\b",
    r"\bmeeting report\b",
    r"\bexecutive summary\b",
    r"\bposition statement\b",
]

PRIORITY_OMICS = {"genomics", "proteomics", "multiomics"}


def split_semicolon(value) -> List[str]:
    if pd.isna(value):
        return []
    return [x.strip() for x in str(value).split(";") if x.strip()]


def classify_article(row: pd.Series) -> str:
    ptypes = {x.lower() for x in split_semicolon(row.get("publication_types", ""))}
    title = str(row.get("title", "") or "").lower()

    if ptypes & EXCLUDED_PUBLICATION_TYPES:
        if "review" in ptypes or "systematic review" in ptypes or "meta-analysis" in ptypes:
            return "review"
        return "non_original"
    if any(re.search(p, title, flags=re.I) for p in TITLE_EXCLUDE_PATTERNS):
        return "protocol_or_summary"

    # Most PubMed original research carries Journal Article, Clinical Trial,
    # Observational Study, Comparative Study, Validation Study, etc.
    return "original"


def add_article_class(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["article_class"] = out.apply(classify_article, axis=1)
    out["is_original"] = out["article_class"].eq("original")
    return out


def topic_components(topic_key: str) -> Tuple[str, str, str]:
    parts = [x.strip() for x in str(topic_key).split("×")]
    while len(parts) < 3:
        parts.append("other")
    return parts[0], parts[1], parts[2]


def row_has_topic(row: pd.Series, topic_key: str) -> bool:
    digital, omics, disease = topic_components(topic_key)
    return (
        digital in split_semicolon(row.get("digital_axes", ""))
        and omics in split_semicolon(row.get("omics_axes", ""))
        and disease in split_semicolon(row.get("disease_axes", ""))
    )


def topic_saturation(all_papers: pd.DataFrame, original_papers: pd.DataFrame, topic_key: str, end_year: int) -> dict:
    recent_start = end_year - 2
    a = all_papers[all_papers.apply(lambda r: row_has_topic(r, topic_key), axis=1)]
    o = original_papers[original_papers.apply(lambda r: row_has_topic(r, topic_key), axis=1)]
    ar = a[a["year"].fillna(0).between(recent_start, end_year)]
    orr = o[o["year"].fillna(0).between(recent_start, end_year)]
    total = len(ar)
    original = len(orr)
    non_original = max(total - original, 0)
    ratio = non_original / total if total else 0.0
    return {
        "recent_all_papers": total,
        "recent_original_papers": original,
        "recent_non_original_papers": non_original,
        "non_original_ratio": round(ratio, 4),
    }


def feasibility_weight(digital: str, omics: str) -> float:
    d = {
        "wearable_sensor": 1.18,
        "ehr_rwd": 1.12,
        "digital_biomarker": 1.10,
        "remote_monitoring": 1.05,
        "mobile_health": 1.00,
        "clinical_decision_support": 0.96,
        "digital_therapeutics": 0.90,
        "digital_twin": 0.82,
    }.get(digital, 0.95)
    o = {"genomics": 1.14, "proteomics": 1.16, "multiomics": 1.02}.get(omics, 0.90)
    return d * o


def evidence_sweet_spot(n_recent: int) -> float:
    # Prefer fields with enough evidence to design a thesis but not so saturated
    # that the topic is already extremely crowded. Peak is roughly 25-50 papers.
    if n_recent <= 0:
        return 0.0
    x = math.log1p(n_recent)
    target = math.log1p(35)
    return max(0.55, math.exp(-abs(x - target) / 2.2))


def make_candidate_table(
    original_opportunities: pd.DataFrame,
    global_all: pd.DataFrame,
    global_original: pd.DataFrame,
    end_year: int,
    top_n: int = 30,
) -> pd.DataFrame:
    rows = []
    for _, r in original_opportunities.iterrows():
        digital, omics, disease = topic_components(r["topic_key"])
        if omics not in PRIORITY_OMICS:
            continue
        sat = topic_saturation(global_all, global_original, r["topic_key"], end_year)
        n = int(r["global_recent_3y"])
        feasibility = feasibility_weight(digital, omics)
        sweet = evidence_sweet_spot(n)
        original_quality = max(0.55, 1.0 - 0.45 * sat["non_original_ratio"])
        skku_gap_boost = 1.15 if float(r["skku_recent_3y"]) == 0 else 1.0
        score = float(r["opportunity_score"]) * feasibility * sweet * original_quality * skku_gap_boost

        rows.append(
            {
                **r.to_dict(),
                "digital_axis": digital,
                "omics_axis": omics,
                "disease_axis": disease,
                **sat,
                "feasibility_weight": round(feasibility, 4),
                "evidence_sweet_spot": round(sweet, 4),
                "thesis_score": round(score, 4),
            }
        )
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).sort_values(
        ["thesis_score", "global_recent_3y", "global_papers"],
        ascending=[False, False, False],
    )
    out["candidate_rank"] = range(1, len(out) + 1)
    return out.head(top_n).reset_index(drop=True)


def supporting_papers_for_topic(
    papers: pd.DataFrame,
    topic_key: str,
    end_year: int,
    n: int = 5,
) -> pd.DataFrame:
    x = papers[papers.apply(lambda r: row_has_topic(r, topic_key), axis=1)].copy()
    if x.empty:
        return x
    x["year_sort"] = pd.to_numeric(x["year"], errors="coerce").fillna(0)
    x["has_abstract"] = x["abstract"].fillna("").str.len().gt(100)
    return x.sort_values(["year_sort", "has_abstract"], ascending=[False, False]).head(n)


def fetch_pubtator(pmids: List[str], batch_size: int = 80) -> pd.DataFrame:
    """Retrieve PubTator annotations. Failure is non-fatal."""
    records = []
    session = requests.Session()
    pmids = [str(x) for x in pmids if str(x).strip()]
    for i in range(0, len(pmids), batch_size):
        batch = pmids[i : i + batch_size]
        try:
            r = session.get(
                PUBTATOR_URL,
                params={"pmids": ",".join(batch)},
                timeout=90,
                headers={"User-Agent": "digital-health-omics-scout/2.0"},
            )
            r.raise_for_status()
            text = r.text
        except Exception as e:
            print(f"[WARN] PubTator batch failed: {e}")
            continue

        for line in text.splitlines():
            if not line or "|t|" in line or "|a|" in line:
                continue
            fields = line.split("\t")
            if len(fields) < 6:
                continue
            pmid, start, end, mention, concept_type, concept_id = fields[:6]
            records.append(
                {
                    "pmid": pmid,
                    "mention": mention,
                    "concept_type": concept_type,
                    "concept_id": concept_id,
                }
            )
        time.sleep(0.15)

    return pd.DataFrame(records, columns=["pmid", "mention", "concept_type", "concept_id"])


def aggregate_entities(ann: pd.DataFrame) -> pd.DataFrame:
    if ann.empty:
        return pd.DataFrame(columns=["pmid", "genes_proteins", "diseases", "chemicals", "variants"])

    out = []
    for pmid, g in ann.groupby("pmid"):
        by_type = defaultdict(list)
        for _, r in g.iterrows():
            typ = str(r["concept_type"]).lower()
            mention = str(r["mention"]).strip()
            if mention:
                by_type[typ].append(mention)

        def uniq(values):
            return "; ".join(dict.fromkeys(values))

        genes = by_type.get("gene", []) + by_type.get("protein", [])
        variants = by_type.get("mutation", []) + by_type.get("variant", [])
        out.append(
            {
                "pmid": str(pmid),
                "genes_proteins": uniq(genes),
                "diseases": uniq(by_type.get("disease", [])),
                "chemicals": uniq(by_type.get("chemical", [])),
                "variants": uniq(variants),
            }
        )
    return pd.DataFrame(out)


def top_entities_for_topic(
    papers: pd.DataFrame,
    entity_by_pmid: Dict[str, dict],
    topic_key: str,
    column: str,
    limit: int = 8,
) -> str:
    subset = papers[papers.apply(lambda r: row_has_topic(r, topic_key), axis=1)]
    counter = Counter()
    for pmid in subset["pmid"].astype(str):
        values = entity_by_pmid.get(pmid, {}).get(column, "")
        for v in split_semicolon(values):
            counter[v] += 1
    return "; ".join(x for x, _ in counter.most_common(limit))


def build_researcher_profiles(skku_papers: pd.DataFrame) -> pd.DataFrame:
    profiles = {}
    for _, row in skku_papers.iterrows():
        authors = split_semicolon(row.get("skku_authors", ""))
        if not authors:
            continue
        for author in authors:
            p = profiles.setdefault(
                author,
                {
                    "skku_author": author,
                    "paper_count": 0,
                    "pmids": [],
                    "digital_axes": Counter(),
                    "omics_axes": Counter(),
                    "disease_axes": Counter(),
                    "recent_titles": [],
                },
            )
            p["paper_count"] += 1
            p["pmids"].append(str(row.get("pmid", "")))
            p["digital_axes"].update(split_semicolon(row.get("digital_axes", "")))
            p["omics_axes"].update(split_semicolon(row.get("omics_axes", "")))
            p["disease_axes"].update(split_semicolon(row.get("disease_axes", "")))
            if int(row.get("year") or 0) >= 2024 and row.get("title"):
                p["recent_titles"].append(str(row["title"]))

    rows = []
    for p in profiles.values():
        rows.append(
            {
                "skku_author": p["skku_author"],
                "paper_count": p["paper_count"],
                "pmids": "; ".join(dict.fromkeys(p["pmids"])),
                "digital_axes": ";".join(p["digital_axes"].keys()),
                "omics_axes": ";".join(p["omics_axes"].keys()),
                "disease_axes": ";".join(p["disease_axes"].keys()),
                "recent_titles": " | ".join(p["recent_titles"][:4]),
            }
        )
    return pd.DataFrame(rows)


def match_researchers(candidates: pd.DataFrame, profiles: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty or profiles.empty:
        return pd.DataFrame(
            columns=["candidate_rank", "topic_key", "skku_author", "match_score", "match_reason", "paper_count", "recent_titles"]
        )

    rows = []
    for _, c in candidates.iterrows():
        for _, p in profiles.iterrows():
            score = 0
            reasons = []
            if c["omics_axis"] in split_semicolon(p["omics_axes"]):
                score += 5
                reasons.append(f"omics:{c['omics_axis']}")
            if c["disease_axis"] in split_semicolon(p["disease_axes"]):
                score += 3
                reasons.append(f"disease:{c['disease_axis']}")
            if c["digital_axis"] in split_semicolon(p["digital_axes"]):
                score += 2
                reasons.append(f"digital:{c['digital_axis']}")
            # Adjacent expertise gets a small credit, useful when SKKU has a true gap.
            if score == 0 and p["paper_count"] >= 2 and c["omics_axis"] in {"genomics", "proteomics"}:
                if any(x in split_semicolon(p["omics_axes"]) for x in ["genomics", "proteomics", "multiomics"]):
                    score = 1
                    reasons.append("adjacent_omics")
            if score > 0:
                rows.append(
                    {
                        "candidate_rank": int(c["candidate_rank"]),
                        "topic_key": c["topic_key"],
                        "skku_author": p["skku_author"],
                        "match_score": score,
                        "match_reason": ", ".join(reasons),
                        "paper_count": int(p["paper_count"]),
                        "recent_titles": p["recent_titles"],
                    }
                )
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).sort_values(
        ["candidate_rank", "match_score", "paper_count"],
        ascending=[True, False, False],
    )
    return out.groupby("candidate_rank", group_keys=False).head(5).reset_index(drop=True)


def question_template(digital: str, omics: str, disease: str, genes: str) -> Tuple[str, str]:
    disease_label = disease.replace("_", " ")
    gene_hint = ""
    if genes:
        gene_hint = f" Candidate molecular anchors from the literature include {', '.join(split_semicolon(genes)[:3])}."

    if digital == "wearable_sensor" and omics == "proteomics":
        q = (
            f"Can longitudinal wearable-derived activity, sleep, and cardiovascular phenotypes identify a plasma proteomic "
            f"signature associated with {disease_label}, and does that signature improve prediction beyond clinical covariates?"
        )
        design = "Prospective/retrospective wearable cohort + plasma proteomics; elastic-net/PLS; nested CV; pathway enrichment."
    elif digital == "wearable_sensor" and omics == "genomics":
        q = (
            f"Do polygenic risk or genetic variants modify the association between wearable-derived digital phenotypes and "
            f"{disease_label}, and can an integrated digital-genetic model improve risk stratification?"
        )
        design = "Wearable phenotypes + genotype/PRS; interaction model; calibration/discrimination; ancestry-aware sensitivity analysis."
    elif digital == "ehr_rwd" and omics == "genomics":
        q = (
            f"Can genomic risk integrated with longitudinal EHR/real-world phenotypes improve identification or prognosis of "
            f"{disease_label} compared with clinical variables alone?"
        )
        design = "EHR phenotyping + genomic variants/PRS; temporal validation; external or held-out validation; explainability."
    elif digital == "ehr_rwd" and omics == "proteomics":
        q = (
            f"Can plasma proteomic signatures combined with longitudinal EHR features define clinically actionable subphenotypes "
            f"of {disease_label}?"
        )
        design = "EHR feature engineering + proteomics; unsupervised subtyping followed by outcome validation and pathway interpretation."
    elif digital == "digital_biomarker":
        q = (
            f"Which {omics} features are associated with digital biomarkers of {disease_label}, and can the combined signature "
            f"support earlier or more precise risk stratification?"
        )
        design = "Digital biomarker derivation + omics association + multiple-testing correction + integrated predictive model."
    elif digital == "digital_twin":
        q = (
            f"Can a patient-specific digital twin integrating longitudinal clinical signals and {omics} data improve simulation "
            f"or prediction of {disease_label} trajectories?"
        )
        design = "Retrospective multimodal cohort; mechanistic or state-space digital twin; temporal holdout validation."
    else:
        q = (
            f"Can {digital.replace('_', ' ')} features integrated with {omics} improve phenotyping, prediction, or stratification "
            f"of {disease_label} compared with either modality alone?"
        )
        design = "Multimodal feature integration; baseline vs integrated model; internal validation; biological interpretation."

    return q + gene_hint, design


def add_questions_and_evidence(
    candidates: pd.DataFrame,
    global_original: pd.DataFrame,
    entities: pd.DataFrame,
    end_year: int,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if candidates.empty:
        return candidates, pd.DataFrame()

    entity_map = {
        str(r["pmid"]): r.to_dict()
        for _, r in entities.iterrows()
    } if not entities.empty else {}

    candidate_rows = []
    evidence_rows = []

    for _, c in candidates.iterrows():
        topic = c["topic_key"]
        supp = supporting_papers_for_topic(global_original, topic, end_year=end_year, n=5)
        genes = top_entities_for_topic(supp, entity_map, topic, "genes_proteins")
        diseases = top_entities_for_topic(supp, entity_map, topic, "diseases")
        question, design = question_template(c["digital_axis"], c["omics_axis"], c["disease_axis"], genes)

        x = c.to_dict()
        x.update(
            {
                "top_genes_proteins": genes,
                "pubtator_diseases": diseases,
                "research_question": question,
                "suggested_design": design,
                "supporting_pmids": "; ".join(supp["pmid"].astype(str).tolist()),
                "supporting_titles": " | ".join(supp["title"].astype(str).tolist()),
            }
        )
        candidate_rows.append(x)

        for _, p in supp.iterrows():
            ent = entity_map.get(str(p["pmid"]), {})
            evidence_rows.append(
                {
                    "candidate_rank": int(c["candidate_rank"]),
                    "topic_key": topic,
                    "pmid": str(p["pmid"]),
                    "year": p["year"],
                    "title": p["title"],
                    "journal": p.get("journal", ""),
                    "genes_proteins": ent.get("genes_proteins", ""),
                    "diseases": ent.get("diseases", ""),
                    "pubmed_url": p.get("pubmed_url", ""),
                }
            )

    return pd.DataFrame(candidate_rows), pd.DataFrame(evidence_rows)


def select_pubtator_pmids(candidates: pd.DataFrame, global_original: pd.DataFrame, skku_papers: pd.DataFrame, end_year: int) -> List[str]:
    selected = []
    for _, c in candidates.head(20).iterrows():
        s = supporting_papers_for_topic(global_original, c["topic_key"], end_year=end_year, n=8)
        selected.extend(s["pmid"].astype(str).tolist())
    selected.extend(skku_papers["pmid"].astype(str).tolist())
    return list(dict.fromkeys(x for x in selected if x and x != "nan"))[:300]


def write_markdown_summary(candidates: pd.DataFrame, matches: pd.DataFrame, outpath: Path):
    lines = [
        "# SKKU Digital Health × Omics Master's Thesis Candidates",
        "",
        "Ranking is based on original-article evidence, recent global growth, SKKU coverage gap, literature saturation, and practical feasibility.",
        "",
    ]
    for _, c in candidates.head(10).iterrows():
        rank = int(c["candidate_rank"])
        lines += [
            f"## {rank}. {c['topic_key']}",
            "",
            f"- Thesis score: **{c['thesis_score']:.2f}**",
            f"- Global original papers (recent 3y): **{int(c['global_recent_3y'])}**",
            f"- SKKU original papers (recent 3y): **{int(c['skku_recent_3y'])}**",
            f"- Non-original saturation ratio: **{float(c['non_original_ratio']):.1%}**",
            f"- Research question: {c['research_question']}",
            f"- Suggested design: {c['suggested_design']}",
        ]
        if c.get("top_genes_proteins"):
            lines.append(f"- PubTator gene/protein anchors: {c['top_genes_proteins']}")
        if not matches.empty:
            m = matches[matches["candidate_rank"] == rank].head(3)
            if not m.empty:
                lines.append("- SKKU researcher matches: " + "; ".join(
                    f"{r['skku_author']} (score {int(r['match_score'])})" for _, r in m.iterrows()
                ))
        lines.append("")
    outpath.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", type=Path, required=True)
    ap.add_argument("--end-year", type=int, required=True)
    ap.add_argument("--top-n", type=int, default=30)
    ap.add_argument("--skip-pubtator", action="store_true")
    args = ap.parse_args()

    indir = args.input_dir
    global_all = add_article_class(pd.read_csv(indir / "global_papers.csv"))
    skku_all = add_article_class(pd.read_csv(indir / "skku_papers.csv"))

    global_original = global_all[global_all["is_original"]].copy()
    skku_original = skku_all[skku_all["is_original"]].copy()

    global_topics = summarize_topics(global_original, args.end_year)
    skku_topics = summarize_topics(skku_original, args.end_year)
    original_opp = compare_global_skku(global_topics, skku_topics)

    global_all.to_csv(indir / "global_papers_classified.csv", index=False)
    skku_all.to_csv(indir / "skku_papers_classified.csv", index=False)
    global_topics.to_csv(indir / "global_original_topics.csv", index=False)
    skku_topics.to_csv(indir / "skku_original_topics.csv", index=False)
    original_opp.to_csv(indir / "global_vs_skku_original_opportunities.csv", index=False)

    candidates = make_candidate_table(
        original_opp, global_all, global_original, args.end_year, top_n=args.top_n
    )

    pmids = select_pubtator_pmids(candidates, global_original, skku_all, args.end_year)
    annotations = pd.DataFrame(columns=["pmid", "mention", "concept_type", "concept_id"])
    if not args.skip_pubtator and pmids:
        print(f"[PubTator] requesting {len(pmids)} priority PMIDs")
        annotations = fetch_pubtator(pmids)
    entities = aggregate_entities(annotations)

    annotations.to_csv(indir / "pubtator_annotations.csv", index=False)
    entities.to_csv(indir / "pubtator_entities_by_pmid.csv", index=False)

    candidates, evidence = add_questions_and_evidence(
        candidates, global_original, entities, args.end_year
    )

    profiles = build_researcher_profiles(skku_all)
    matches = match_researchers(candidates, profiles)

    candidates.to_csv(indir / "master_thesis_candidates.csv", index=False)
    evidence.to_csv(indir / "candidate_supporting_papers.csv", index=False)
    profiles.to_csv(indir / "skku_researcher_profiles.csv", index=False)
    matches.to_csv(indir / "skku_researcher_matches.csv", index=False)
    write_markdown_summary(candidates, matches, indir / "master_thesis_candidates.md")

    summary = {
        "global_all": int(len(global_all)),
        "global_original": int(len(global_original)),
        "skku_all": int(len(skku_all)),
        "skku_original": int(len(skku_original)),
        "candidate_count": int(len(candidates)),
        "pubtator_pmids_requested": int(len(pmids)),
        "pubtator_annotations": int(len(annotations)),
        "skku_researcher_profiles": int(len(profiles)),
    }
    (indir / "v2_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("\n=== V2 SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print("\n=== MASTER THESIS TOP 10 ===")
    cols = [
        "candidate_rank", "topic_key", "thesis_score", "global_recent_3y",
        "skku_recent_3y", "non_original_ratio", "top_genes_proteins",
        "research_question",
    ]
    print(candidates[cols].head(10).to_string(index=False))

    print("\n=== TOP SKKU RESEARCHER MATCHES ===")
    if matches.empty:
        print("No researcher matches generated.")
    else:
        print(matches.head(30).to_string(index=False))


if __name__ == "__main__":
    main()
