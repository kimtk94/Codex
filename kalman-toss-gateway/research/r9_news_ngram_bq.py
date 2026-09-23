from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import pandas as pd

DEFAULT_EVENTS="/opt/kalman/state/r8_sec/events.json"
DEFAULT_OUT="/opt/kalman/state/r9_news_ngram"

OVERRIDES={
    "AAPL":"Apple Inc",
    "MSFT":"Microsoft",
    "NVDA":"NVIDIA",
    "AMZN":"Amazon",
    "META":"Meta Platforms",
    "GOOG":"Alphabet",
    "GOOGL":"Alphabet",
    "JPM":"JPMorgan Chase",
    "XOM":"ExxonMobil",
    "WMT":"Walmart",
    "UNH":"UnitedHealth Group",

    # Frozen public-name contractions for Web 1Gram / 2Gram matching.
    "AMAT":"Applied Materials",
    "AMD":"Advanced Micro",
    "AMT":"American Tower",
    "BMY":"Bristol Myers",
    "BNY":"BNY Mellon",
    "COF":"Capital One",
    "DHR":"Danaher",
    "IBM":"IBM",
    "LLY":"Eli Lilly",
    "PG":"Procter Gamble",
    "PM":"Philip Morris",
    "QCOM":"Qualcomm",
    "TMO":"Thermo Fisher",
    "UPS":"UPS",
    "USB":"US Bancorp",
    "WFC":"Wells Fargo",

    # Frozen public shorthands for the three names that cannot be represented
    # faithfully as contiguous <=2-token legal-name aliases. Historical source
    # validation still decides whether each alias has usable coverage.
    "BAC":"BofA",
    "JNJ":"J&J",
    "T":"AT&T",
}

SUFFIX_RE=re.compile(
    r"\s+(CORPORATION|CORP|INCORPORATED|INC|COMPANY|CO|PLC|LTD|LIMITED|"
    r"HOLDINGS?|GROUP|N\.V\.|S\.A\.)\.?$",
    re.I,
)
WS_RE=re.compile(r"\s+")

def clean_name(x):
    s=str(x or "").replace("&"," and ")
    s=re.sub(r"[^A-Za-z0-9. -]+"," ",s)
    return WS_RE.sub(" ",s).strip(" .-")

def default_alias(company_name):
    s=clean_name(company_name)
    prev=None
    while s and s!=prev:
        prev=s
        s=SUFFIX_RE.sub("",s).strip()
    return s

def load_registry(events_path):
    rows=json.loads(Path(events_path).read_text())
    by={}
    for e in rows:
        sym=str(e.get("symbol") or "").upper()
        name=str(e.get("company_name") or "").strip()
        if sym and name:
            by.setdefault(sym,[]).append(name)

    out=[]
    for sym,names in sorted(by.items()):
        uniq=sorted(set(names),key=lambda x:(-len(clean_name(x)),clean_name(x)))
        company=uniq[0]
        alias=OVERRIDES.get(sym) or default_alias(company)
        tokens=[x for x in alias.split(" ") if x]
        supported=len(tokens) in {1,2}
        out.append({
            "symbol":sym,
            "company_name":company,
            "alias":alias,
            "alias_lower":alias.lower(),
            "ngram_order":len(tokens),
            "status":"SUPPORTED" if supported else "NEEDS_OVERRIDE",
        })
    return pd.DataFrame(out)

def sql_string(x):
    return str(x).replace("\\","\\\\").replace("'","\\'")

def build_sql(reg,start_int=20240801000000,end_int=20260902000000):
    x=reg.loc[reg["status"]=="SUPPORTED"].copy()
    structs=[]
    for r in x.itertuples(index=False):
        structs.append(
            "STRUCT("
            f"'{sql_string(r.symbol)}' AS symbol, "
            f"'{sql_string(r.alias_lower)}' AS alias_lower, "
            f"{int(r.ngram_order)} AS ngram_order)"
        )
    aliases=",\n    ".join(structs)

    return f"""-- Kalman R9-NG research-only historical mention intensity
-- PIT: downstream hourly features may use completed UTC days only.\n-- Cost-bounded research window: ~25 months, sufficient for the >=24 month readiness gate.
WITH aliases AS (
  SELECT * FROM UNNEST([
    {aliases}
  ])
),
u1 AS (
  SELECT
    a.symbol,
    CAST(SUBSTR(CAST(g.DATE AS STRING), 1, 8) AS INT64) AS day_utc,
    SUM(g.COUNT) AS mention_count
  FROM `gdelt-bq.gdeltv2.web_1grams` g
  JOIN aliases a
    ON a.ngram_order = 1
   AND LOWER(g.NGRAM) = a.alias_lower
  WHERE g.DATE >= {int(start_int)}
    AND g.DATE < {int(end_int)}
    AND g.LANG = 'ENGLISH'
  GROUP BY a.symbol, day_utc
),
u2 AS (
  SELECT
    a.symbol,
    CAST(SUBSTR(CAST(g.DATE AS STRING), 1, 8) AS INT64) AS day_utc,
    SUM(g.COUNT) AS mention_count
  FROM `gdelt-bq.gdeltv2.web_2grams` g
  JOIN aliases a
    ON a.ngram_order = 2
   AND LOWER(g.NGRAM) = a.alias_lower
  WHERE g.DATE >= {int(start_int)}
    AND g.DATE < {int(end_int)}
    AND g.LANG = 'ENGLISH'
  GROUP BY a.symbol, day_utc
)
SELECT symbol, day_utc, SUM(mention_count) AS mention_count
FROM (
  SELECT * FROM u1
  UNION ALL
  SELECT * FROM u2
)
GROUP BY symbol, day_utc
ORDER BY day_utc, symbol
"""

