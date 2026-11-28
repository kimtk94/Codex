"""Rehearse frozen cash replays from existing GitHub artifacts, without Drive secrets."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from outcome_profile import load_original
from regime_cash_replay import CORE, replay as regime_replay
from risk_cash_replay import replay as risk_replay

EXPECTED = {
    "data": (52, "4808dedf3b18883b0c1e3103b6760f5fcc51a1d5bd9def05b754558a06102436"),
    "results": (135, "2db1d9628ae6e4b9b7cdf76e60092efab4bb97a3ebdab1bdc1967151ce059d6d"),
}
RUN_ID = 45382109010
ARTIFACTS = {"data":14914022566,"results":14915505210}

def verified_directory(root, kind):
    root=Path(root)
    if not root.is_dir():
        raise ValueError("ARTIFACT_DIRECTORY_MISSING")
    payload={}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("ARTIFACT_SYMLINK")
        if path.is_file():
            payload[path.relative_to(root).as_posix()]=path.read_bytes()
    hashes={k:hashlib.sha256(v).hexdigest() for k,v in payload.items()}
    digest=hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    if (len(payload),digest)!=EXPECTED[kind]:
        raise ValueError("ARTIFACT_DRIVE_MEMBER_DIGEST_MISMATCH:"+kind)
    return payload

def main():
    p=argparse.ArgumentParser()
    for name in ("data","results","original-source","out"):
        p.add_argument("--"+name,required=True)
    a=p.parse_args()
    verified_directory(a.data,"data")
    payload=verified_directory(a.results,"results")
    train=load_original(a.original_source)
    import portfolio
    market=Path(a.data)/"market"
    prices={s:train.load_bars(train.market_file(market,s))[["open","close"]]
            for s in CORE+["^VIX","GLD"]}
    out=Path(a.out)
    out.mkdir(parents=True,exist_ok=True)
    meta={"source_run_id":RUN_ID,"artifact_ids":ARTIFACTS,
          "drive_payload_member_digests":EXPECTED,"all_187_members_verified":True,
          "research_only":True,"approved_live":False,"production_writes":False}
    for name,fn in (("regime",lambda:regime_replay(prices,payload,portfolio)),
                    ("risk",lambda:risk_replay(payload,prices,portfolio))):
        report=fn()
        report["artifact_member_equivalence"]=meta
        (out/(name+"_artifact_replay.json")).write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
        print("FROZEN_ARTIFACT_REPLAY_OK",name,len(report["scenarios"]),flush=True)

if __name__=="__main__":
    main()
