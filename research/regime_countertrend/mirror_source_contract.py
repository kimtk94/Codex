"""Static source audit of LIVE mirror calculation (read-only, no imports or writes).

This is evidence of a source-code pattern, never proof of deployed SHA.
"""
import ast
import argparse
import hashlib
import json
from pathlib import Path

def classify(text):
    tree=ast.parse(text)
    funcs=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name=="_round_trip_quality"]
    if len(funcs)!=1:
        return {"status":"HOLD_ROUND_TRIP_FUNCTION_NOT_UNIQUE","functions":len(funcs)}
    f=funcs[0]
    parameters=[a.arg for a in f.args.posonlyargs+f.args.args+f.args.kwonlyargs]
    argcalls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=="_round_trip_quality"]
    has_position=("position" in parameters)
    has_verified=("broker_fills_verified" in parameters)
    passes_position=bool(argcalls) and all("position" in [k.arg for k in call.keywords] or len(call.args)>=3 for call in argcalls)
    passes_verified=bool(argcalls) and all("broker_fills_verified" in [k.arg for k in call.keywords] for call in argcalls)
    if not all((has_position,has_verified,passes_position,passes_verified)):
        status="HOLD_NO_FULL_POSITION_AND_BROKER_PROVENANCE_CONTRACT"
    else:
        status="REVIEW_CONTRACT_PRESENT_NOT_DEPLOYMENT_PROVEN"
    return {"status":status,"round_trip_parameters":parameters,
        "callsites":len(argcalls),"all_calls_pass_position":passes_position,
        "all_calls_pass_broker_verification":passes_verified,
        "source_sha256":hashlib.sha256(text.encode()).hexdigest(),
        "broker_verified":False,"production_compatible":False,
        "note":"Static analysis only. Even REVIEW needs independent runtime deployment and broker evidence."}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="kalman-toss-gateway/engine/trade_mirror.py")
    p.add_argument("--out",default="results/regime_countertrend/mirror_source")
    a=p.parse_args()
    outcome=classify(Path(a.source).read_text())
    dest=Path(a.out);dest.mkdir(parents=True,exist_ok=True)
    (dest/"source_gate.json").write_text(json.dumps(outcome,indent=2))
    print("SOURCE_GATE",json.dumps(outcome))