def summarize_result(csv_path,registry_path,out_path):
    reg=pd.read_csv(registry_path)
    x=pd.read_csv(csv_path)

    required={"symbol","day_utc","mention_count"}
    if not required.issubset(x.columns):
        raise RuntimeError(f"missing result columns: {sorted(required-set(x.columns))}")

    x["mention_count"]=pd.to_numeric(x["mention_count"],errors="coerce")
    x["day_utc"]=pd.to_numeric(x["day_utc"],errors="coerce")
    x["date_utc"]=pd.to_datetime(
        x["day_utc"].astype("Int64").astype(str),
        format="%Y%m%d",
        utc=True,
        errors="coerce",
    )

    supported=int(reg["status"].eq("SUPPORTED").sum())
    symbols_with_mentions=int(x.loc[x["mention_count"]>0,"symbol"].nunique())
    duplicates=int(x.duplicated(["symbol","day_utc"]).sum())
    finite_nonnegative=bool(
        x["mention_count"].notna().all() and (x["mention_count"]>=0).all()
    )
    dates=x["date_utc"].dropna()
    span_months=(
        (dates.max()-dates.min()).total_seconds()/86400/30.4375
        if len(dates)>=2 else 0.0
    )

    gates={
        "universe_is_93":len(reg)==93,
        "supported_aliases_ge_90":supported>=90,
        "symbols_with_mentions_ge_80":symbols_with_mentions>=80,
        "usable_span_months_ge_24":span_months>=24,
        "duplicate_symbol_day_zero":duplicates==0,
        "mention_count_finite_nonnegative":finite_nonnegative,
    }
    manifest={
        "schema":"kalman-r9-news-ngram-readiness-v1",
        "research_only":True,
        "production_changed":False,
        "model_fitting_allowed":False,
        "source":"GDELT_BIGQUERY_WEB_1GRAMS_2GRAMS",
        "universe_symbols":len(reg),
        "supported_aliases":supported,
        "unsupported_aliases":int(len(reg)-supported),
        "result_rows":len(x),
        "symbols_with_mentions":symbols_with_mentions,
        "usable_span_months":span_months,
        "duplicate_symbol_day_rows":duplicates,
        "gates":gates,
        "r9_ngram_ready":all(gates.values()),
        "next_action":(
            "PREREGISTER_SINGLE_R9_NGRAM_ABLATION"
            if all(gates.values())
            else "FIX_R9_NGRAM_READINESS"
        ),
    }
    Path(out_path).write_text(json.dumps(manifest,indent=2)+"\n")
    return manifest

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--events",default=DEFAULT_EVENTS)
    ap.add_argument("--output-dir",default=DEFAULT_OUT)
    ap.add_argument("--summarize-csv")
    args=ap.parse_args()

    out=Path(args.output_dir)
    out.mkdir(parents=True,exist_ok=True)

    reg=load_registry(args.events)
    if len(reg)!=93:
        raise RuntimeError(f"expected frozen 93-symbol universe, got {len(reg)}")

    registry=out/"alias_registry.csv"
    sql_path=out/"r9_ngram_historical.sql"
    reg.to_csv(registry,index=False)
    sql_path.write_text(build_sql(reg),encoding="utf-8")

    print("REGISTRY=",registry)
    print("SQL=",sql_path)
    print("SUPPORTED=",int(reg["status"].eq("SUPPORTED").sum()))
    print("NEEDS_OVERRIDE=",int(reg["status"].ne("SUPPORTED").sum()))

    bad=reg.loc[
        reg["status"]!="SUPPORTED",
        ["symbol","company_name","alias","ngram_order","status"],
    ]
    if len(bad):
        print("===== NEEDS OVERRIDE =====")
        print(bad.to_string(index=False))

    if args.summarize_csv:
        manifest=summarize_result(
            args.summarize_csv,
            registry,
            out/"manifest.json",
        )
        print(json.dumps(manifest,indent=2))

if __name__=="__main__":
    main()
