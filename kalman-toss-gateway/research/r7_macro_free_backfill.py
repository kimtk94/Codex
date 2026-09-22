#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, re, os
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

UTC=timezone.utc
NY=ZoneInfo("America/New_York")
BLS_API="https://api.bls.gov/publicAPI/v1/timeseries/data/"
BLS_SCHEDULE="https://www.bls.gov/schedule/{year}/"
FED_CAL="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

SERIES={
 "CPI_HEADLINE_INDEX":"CUSR0000SA0",
 "CORE_CPI_INDEX":"CUSR0000SA0L1E",
 "NFP_LEVEL":"CES0000000001",
 "UNEMPLOYMENT_RATE":"LNS14000000",
 "AHE_LEVEL":"CES0500000003",
 "PPI_FINAL_DEMAND_INDEX":"WPSFD4",
 "JOLTS_OPENINGS":"JTS000000000000000JOL",
}
RELEASE_PATTERNS={
 "CPI": re.compile(r"Consumer Price Index",re.I),
 "EMPLOYMENT": re.compile(r"Employment Situation",re.I),
 "PPI": re.compile(r"Producer Price Index",re.I),
 "JOLTS": re.compile(r"Job Openings and Labor Turnover Survey",re.I),
}
MONTHS={m:i for i,m in enumerate(
 ["January","February","March","April","May","June","July","August","September","October","November","December"],1
)}

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.in_td=False; self.in_tr=False; self.cell=[]; self.row=[]; self.rows=[]
    def handle_starttag(self,tag,attrs):
        if tag=="tr": self.in_tr=True; self.row=[]
        elif tag in ("td","th") and self.in_tr: self.in_td=True; self.cell=[]
    def handle_data(self,data):
        if self.in_td: self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ("td","th") and self.in_td:
            self.row.append(" ".join("".join(self.cell).split())); self.in_td=False
        elif tag=="tr" and self.in_tr:
            if self.row: self.rows.append(self.row)
            self.in_tr=False

def fetch_json(client,url,payload):
    r=client.post(url,json=payload); r.raise_for_status(); return r.json()

def parse_bls_value(value):
    text=str(value or "").strip()
    if text in {"", "-", ".", "NA", "N/A", "null", "None"}:
        return None
    try:
        return float(text.replace(",", ""))
    except (TypeError, ValueError):
        return None

def bls_data(start_year,end_year):
    payload={"seriesid":list(SERIES.values()),"startyear":str(start_year),"endyear":str(end_year)}
    with httpx.Client(timeout=30,headers={"User-Agent":"Kalman-R7-research"}) as client:
        x=fetch_json(client,BLS_API,payload)
    if x.get("status")!="REQUEST_SUCCEEDED":
        raise RuntimeError(x)
    by_id={}
    skipped_missing=0
    skipped_invalid=0
    for s in (x.get("Results") or {}).get("series") or []:
        vals={}
        for r in s.get("data") or []:
            p=str(r.get("period") or "")
            if not (len(p)==3 and p.startswith("M") and p[1:].isdigit()):
                continue
            raw=r.get("value")
            value=parse_bls_value(raw)
            if value is None:
                if str(raw or "").strip() in {"", "-", ".", "NA", "N/A", "null", "None"}:
                    skipped_missing += 1
                else:
                    skipped_invalid += 1
                continue
            vals[(int(r["year"]),int(p[1:]))]=value
        by_id[s["seriesID"]]=vals
    return by_id, {
        "skipped_missing_values": skipped_missing,
        "skipped_invalid_values": skipped_invalid,
    }

def pct(a,b):
    return None if a is None or b in (None,0) else (a/b-1.0)*100.0

def derived_actuals(by_id):
    inv={v:k for k,v in SERIES.items()}
    raw={inv[k]:v for k,v in by_id.items() if k in inv}
    out={}
    keys=set()
    for v in raw.values(): keys |= set(v)
    for ym in sorted(keys):
        y,m=ym; py,pm=(y-1,12) if m==1 else (y,m-1)
        prev=(py,pm)
        row={}
        cpi=raw.get("CPI_HEADLINE_INDEX",{})
        core=raw.get("CORE_CPI_INDEX",{})
        nfp=raw.get("NFP_LEVEL",{})
        ahe=raw.get("AHE_LEVEL",{})
        ppi=raw.get("PPI_FINAL_DEMAND_INDEX",{})
        jolts=raw.get("JOLTS_OPENINGS",{})
        unemp=raw.get("UNEMPLOYMENT_RATE",{})
        if ym in cpi: row["CPI_HEADLINE_MOM"]=pct(cpi[ym],cpi.get(prev))
        if ym in core: row["CORE_CPI_MOM"]=pct(core[ym],core.get(prev))
        if ym in nfp: row["NFP"]=None if prev not in nfp else nfp[ym]-nfp[prev]
        if ym in unemp: row["UNEMPLOYMENT_RATE"]=unemp[ym]
        if ym in ahe: row["AVERAGE_HOURLY_EARNINGS_MOM"]=pct(ahe[ym],ahe.get(prev))
        if ym in ppi: row["PPI_MOM"]=pct(ppi[ym],ppi.get(prev))
        if ym in jolts: row["JOLTS_OPENINGS"]=jolts[ym]
        out[ym]=row
    return out

