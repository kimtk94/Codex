"""V4.24 local ETH history source audit; metadata/sample only, zero network or orders.
ZIP is inspected without extraction. Parquet is inspected with pyarrow if present.
"""
import argparse,csv,json,zipfile
from pathlib import Path

def sample_csv(p):
 with p.open(newline="",encoding="utf-8-sig") as f:
  r=csv.reader(f); first=next(r,None); second=next(r,None)
 return {"first_row":first,"second_row":second}
def inspect(p):
 out={"path":str(p),"bytes":p.stat().st_size,"suffix":p.suffix.lower()}
 try:
  if p.suffix.lower()==".zip":
   with zipfile.ZipFile(p) as z:
    files=[x for x in z.infolist() if not x.is_dir()]
    out["members"]=[{"name":x.filename,"uncompressed_bytes":x.file_size} for x in files[:5]]
    if files and files[0].file_size:
     with z.open(files[0]) as f:
      out["first_lines"]=[f.readline().decode("utf-8-sig",errors="replace").strip()[:300] for _ in range(2)]
  elif p.suffix.lower()==".csv":
   out.update(sample_csv(p))
  elif p.suffix.lower()==".parquet":
   try:
    import pyarrow.parquet as pq
    q=pq.ParquetFile(p)
    out["row_groups"]=q.num_row_groups
    out["rows"]=q.metadata.num_rows
    out["columns"]=q.schema.names
    if q.num_row_groups:
     names=q.schema.names
     col=next((x for x in ("open_time","timestamp","t","time","datetime") if x in names),None)
     if col:
      table=q.read_row_group(0,columns=[col])
      arr=table[col]
      out["first_timestamp_sample"]=str(arr[0].as_py()) if len(arr) else None
   except ImportError:out["warning"]="pyarrow not installed; metadata only"
 except Exception as e:out["error"]=str(e)[:300]
 return out
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--roots",nargs="+",required=True)
 p.add_argument("--out",required=True)
 p.add_argument("--max-files",type=int,default=300)
 a=p.parse_args()
 entries=[]
 for item in a.roots:
  root=Path(item).expanduser()
  if not root.exists():continue
  if root.is_file():candidates=[root]
  else:candidates=(x for x in root.rglob("*") if x.is_file() and "ETHUSDT" in x.name.upper() and x.suffix.lower() in (".csv",".parquet",".zip"))
  for x in candidates:
   entries.append(inspect(x))
   if len(entries)>=a.max_files:break
  if len(entries)>=a.max_files:break
 report={"mode":"READ_ONLY_METADATA_AUDIT","files_inspected":len(entries),"entries":entries,
  "caveats":["ETHUSDT does not imply Upbit KRW-ETH or Upbit USDT-ETH.","Inspect provenance, spot/futures, timestamp unit and timezone before reuse.","Compressed files are not extracted."]}
 target=Path(a.out);target.parent.mkdir(parents=True,exist_ok=True)
 target.write_text(json.dumps(report,ensure_ascii=False,indent=2))
 for r in entries:
  print(json.dumps({"path":r["path"],"bytes":r["bytes"],"suffix":r["suffix"],
   "first_lines":r.get("first_lines"),"first_row":r.get("first_row"),
   "columns":r.get("columns"),"rows":r.get("rows"),"error":r.get("error")},ensure_ascii=False))
 print(json.dumps({"status":"COMPLETE","files":len(entries),"out":str(target)}))
if __name__=="__main__":main()
