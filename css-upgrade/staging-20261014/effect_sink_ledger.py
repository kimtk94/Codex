#!/usr/bin/env python3
"""AST-only classified high-impact effects ledger, no production imports or execution."""
import ast,hashlib,json,re,sys,collections
from pathlib import Path
SHA="a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
EXACT={
 "sheets_write":{"overwrite_dataframe_if_changed","overwrite_typed_worksheet","spreadsheet.batch_update","worksheet.update","worksheet.batch_update","worksheet.clear","worksheet.append_rows","worksheet.format","worksheet.freeze"},
 "database_write":{"conn.commit","conn.rollback","conn.executemany","conn.execute","conn.backup"},
 "filesystem_mutation":{"os.replace","os.rename","shutil.move","shutil.copy","shutil.copy2","Path.write_text","Path.write_bytes"},
 "potential_outbound":{"gspread.authorize","gc.open_by_key","requests.post","requests.put","requests.patch","requests.delete"}
}
def run(path):
 b=Path(path).read_bytes()
 assert hashlib.sha256(b).hexdigest()==SHA,"LIVE_SOURCE_DRIFT"
 t=ast.parse(b)
 funcs={f.name:f for f in t.body if isinstance(f,(ast.FunctionDef,ast.AsyncFunctionDef))}
 visited=set();stack=["main"];records=[];calls=0
 while stack:
  fn=stack.pop()
  if fn in visited:continue
  visited.add(fn)
  root=funcs[fn]
  for call in ast.walk(root):
   if not isinstance(call,ast.Call):continue
   calls+=1
   name=ast.unparse(call.func)
   if name in funcs and name not in visited:stack.append(name)
   category=next((k for k,v in EXACT.items() if name in v),None)
   if category:
    records.append({"category":category,"owner":fn,"line":call.lineno,
                    "call":name})
 records.sort(key=lambda x:(x["category"],x["line"],x["owner"]))
 summary={}
 for category in EXACT:
  sub=[r for r in records if r["category"]==category]
  summary[category]={"sites":len(sub),"owners":len(set(r["owner"] for r in sub)),
      "calls":dict(collections.Counter(r["call"] for r in sub)),
      "sample_sites":sub[:18]}
 assert len(visited)>=300 and summary["sheets_write"]["sites"]>=20
 # A sink inventory is NOT an enforcement sandbox.
 report={"source_verified":True,"reachable_functions":len(visited),"all_ast_calls":calls,
         "selected_sites":len(records),"classes":summary,
         "db_execute_can_be_read_or_write":True,
         "whole_main_allowed":False,"network_isolation_enforced":False}
 print("CSS_EFFECT_SINK_LEDGER",json.dumps(report,sort_keys=True),flush=True)
 print("ALL_PRODUCTION_WRITES_DISALLOWED",True,flush=True)
if __name__=="__main__":run(sys.argv[1])
