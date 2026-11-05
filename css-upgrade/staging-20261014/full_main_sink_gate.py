"""Static source-to-sink gate for entire CSS main, fail-closed and no imports."""
import ast,hashlib,json,sys
from collections import Counter
from pathlib import Path

EXPECTED="a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
RISK={
 "sheet":("overwrite_dataframe_if_changed","overwrite_typed_worksheet","worksheet.update","worksheet.batch_update","worksheet.clear","worksheet.append_rows","gspread.authorize","gc.open_by_key"),
 "db":("sqlite3.connect","conn.execute","conn.executemany","conn.commit","conn.backup"),
 "network":("requests.post","requests.put","requests.patch","requests.delete","httpx.post","smtplib.SMTP","imaplib.IMAP4_SSL"),
 "process":("subprocess.run","subprocess.Popen","os.system","os.replace","os.rename","shutil.copy","shutil.move"),
 "external":("publish_mail_state_to_drive","send_email","send_mail","salesforce_update","drive_service.files")
}
def main(path):
 raw=Path(path).read_bytes()
 assert hashlib.sha256(raw).hexdigest()==EXPECTED,"LIVE_SOURCE_SHA_MISMATCH"
 tree=ast.parse(raw)
 funcs={n.name:n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
 assert "main" in funcs
 main=funcs["main"]
 direct=Counter(ast.unparse(n.func) for n in ast.walk(main) if isinstance(n,ast.Call))
 names=set(direct)
 reachable={"main"}
 work=["main"]
 unresolved=set()
 while work:
  current=work.pop()
  node=funcs[current]
  for call in (n for n in ast.walk(node) if isinstance(n,ast.Call)):
   name=ast.unparse(call.func)
   if name in funcs and name not in reachable:
    reachable.add(name);work.append(name)
   elif name not in funcs and name not in ("print","len","str","int","float","bool","set","list","dict","tuple","sum","max","min","range","enumerate","sorted","any","all","zip","getattr","hasattr","isinstance"):
    unresolved.add(name)
 allcalls=Counter()
 for n in reachable:
  allcalls.update(ast.unparse(call.func) for call in ast.walk(funcs[n]) if isinstance(call,ast.Call))
 findings={kind:{x:allcalls[x] for x in patterns if allcalls[x]>0} for kind,patterns in RISK.items()}
 assert direct["overwrite_dataframe_if_changed"]>=20,"EXPECTED_SHEET_SINK_COUNT_DRIFT"
 assert any(findings.values()),"SINK_DETECTION_EMPTY"
 report={"source_sha_verified":True,"main_ast_calls":sum(direct.values()),
 "main_direct_write_sites":direct["overwrite_dataframe_if_changed"],
 "reachable_local_function_count":len(reachable),
 "transitive_call_sites":sum(allcalls.values()),
 "sink_call_counts":findings,
 "unresolved_external_call_names":len(unresolved),
 "complete_os_egress_isolation":False,
 "full_main_execution_allowed":False,
 "production_write_permitted":False}
 print("CSS_FULL_MAIN_SINK_GATE",json.dumps(report,sort_keys=True),flush=True)
 print("FULL_MAIN_FAIL_CLOSED_PASS",flush=True)
if __name__=="__main__":main(sys.argv[1])
