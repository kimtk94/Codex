#!/usr/bin/env python3
"""Fail-closed AST triage of CSS main transitive external call expressions.
Read-only; no import or execution of production application modules.
"""
import ast,collections,hashlib,json,re,sys
from pathlib import Path
EXPECTED="a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
BUILTINS=set("print len str int float bool set list dict tuple sum max min range enumerate sorted any all zip getattr hasattr isinstance next iter repr abs round format type open map filter reversed slice object Exception ValueError RuntimeError KeyError AttributeError".split())
def classify(name):
    x=name.lower()
    if any(k in x for k in ("exec(", "eval(", "__import__", "import_module", "getattr(", "globals(", "locals(")):
        return "dynamic"
    if re.search(r"(^|\.)(send|smtp|imap|mail|post|put|patch|delete|request|urlopen|session|http|fetch|download|upload|oauth|token|authorize|auth|api|refresh|salesforce|drive|gmail|gspread|sheets|worksheet|spreadsheet|service_account|open_by_key|batch_update|append_rows)(_|\.|$)",x):
        return "external_or_network"
    if re.search(r"(^|\.)(connect|execute|executemany|commit|rollback|backup|cursor|to_sql|read_sql|sqlite|transaction|savepoint|vacuum)(_|\.|$)",x):
        return "database"
    if re.search(r"(^|\.)(write|save|dump|export|replace|rename|unlink|remove|rmtree|mkdir|makedirs|copy|move|chmod|touch|open|to_csv|to_excel|to_json|read_text|write_text|read_bytes|write_bytes|subprocess|popen|system)(_|\.|$)",x):
        return "filesystem_or_process"
    if x.startswith(("pd.","np.","re.","datetime.","time.","math.","json.","pathlib.","logging.","logger.")):
        return "common_library"
    return "unknown"
def run(path):
    b=Path(path).read_bytes()
    assert hashlib.sha256(b).hexdigest()==EXPECTED,"LIVE_SHA_DRIFT"
    tree=ast.parse(b)
    funcs={n.name:n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    reached={"main"}
    frontier=["main"]
    calls=collections.Counter()
    while frontier:
        name=frontier.pop()
        for n in ast.walk(funcs[name]):
            if not isinstance(n,ast.Call):continue
            target=ast.unparse(n.func)
            calls[target]+=1
            if target in funcs and target not in reached:
                reached.add(target);frontier.append(target)
    unidentified={k:v for k,v in calls.items() if k not in funcs and k not in BUILTINS}
    groups=collections.defaultdict(list)
    for name,count in unidentified.items():
        groups[classify(name)].append((name,count))
    detail={}
    for group,entries in sorted(groups.items()):
        entries.sort(key=lambda x:(-x[1],x[0]))
        detail[group]={"unique":len(entries),"occurrences":sum(v for _,v in entries),
                       "top_calls":[{"name":n,"sites":v} for n,v in entries[:30]]}
    explicit={"external_or_network","database","filesystem_or_process","dynamic"}
    assert all(k in detail for k in ("external_or_network","database","filesystem_or_process")),"RISK_CATEGORIES_NOT_FOUND"
    report={"source_sha_verified":True,"reachable_functions":len(reached),
            "total_transitive_calls":sum(calls.values()),"unresolved_distinct":len(unidentified),
            "risk_distinct":sum(detail[k]["unique"] for k in explicit if k in detail),
            "risk_occurrences":sum(detail[k]["occurrences"] for k in explicit if k in detail),
            "groups":detail,"unknown_not_assumed_safe":True,
            "full_main_execution_allowed":False,"network_block_enforced":False}
    print("CSS_UNRESOLVED_CALL_TRIAGE",json.dumps(report,sort_keys=True),flush=True)
    print("FULL_MAIN_REMAINS_BLOCKED",True,flush=True)
if __name__=="__main__":run(sys.argv[1])