def parse_reference_month(text):
    m=re.search(r"for\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",text,re.I)
    if not m: return None
    return int(m.group(2)), MONTHS[m.group(1).title()]

def parse_release_dt(date_text,time_text):
    # BLS year pages render e.g. Friday, April 3, 2026 + 08:30 AM
    d=re.sub(r"^[A-Za-z]+,\s*","",date_text.strip())
    naive=datetime.strptime(d+" "+time_text.strip(),"%B %d, %Y %I:%M %p")
    return naive.replace(tzinfo=NY).astimezone(UTC)

def bls_schedule(start_year,end_year):
    events=[]
    with httpx.Client(timeout=30,headers={"User-Agent":"Kalman-R7-research"}) as c:
        for year in range(start_year,end_year+1):
            r=c.get(BLS_SCHEDULE.format(year=year)); r.raise_for_status()
            p=TableParser(); p.feed(r.text)
            for row in p.rows:
                if len(row)<3: continue
                date_text,time_text,name=row[0],row[1],row[2]
                fam=next((k for k,pat in RELEASE_PATTERNS.items() if pat.search(name)),None)
                if not fam: continue
                try: release_at=parse_release_dt(date_text,time_text)
                except Exception: continue
                events.append({
                    "family":fam,"event_name":name,"release_at":release_at.isoformat(),
                    "reference_period":parse_reference_month(name),
                    "source":"BLS_RELEASE_CALENDAR","time_quality":"OFFICIAL_SCHEDULE_TS"
                })
    return events

def fomc_events(start_year,end_year):
    with httpx.Client(timeout=30,headers={"User-Agent":"Kalman-R7-research"}) as c:
        r=c.get(FED_CAL); r.raise_for_status(); html=r.text
    dates=set()
    for ds in re.findall(r"monetary(20\d{6})a\.htm",html):
        y=int(ds[:4])
        if start_year<=y<=end_year: dates.add(ds)
    out=[]
    for ds in sorted(dates):
        d=datetime.strptime(ds,"%Y%m%d")
        release=d.replace(hour=14,minute=0,tzinfo=NY).astimezone(UTC)
        out.append({
            "family":"FOMC","event_name":"FOMC statement","release_at":release.isoformat(),
            "reference_period":None,"source":"FED_FOMC_CALENDAR",
            "time_quality":"OFFICIAL_STATEMENT_TS_2PM_ET"
        })
    return out

def attach_actuals(events,actuals):
    for e in events:
        rp=e.get("reference_period")
        vals=actuals.get(tuple(rp),{}) if rp else {}
        fam=e["family"]
        if fam=="CPI": keys=["CPI_HEADLINE_MOM","CORE_CPI_MOM"]
        elif fam=="EMPLOYMENT": keys=["NFP","UNEMPLOYMENT_RATE","AVERAGE_HOURLY_EARNINGS_MOM"]
        elif fam=="PPI": keys=["PPI_MOM"]
        elif fam=="JOLTS": keys=["JOLTS_OPENINGS"]
        else: keys=[]
        e["actuals"]={k:vals.get(k) for k in keys}
        e["actual_data_quality"]="REVISED_SERIES_NOT_PIT" if keys else "EVENT_ONLY"
        e["consensus"]=None
        e["r7_model_eligible"]=False
    return events

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--start-year",type=int,default=2020)
    ap.add_argument("--end-year",type=int,default=2026)
    ap.add_argument("--output-dir",default="/opt/kalman/state/r7_macro_free")
    args=ap.parse_args()
    data, bls_parse = bls_data(args.start_year,args.end_year)
    actuals=derived_actuals(data)
    events=bls_schedule(args.start_year,args.end_year)+fomc_events(args.start_year,args.end_year)
    events=attach_actuals(events,actuals)
    events.sort(key=lambda x:x["release_at"])
    fams=sorted(set(e["family"] for e in events))
    n_actual=sum(bool(e["actuals"]) for e in events)
    report={
      "schema":"kalman-r7-macro-free-v2",
      "generated_at_utc":datetime.now(UTC).isoformat(),
      "research_only":True,"production_changed":False,
      "provider_cost":"FREE_NO_KEY",
      "sources":["BLS_PUBLIC_API_V1","BLS_RELEASE_CALENDAR","FED_FOMC_CALENDAR"],
      "start_year":args.start_year,"end_year":args.end_year,
      "events":len(events),"families":fams,"family_count":len(fams),
      "events_with_revised_actuals":n_actual,
      "bls_parse":bls_parse,
      "consensus_available":False,
      "pit_actual_ready":False,
      "reaction_ready":False,
      "model_fitting_allowed":False,
      "blockers":[
        "NO_CONSENSUS_FREE_SOURCE",
        "BLS_API_HISTORY_IS_REVISED_NOT_FIRST_RELEASE_VINTAGE",
        "MARKET_REACTION_LAYER_NOT_BUILT"
      ]
    }
    out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True)
    (out/"events.json").write_text(json.dumps(events,indent=2,default=str)+"\n")
    (out/"manifest.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    print("EVENTS_FILE=",out/"events.json")
    print("MANIFEST=",out/"manifest.json")

if __name__=="__main__": main()
