#!/usr/bin/env python3
"""Digital Health × Omics PubMed research scout.

Two routes:
- global: all PubMed papers matching Digital Health + omics
- skku: same concept space restricted to Sungkyunkwan University affiliations

The script creates topic summaries and, when both routes are run,
a Global-vs-SKKU research opportunity table.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
from xml.etree import ElementTree as ET

import pandas as pd
import requests

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
HERE = Path(__file__).resolve().parent

GLOBAL_CORE = r"""(
  ("digital health"[Title/Abstract] OR wearable*[Title/Abstract] OR smartwatch*[Title/Abstract]
   OR "digital biomarker"[Title/Abstract] OR "digital phenotype"[Title/Abstract]
   OR "electronic health record"[Title/Abstract] OR "electronic medical record"[Title/Abstract]
   OR "real-world data"[Title/Abstract] OR "remote monitoring"[Title/Abstract]
   OR telemedicine[Title/Abstract] OR telehealth[Title/Abstract]
   OR "mobile health"[Title/Abstract] OR mhealth[Title/Abstract]
   OR smartphone*[Title/Abstract] OR "mobile app"[Title/Abstract]
   OR "digital therapeutic"[Title/Abstract] OR "digital therapeutics"[Title/Abstract]
   OR "digital twin"[Title/Abstract] OR "clinical decision support"[Title/Abstract])
  AND
  (genomic*[Title/Abstract] OR GWAS[Title/Abstract] OR "genome-wide association"[Title/Abstract]
   OR "polygenic risk"[Title/Abstract] OR transcriptom*[Title/Abstract]
   OR "RNA-seq"[Title/Abstract] OR proteom*[Title/Abstract] OR pQTL[Title/Abstract]
   OR metabolom*[Title/Abstract] OR "multi-omics"[Title/Abstract] OR multiomics[Title/Abstract])
)"""

SKKU_AFFILIATION = r"""(
  "Sungkyunkwan University"[Affiliation]
  OR "Sungkyunkwan University School of Medicine"[Affiliation]
  OR "Sungkyunkwan Univ"[Affiliation]
)"""


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_query(route: str, start_year: int, end_year: int) -> str:
    date_q = f'("{start_year}/01/01"[Date - Publication] : "{end_year}/12/31"[Date - Publication])'
    q = f"({GLOBAL_CORE}) AND {date_q}"
    if route == "skku":
        q = f"({q}) AND {SKKU_AFFILIATION}"
    return re.sub(r"\s+", " ", q).strip()


class PubMedClient:
    def __init__(self, email: str | None = None, api_key: str | None = None):
        self.email = email or os.getenv("NCBI_EMAIL", "")
        self.api_key = api_key or os.getenv("NCBI_API_KEY", "")
        self.session = requests.Session()

    @property
    def pause(self) -> float:
        return 0.11 if self.api_key else 0.36

    def _params(self, **kwargs):
        p = dict(kwargs)
        p["tool"] = "digital_health_omics_scout"
        if self.email:
            p["email"] = self.email
        if self.api_key:
            p["api_key"] = self.api_key
        return p

    def search(self, query: str, max_records: int) -> Tuple[List[str], int]:
        params = self._params(
            db="pubmed",
            term=query,
            retmode="json",
            retmax=max_records,
            sort="pub date",
        )
        r = self.session.get(f"{BASE}/esearch.fcgi", params=params, timeout=60)
        r.raise_for_status()
        data = r.json()["esearchresult"]
        return data.get("idlist", []), int(data.get("count", 0))

    def fetch(self, pmids: List[str], batch_size: int = 200) -> List[dict]:
        rows: List[dict] = []
        for i in range(0, len(pmids), batch_size):
            batch = pmids[i : i + batch_size]
            params = self._params(
                db="pubmed",
                id=",".join(batch),
                retmode="xml",
            )
            r = self.session.get(f"{BASE}/efetch.fcgi", params=params, timeout=90)
            r.raise_for_status()
            rows.extend(parse_pubmed_xml(r.content))
            time.sleep(self.pause)
        return rows


def text_of(node) -> str:
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


def first_text(root, paths: Iterable[str]) -> str:
    for path in paths:
        node = root.find(path)
        value = text_of(node)
        if value:
            return value
    return ""


def parse_year(article) -> int | None:
    candidates = [
        ".//JournalIssue/PubDate/Year",
        ".//ArticleDate/Year",
        ".//PubMedPubDate[@PubStatus='pubmed']/Year",
        ".//PubMedPubDate[@PubStatus='entrez']/Year",
    ]
    for path in candidates:
        x = article.find(path)
        if x is not None and text_of(x).isdigit():
            return int(text_of(x))
    medline = first_text(article, [".//JournalIssue/PubDate/MedlineDate"])
    m = re.search(r"(19|20)\d{2}", medline)
    return int(m.group(0)) if m else None


def parse_pubmed_xml(xml_bytes: bytes) -> List[dict]:
    root = ET.fromstring(xml_bytes)
    rows = []
    for citation in root.findall(".//PubmedArticle"):
        pmid = first_text(citation, [".//MedlineCitation/PMID"])
        title = first_text(citation, [".//Article/ArticleTitle"])
        abstract_nodes = citation.findall(".//Article/Abstract/AbstractText")
        abstract = " ".join(text_of(x) for x in abstract_nodes if text_of(x))
        journal = first_text(citation, [".//Article/Journal/Title", ".//MedlineJournalInfo/MedlineTA"])
        year = parse_year(citation)

        author_names = []
        affiliations = []
        for author in citation.findall(".//Article/AuthorList/Author"):
            collective = first_text(author, ["CollectiveName"])
            if collective:
                author_names.append(collective)
            else:
                fore = first_text(author, ["ForeName"])
                last = first_text(author, ["LastName"])
                name = " ".join(x for x in [fore, last] if x)
                if name:
                    author_names.append(name)
            for aff in author.findall(".//AffiliationInfo/Affiliation"):
                value = text_of(aff)
                if value:
                    affiliations.append(value)

        doi = ""
        for article_id in citation.findall(".//PubmedData/ArticleIdList/ArticleId"):
            if article_id.attrib.get("IdType") == "doi":
                doi = text_of(article_id)
                break

        publication_types = [
            text_of(x)
            for x in citation.findall(".//Article/PublicationTypeList/PublicationType")
            if text_of(x)
        ]

        rows.append(
            {
                "pmid": pmid,
                "year": year,
                "title": title,
                "abstract": abstract,
                "journal": journal,
                "authors": "; ".join(author_names),
                "affiliations": " | ".join(dict.fromkeys(affiliations)),
                "doi": doi,
                "publication_types": "; ".join(publication_types),
                "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
            }
        )
    return rows


def normalize_text(row: pd.Series) -> str:
    return f"{row.get('title', '')} {row.get('abstract', '')}".lower()


def term_match(text: str, term: str) -> bool:
    t = term.lower()
    if len(t) <= 4 and re.fullmatch(r"[a-z0-9-]+", t):
        return re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", text) is not None
    return t in text


def matched_axes(text: str, axis_map: Dict[str, List[str]]) -> List[str]:
    hits = []
    for axis, terms in axis_map.items():
        if any(term_match(text, term) for term in terms):
            hits.append(axis)
    return hits


def annotate_papers(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    out = df.copy()
    digital_col = []
    omics_col = []
    disease_col = []

    for _, row in out.iterrows():
        text = normalize_text(row)
        digital = matched_axes(text, cfg["digital_health_terms"])
        omics = matched_axes(text, cfg["omics_terms"])
        disease = matched_axes(text, cfg["disease_terms"])
        if not disease:
            disease = ["other"]

        digital_col.append(";".join(digital))
        omics_col.append(";".join(omics))
        disease_col.append(";".join(disease))

    out["digital_axes"] = digital_col
    out["omics_axes"] = omics_col
    out["disease_axes"] = disease_col
    return out


def explode_topics(df: pd.DataFrame) -> pd.DataFrame:
    records = []
    for _, row in df.iterrows():
        digital = [x for x in str(row.get("digital_axes", "")).split(";") if x]
        omics = [x for x in str(row.get("omics_axes", "")).split(";") if x]
        diseases = [x for x in str(row.get("disease_axes", "")).split(";") if x] or ["other"]

        for d in digital:
            for o in omics:
                for dis in diseases:
                    records.append(
                        {
                            "pmid": row["pmid"],
                            "year": row["year"],
                            "digital_axis": d,
                            "omics_axis": o,
                            "disease_axis": dis,
                            "topic_key": f"{d} × {o} × {dis}",
                        }
                    )
    return pd.DataFrame(records)


def growth_score(years: List[int], end_year: int) -> Tuple[int, int, float]:
    years = [int(y) for y in years if pd.notna(y)]
    recent = sum(end_year - 2 <= y <= end_year for y in years)
    previous = sum(end_year - 5 <= y <= end_year - 3 for y in years)
    # Smoothed log2 ratio; stable for sparse emerging topics.
    growth = math.log2((recent + 1.0) / (previous + 1.0))
    return recent, previous, growth


def summarize_topics(df: pd.DataFrame, end_year: int) -> pd.DataFrame:
    exploded = explode_topics(df)
    if exploded.empty:
        return pd.DataFrame(
            columns=[
                "topic_key",
                "digital_axis",
                "omics_axis",
                "disease_axis",
                "paper_count",
                "recent_3y",
                "previous_3y",
                "growth_log2",
                "first_year",
                "last_year",
            ]
        )

    rows = []
    for topic, g in exploded.groupby("topic_key"):
        recent, previous, growth = growth_score(g["year"].dropna().astype(int).tolist(), end_year)
        rows.append(
            {
                "topic_key": topic,
                "digital_axis": g["digital_axis"].iloc[0],
                "omics_axis": g["omics_axis"].iloc[0],
                "disease_axis": g["disease_axis"].iloc[0],
                "paper_count": int(g["pmid"].nunique()),
                "recent_3y": recent,
                "previous_3y": previous,
                "growth_log2": round(growth, 4),
                "first_year": int(g["year"].dropna().min()) if g["year"].notna().any() else None,
                "last_year": int(g["year"].dropna().max()) if g["year"].notna().any() else None,
            }
        )

    out = pd.DataFrame(rows)
    return out.sort_values(["recent_3y", "growth_log2", "paper_count"], ascending=[False, False, False])


def compare_global_skku(global_topics: pd.DataFrame, skku_topics: pd.DataFrame) -> pd.DataFrame:
    g = global_topics.copy()
    s = skku_topics.copy()

    keep = ["topic_key", "paper_count", "recent_3y", "previous_3y", "growth_log2"]
    g = g[keep].rename(
        columns={
            "paper_count": "global_papers",
            "recent_3y": "global_recent_3y",
            "previous_3y": "global_previous_3y",
            "growth_log2": "global_growth_log2",
        }
    )
    s = s[keep].rename(
        columns={
            "paper_count": "skku_papers",
            "recent_3y": "skku_recent_3y",
            "previous_3y": "skku_previous_3y",
            "growth_log2": "skku_growth_log2",
        }
    )

    m = g.merge(s, on="topic_key", how="left")
    for c in ["skku_papers", "skku_recent_3y", "skku_previous_3y", "skku_growth_log2"]:
        m[c] = m[c].fillna(0)

    # Coverage is intentionally capped to keep sparse global topics from producing odd ratios.
    m["skku_coverage"] = (m["skku_papers"] / m["global_papers"].clip(lower=1)).clip(0, 1)

    # Evidence component grows sub-linearly with global size.
    evidence = m["global_recent_3y"].apply(lambda x: math.log1p(max(float(x), 0.0)))
    growth = m["global_growth_log2"].clip(lower=-2, upper=4) + 2
    gap = 1 - m["skku_coverage"]

    m["opportunity_score"] = (evidence * growth * gap).round(4)
    m["skku_gap_flag"] = (m["global_recent_3y"] >= 5) & (m["skku_recent_3y"] == 0)

    return m.sort_values(
        ["opportunity_score", "global_recent_3y", "global_papers"],
        ascending=[False, False, False],
    )


def save_route(route: str, papers: pd.DataFrame, topics: pd.DataFrame, outdir: Path):
    papers.to_csv(outdir / f"{route}_papers.csv", index=False)
    topics.to_csv(outdir / f"{route}_topics.csv", index=False)


def route_run(
    route: str,
    client: PubMedClient,
    cfg: dict,
    start_year: int,
    end_year: int,
    max_records: int,
) -> Tuple[pd.DataFrame, pd.DataFrame, dict]:
    query = build_query(route, start_year, end_year)
    print(f"\n[{route.upper()}] PubMed query:\n{query}\n")
    pmids, total_count = client.search(query, max_records=max_records)
    print(f"[{route.upper()}] PubMed matched {total_count:,}; fetching {len(pmids):,} records.")
    rows = client.fetch(pmids)
    papers = annotate_papers(pd.DataFrame(rows), cfg)
    topics = summarize_topics(papers, end_year=end_year)

    meta = {
        "route": route,
        "query": query,
        "pubmed_total_count": total_count,
        "records_fetched": len(papers),
        "topic_count": len(topics),
    }
    return papers, topics, meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--route", choices=["global", "skku", "both"], default="both")
    parser.add_argument("--start-year", type=int, default=2020)
    parser.add_argument("--end-year", type=int, default=datetime.now().year)
    parser.add_argument("--max-records", type=int, default=5000)
    parser.add_argument("--config", type=Path, default=HERE / "config.json")
    parser.add_argument("--output-dir", type=Path, default=HERE / "outputs")
    args = parser.parse_args()

    if args.start_year > args.end_year:
        raise SystemExit("--start-year must be <= --end-year")
    if args.max_records < 1:
        raise SystemExit("--max-records must be >= 1")

    cfg = load_config(args.config)
    client = PubMedClient()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = args.output_dir / stamp
    outdir.mkdir(parents=True, exist_ok=True)

    routes = ["global", "skku"] if args.route == "both" else [args.route]
    results = {}
    summary = {
        "created_utc": stamp,
        "start_year": args.start_year,
        "end_year": args.end_year,
        "max_records_per_route": args.max_records,
        "routes": {},
    }

    for route in routes:
        papers, topics, meta = route_run(
            route,
            client,
            cfg,
            args.start_year,
            args.end_year,
            args.max_records,
        )
        save_route(route, papers, topics, outdir)
        results[route] = (papers, topics)
        summary["routes"][route] = meta

    if args.route == "both":
        opportunities = compare_global_skku(results["global"][1], results["skku"][1])
        opportunities.to_csv(outdir / "global_vs_skku_opportunities.csv", index=False)

        print("\nTop Global-vs-SKKU opportunities:")
        cols = [
            "topic_key",
            "global_recent_3y",
            "skku_recent_3y",
            "global_growth_log2",
            "opportunity_score",
        ]
        print(opportunities[cols].head(20).to_string(index=False))

    with (outdir / "run_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\nSaved outputs to: {outdir}")


if __name__ == "__main__":
    main()
