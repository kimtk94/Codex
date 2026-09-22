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
 "EMPLOYMENT": re.compile(r"^Employment Situation for ",re.I),
 "PPI": re.compile(r"Producer Price Index",re.I),
 "JOLTS": re.compile(r"Job Openings and Labor Turnover Survey",re.I),
}
ARCHIVE_SLUGS={
 "CPI":"cpi",
 "EMPLOYMENT":"empsit",
 "PPI":"ppi",
 "JOLTS":"jolts",
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

class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]
    def handle_data(self,data):
        if data and data.strip():
            self.parts.append(data.strip())

def html_to_text(html):
    p=TextParser(); p.feed(html)
    return re.sub(r"\s+"," "," ".join(p.parts)).strip()

def signed_value(verb,value):
    v=float(value)
    verb=(verb or "").lower()
    if any(x in verb for x in ("decreased","declined","fell","dropped","down")):
        return -v
    return v

def parse_archive_actuals(family,text):
    t=re.sub(r"\s+"," ",text)
    out={}
    if family=="CPI":
        m=re.search(r"(?:CPI-U\)|Consumer Price Index for All Urban Consumers).*?\b(increased|rose|advanced|decreased|declined|fell|dropped)\s+([0-9.]+)\s+percent",t,re.I)
        if m: out["CPI_HEADLINE_MOM"]=signed_value(m.group(1),m.group(2))
        m=re.search(r"index for all items less food and energy\s+(rose|increased|advanced|fell|declined|decreased|dropped)\s+([0-9.]+)\s+percent",t,re.I)
        if m: out["CORE_CPI_MOM"]=signed_value(m.group(1),m.group(2))
    elif family=="EMPLOYMENT":
        head=t[:7000]
        m=re.search(r"Total nonfarm payroll employment\s+(?:increased|rose)\s+by\s+([0-9,]+)",head,re.I)
        if m: out["NFP"]=float(m.group(1).replace(",",""))
        if "NFP" not in out:
            m=re.search(r"Total nonfarm payroll employment\s+(?:declined|decreased|fell)\s+by\s+([0-9,]+)",head,re.I)
            if m: out["NFP"]=-float(m.group(1).replace(",",""))
        if "NFP" not in out:
            m=re.search(r"(?:total )?nonfarm payroll employment\s*\(([+-]?[0-9,]+)\)",head,re.I)
            if m: out["NFP"]=float(m.group(1).replace(",",""))
        m=re.search(r"unemployment rate.*?(?:to|at|\()\s*([0-9.]+)\s+percent",head,re.I)
        if m: out["UNEMPLOYMENT_RATE"]=float(m.group(1))
        m=re.search(r"average hourly earnings for all employees on private nonfarm payrolls.{0,220}?(?:or\s+)?([0-9.]+)\s+percent",t,re.I)
        if m:
            snippet=m.group(0).lower()
            val=float(m.group(1))
            if any(x in snippet for x in ("declined","decreased","fell","down")): val=-val
            out["AVERAGE_HOURLY_EARNINGS_MOM"]=val
    elif family=="PPI":
        m=re.search(r"Producer Price Index for final demand\s+(moved up|rose|increased|advanced|edged up|fell|declined|decreased|edged down)\s+([0-9.]+)\s+percent",t,re.I)
        if m: out["PPI_MOM"]=signed_value(m.group(1),m.group(2))
        elif re.search(r"Producer Price Index for final demand\s+was unchanged",t,re.I):
            out["PPI_MOM"]=0.0
    elif family=="JOLTS":
        head=t[:5000]
        patterns=[
            r"(?:The\s+)?number of job openings.{0,140}?(?:at|to|of)\s+([0-9.]+)\s+million",
            r"(?:The\s+)?number of job openings\s+(?:reached|increased to|declined to|decreased to|was little changed at).*?([0-9.]+)\s+million",
            r"Job openings\s+(?:increased|decreased|declined|rose|fell|were little changed|was little changed).*?\s(?:to|at)\s+([0-9.]+)\s+million",
            r"job openings level.{0,100}?\s(?:to|at|of)\s+([0-9.]+)\s+million",
        ]
        for pat in patterns:
            m=re.search(pat,head,re.I)
            if m:
                out["JOLTS_OPENINGS"]=float(m.group(1))*1000.0
                break
    return out

def archive_url(event):
    slug=ARCHIVE_SLUGS.get(event.get("family"))
    if not slug: return None
    dt=datetime.fromisoformat(str(event["release_at"]).replace("Z","+00:00"))
    local=dt.astimezone(NY)
    return f"https://www.bls.gov/news.release/archives/{slug}_{local:%m%d%Y}.htm"

