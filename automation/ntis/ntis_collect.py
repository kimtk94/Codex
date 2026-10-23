#!/usr/bin/env python3
"""NTIS project ingest: read-only API, lossless XML fields and CSV exports."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

URL = "https://www.ntis.go.kr/rndopen/openApi/pjtSearch/project"
TOPICS = {
    "NGS": ["NGS", "sequencing", "차세대염기서열", "유전체", "전장유전체", "WGS", "WES"],
    "RNA": ["RNA-seq", "RNA sequencing", "전사체", "단일세포", "single-cell", "spatial transcriptomics"],
    "Proteomics": ["proteomics", "단백체", "질량분석", "LC-MS"],
    "Metabolomics": ["metabolomics", "대사체", "메타볼로믹스"],
}
FIELDS = ["project_id", "title", "researcher", "institution", "year", "budget_raw",
          "topic_labels", "matched_terms", "source", "source_query", "raw_json"]

def local_name(tag):
    return tag.split("}")[-1].lower()

def flatten(item):
    out = {}
    for el in item.iter():
        if el is item or len(el):
            continue
        value = (el.text or "").strip()
        if value:
            k = local_name(el.tag)
            out[k] = (out[k] + " | " + value) if k in out else value
    return out

def first(d, *names):
    for name in names:
        if d.get(name):
            return d[name]
    return ""

def classify(d):
    haystack = " ".join(str(x) for x in d.values()).lower()
    found = {k: [t for t in vals if t.lower() in haystack] for k, vals in TOPICS.items()}
    return [k for k,v in found.items() if v], sorted(set(t for vals in found.values() for t in vals))

def records_from_xml(body):
    root = ET.fromstring(body)
    errors = [(local_name(x.tag), (x.text or "").strip()) for x in root.iter()
              if local_name(x.tag) in ("error", "errormessage", "errmsg")]
    if errors:
        raise RuntimeError("NTIS error response: " + str(errors)[:500])
    # NTIS XML formats can vary by approved service; fail closed if no identifiable record.
    items = [x for x in root.iter() if local_name(x.tag) in ("item", "record", "result", "project")]
    items = [x for x in items if any(len(y) == 0 and (y.text or "").strip() for y in x.iter())]
    if not items:
        if any(local_name(x.tag) in ("totalcount","totalcnt") and (x.text or "").strip() == "0" for x in root.iter()):
            return []
        raise RuntimeError("Unrecognized XML record layout; inspect schema before scheduling")
    return [flatten(x) for x in items]

def normalize(raw, query):
    title = first(raw, "pjtnm","projectname","projecttitle","pjt_nm","title","rchtitle","rchnm")
    researcher = first(raw, "rchrnm","researchername","researcher","pi","pjnm","rscnm")
    institution = first(raw, "orgnm","orgname","institution","agencyname","mngorgnm","performorgnm")
    year = first(raw, "pyear","year","researchyear","py","prjyear")
    budget = first(raw, "govfund","budget","totalfund","researchfund","totfund","govexpense")
    pid = first(raw, "pjtno","projectid","projectno","pjt_id","prjno","pjtcode")
    if not pid:
        pid = "hash:" + hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]
    labels, terms = classify(raw)
    return dict(project_id=pid,title=title,researcher=researcher,institution=institution,
                year=year,budget_raw=budget,topic_labels=";".join(labels),
                matched_terms=";".join(terms),source="NTIS",source_query=query,
                raw_json=json.dumps(raw, ensure_ascii=False,sort_keys=True))

def fetch(key, keyword, position, count, year=None):
    params = {"apprvKey":key,"SRWR":keyword,"collection":"project",
              "searchFd":"BI","startPosition":position,"displayCnt":count}
    if year is not None:
        params["addQuery"] = f"PY={year}/SAME"
    url = URL + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent":"ntis-rnd-pipeline/0.1"})
    with urllib.request.urlopen(request, timeout=35) as response:
        return response.read()

def run(args):
    key = os.getenv("NTIS_API_KEY","").strip()
    if not key:
        raise SystemExit("Missing NTIS_API_KEY; set GitHub Actions secret (never commit it)")
    out = Path(args.output)
    out.mkdir(parents=True,exist_ok=True)
    all_rows = {}
    audit = []
    truncated = []
    for keyword in args.keywords:
        for year in range(args.start_year,args.end_year+1):
            completed = False
            seen_pages = set()
            for page in range(args.max_pages):
                position = 1 + page*args.page_size
                for attempt in range(3):
                    try:
                        recs = records_from_xml(fetch(key,keyword,position,args.page_size,year))
                        break
                    except Exception as exc:
                        if attempt == 2:
                            raise RuntimeError(f"API failed for keyword={keyword!r} year={year} position={position}: {type(exc).__name__}") from None
                        time.sleep(2**attempt)
                signature = hashlib.sha256(json.dumps(recs,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                if signature in seen_pages and recs:
                    raise RuntimeError(f"Repeated API page: query={keyword!r} year={year} position={position}; verify pagination")
                seen_pages.add(signature)
                audit.append({"query":keyword,"year":year,"position":position,"records":len(recs)})
                for rec in recs:
                    row = normalize(rec,keyword)
                    dedup_key = (row["project_id"], year)
                    if dedup_key in all_rows:
                        previous=all_rows[dedup_key]
                        merged=set(filter(None,previous["source_query"].split(";"))) | {keyword}
                        previous["source_query"]=";".join(sorted(merged))
                    else:
                        all_rows[dedup_key]=row
                if len(recs) < args.page_size:
                    completed = True
                    break
                time.sleep(args.delay)
            if not completed:
                truncated.append({"query":keyword,"year":year,"max_pages":args.max_pages})
    rows = list(all_rows.values())
    with (out/"ntis_projects.csv").open("w",newline="",encoding="utf-8-sig") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader();writer.writerows(rows)
    with (out/"ntis_sales_candidates.csv").open("w",newline="",encoding="utf-8-sig") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader()
        writer.writerows([r for r in rows if r["topic_labels"]])
    with (out/"ntis_audit.json").open("w",encoding="utf-8") as f:
        json.dump({"records":len(rows),"requests":audit,"truncated":truncated,"complete":not bool(truncated),"warning":"budget_raw is unnormalized; verify NTIS units and schema"},f,ensure_ascii=False,indent=2)
    print(json.dumps({"records":len(rows),"requests":len(audit),"truncated":len(truncated),"output":str(out)},ensure_ascii=False))
    if truncated:
        raise SystemExit(f"Incomplete backfill: {len(truncated)} keyword-year searches reached max-pages; inspect audit JSON")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--keywords",nargs="+",default=["NGS","RNA-seq","유전체","단백체","대사체"])
    p.add_argument("--start-year",type=int,default=2021)
    p.add_argument("--end-year",type=int,default=2026)
    p.add_argument("--page-size",type=int,default=20)
    p.add_argument("--max-pages",type=int,default=500)
    p.add_argument("--delay",type=float,default=0.5)
    p.add_argument("--output",default="outputs/ntis")
    a=p.parse_args()
    if a.end_year<a.start_year or not (1<=a.page_size<=100) or a.max_pages<1:
        p.error("Invalid year range/page size/max pages")
    run(a)
