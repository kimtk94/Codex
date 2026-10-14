"""V4.25 provenance gate for local ETHUSDT research archives.

Metadata and bounded samples only. No broker, API credentials, orders, or file
mutations outside --out. Do not promote unknown venue/market type to trusted.
"""
import argparse, csv, json, re, zipfile
from pathlib import Path
from datetime import datetime, timezone

def iso_ms(v):
 try:return datetime.fromtimestamp(int(v)/1000,timezone.utc).isoformat()
 except (ValueError,OverflowError,TypeError):return None

def zip_sample(path):
 with zipfile.ZipFile(path) as z:
  names=[n for n in z.namelist() if n.lower().endswith(".csv")]
  if not names:return {"status":"NO_CSV"}
  with z.open(names[0]) as f:
   import io
   r=csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig"))
   first=next(r,None)
   if first and first[0].lower() in ("open_time","timestamp"):first=next(r,None)
   second=next(r,None)
  if not first or len(first)<6:return {"status":"BAD_ROW"}
  return {"status":"SAMPLE_OK","zip_member":names[0],
    "first_ts_utc":iso_ms(first[0]),"second_ts_utc":iso_ms(second[0]) if second else None,
    "first_ohlcv":first[:6],"schema_length":len(first)}

def source_lines(roots,limit=60):
 matches=[]
 pattern=re.compile(r"(data\.binance\.vision|fapi\.binance\.com|api\.binance\.com|/futures/|/spot/|monthly/klines|fundingRate)",re.I)
 for root in roots:
  if not root.exists():continue
  candidates=(root,) if root.is_file() else root.rglob("*")
  for p in candidates:
   if not p.is_file() or p.suffix.lower() not in (".py",".sh",".md",".json",".txt"):continue
   try:
    if p.stat().st_size>2_000_000:continue
    with p.open(errors="replace") as f:
     for i,line in enumerate(f,1):
      if pattern.search(line):
       matches.append({"path":str(p),"line":i,"text":line.strip()[:250]})
       if len(matches)>=limit:return matches
   except (OSError,UnicodeError):pass
 return matches

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--zip-root",required=True)
 p.add_argument("--source-roots",nargs="+",required=True)
 p.add_argument("--out",required=True)
 a=p.parse_args()
 root=Path(a.zip_root).expanduser()
 zips=sorted(root.glob("ETHUSDT-1m-*.zip"))
 reports=[]
 for path in zips:
  x=zip_sample(path)
  reports.append({"file":path.name,"size_bytes":path.stat().st_size,**x,
                  "classification":"VENUE_AND_SPOT_FUTURES_UNVERIFIED"})
 references=source_lines([Path(s).expanduser() for s in a.source_roots])
 report={"status":"PROVENANCE_REVIEW_REQUIRED","zip_files_checked":len(reports),
  "zips":reports,"source_references":references,
  "policy":"Do not mix with Upbit KRW-ETH execution prices. Source code references require manual provenance verification."}
 dest=Path(a.out).expanduser();dest.parent.mkdir(parents=True,exist_ok=True)
 dest.write_text(json.dumps(report,indent=2,ensure_ascii=False))
 print(json.dumps({"status":report["status"],"zip_files_checked":len(reports),
  "sample_first":reports[0] if reports else None,"source_references_count":len(references),
  "source_reference_examples":references[:12],"out":str(dest)},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