def attach_archive_first_release(events):
    stats={"attempted":0,"fetched":0,"parsed":0,"reissued_or_corrected":0}
    with httpx.Client(timeout=30,headers={"User-Agent":"Kalman-R7-research"}) as client:
        for e in events:
            url=archive_url(e)
            if not url:
                continue
            stats["attempted"]+=1
            e["archive_url"]=url
            try:
                r=client.get(url)
                if r.status_code!=200:
                    e["archive_fetch_status"]=f"HTTP_{r.status_code}"
                    e["first_release_actuals"]={}
                    e["first_release_quality"]="ARCHIVE_FETCH_FAILED"
                    e["pit_actual_eligible"]=False
                    continue
                stats["fetched"]+=1
                text=html_to_text(r.text)
                actuals=parse_archive_actuals(e["family"],text)
                reissued=bool(re.search(r"reissued this news release|corrected this news release",text,re.I))
                if reissued: stats["reissued_or_corrected"]+=1
                if actuals: stats["parsed"]+=1
                e["archive_fetch_status"]="OK"
                e["first_release_actuals"]=actuals
                if reissued:
                    e["first_release_quality"]="OFFICIAL_BLS_ARCHIVE_REISSUED_OR_CORRECTED"
                    e["pit_actual_eligible"]=False
                elif actuals:
                    e["first_release_quality"]="OFFICIAL_BLS_ARCHIVE_PIT_CANDIDATE"
                    e["pit_actual_eligible"]=True
                else:
                    e["first_release_quality"]="ARCHIVE_PARSE_FAILED"
                    e["pit_actual_eligible"]=False
            except Exception as ex:
                e["archive_fetch_status"]=f"ERROR:{type(ex).__name__}"
                e["first_release_actuals"]={}
                e["first_release_quality"]="ARCHIVE_FETCH_FAILED"
                e["pit_actual_eligible"]=False
    return stats

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
                if release_at > datetime.now(UTC):
                    continue
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
        if release > datetime.now(UTC):
            continue
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
    archive_stats=attach_archive_first_release(events)
    events.sort(key=lambda x:x["release_at"])
    fams=sorted(set(e["family"] for e in events))
    n_actual=sum(bool(e["actuals"]) for e in events)
    eligible=sum(bool(e.get("pit_actual_eligible")) for e in events)
    attempted=archive_stats.get("attempted") or 0
    pit_archive_coverage_ratio=(eligible/attempted) if attempted else 0.0
    per_family={}
    for family in sorted(fams):
        xs=[e for e in events if e.get("family")==family]
        attempted_rows=[e for e in xs if e.get("archive_url")]
        eligible_rows=[e for e in attempted_rows if e.get("pit_actual_eligible")]
        per_family[family]={
            "events":len(xs),
            "archive_attempted":len(attempted_rows),
            "pit_eligible":len(eligible_rows),
            "coverage_ratio":(
                len(eligible_rows)/len(attempted_rows)
                if attempted_rows else None
            ),
        }
    report={
      "schema":"kalman-r7-macro-free-v5",
      "generated_at_utc":datetime.now(UTC).isoformat(),
      "research_only":True,"production_changed":False,
      "provider_cost":"FREE_NO_KEY",
      "sources":["BLS_PUBLIC_API_V1","BLS_RELEASE_CALENDAR","BLS_ARCHIVED_NEWS_RELEASE_HTML","FED_FOMC_CALENDAR"],
      "start_year":args.start_year,"end_year":args.end_year,
      "events":len(events),"families":fams,"family_count":len(fams),
      "events_with_revised_actuals":n_actual,
      "bls_parse":bls_parse,
      "archive_first_release":archive_stats,
      "pit_archive_eligible_events":eligible,
      "pit_archive_coverage_ratio":pit_archive_coverage_ratio,
      "per_family_archive_coverage":per_family,
      "actual_gate_contract":{
        "scope":"OVERALL_BLS_ARCHIVE_EVENTS",
        "threshold":0.95,
        "per_family_coverage_is_diagnostic_only":True,
        "reissued_or_corrected_rows_are_event_level_missing":True
      },
      "consensus_available":False,
      "pit_actual_ready":pit_archive_coverage_ratio>=0.95,
      "reaction_ready":False,
      "model_fitting_allowed":False,
      "blockers":(
        ["NO_CONSENSUS_FREE_SOURCE"]
        + ([] if pit_archive_coverage_ratio>=0.95 else ["ARCHIVE_FIRST_RELEASE_COVERAGE_BELOW_95PCT"])
        + ["MARKET_REACTION_LAYER_NOT_BUILT"]
      )
    }
    out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True)
    (out/"events.json").write_text(json.dumps(events,indent=2,default=str)+"\n")
    (out/"manifest.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    print("EVENTS_FILE=",out/"events.json")
    print("MANIFEST=",out/"manifest.json")

if __name__=="__main__": main()
