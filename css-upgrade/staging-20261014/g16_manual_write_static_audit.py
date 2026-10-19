"""Read-only AST audit: find manual-control columns in CSS sheet write flows.

Private server source is never imported or executed. Emits only aggregate
counts / fixed allowlisted control names, no customer records or source text.
"""
import ast, hashlib, json, os
from pathlib import Path

SOURCE=Path("/home/taehoon/services/novogene-css/app/Novogene_Mail_CSS_DashBoard_server.py")
SHA="a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
WATCH=("exclude","exclude_reason","skip","Prepayment","skip_reason","restore")
SINKS=("overwrite_dataframe_if_changed","overwrite_typed_worksheet",
       "update_cells","batch_update","clear","append_rows","resize",
       "update","set_with_dataframe","worksheet.update","values_update")

def callname(n):
    if isinstance(n,ast.Name):return n.id
    if isinstance(n,ast.Attribute):return callname(n.value)+"."+n.attr
    return "unknown"

def main():
    if os.environ.get("G16_AST_AUDIT_READONLY")!="1":
        raise SystemExit("G16_FAIL_CLOSED")
    raw=SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SHA:
        raise SystemExit("G16_SOURCE_SHA_MISMATCH")
    tree=ast.parse(raw)
    functions=[x for x in tree.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))]
    rows=[]
    sink_sites=0
    writers=[]
    for fn in functions:
        names=set()
        calls=[]
        for n in ast.walk(fn):
            if isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value in WATCH:
                names.add(n.value)
            if isinstance(n,ast.Call):
                name=callname(n.func)
                if any(s==name or name.endswith("."+s) for s in SINKS):
                    calls.append(name)
        if names and calls:
            rows.append({"function_sha8":hashlib.sha256(fn.name.encode()).hexdigest()[:8],
                         "manual_columns":sorted(names),"write_call_sites":len(calls)})
        if calls:
            sink_sites+=len(calls)
            writers.append(fn.name)
    direct={}
    for name in WATCH:
        direct[name]=sum(name in entry["manual_columns"] for entry in rows)
    print("G16_MANUAL_WRITE_AUDIT_BEGIN")
    print(json.dumps({"source_sha_verified":True,
      "functions_parsed":len(functions),
      "sheet_write_candidate_sites":sink_sites,
      "functions_with_sheet_write_candidates":len(writers),
      "functions_with_manual_column_literals_and_sheet_writer":len(rows),
      "potential_cooccurrence_by_column":direct,
      "candidate_cooccurrences":rows[:60],
      "proof_of_actual_cell_overwrite":False,
      "source_executed":False},sort_keys=True))
    print("G16_MANUAL_WRITE_AUDIT_END")
    print("G16_STATIC_COOCCURRENCE_NOT_WRITE_RANGE_PROOF")
if __name__=="__main__":main()
