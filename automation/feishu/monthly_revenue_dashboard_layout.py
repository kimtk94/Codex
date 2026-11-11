#!/usr/bin/env python3
"""Put a real source-backed Monthly Revenue list below its chart.

Only dashboard widget positions change. The native ranking block reads the
'Monthly Tax Invoice' records and opens underlying detail. No static fake
checkbox table, revenue recalculation, or source record writes.
"""
import json
import os
import sys
from native_dashboard_cli import BASE, cli, collect, find_named
from shortcut_chart_dashboards import CHARTS, MONTHLY_LIST_NAME

MONTHLY=next(x for x in CHARTS if x[0]=="MONTHLY_TREND")
DASHBOARD_TITLE=MONTHLY[2]
CHART=MONTHLY[3]
NOTE=MONTHLY[4]
ORDER=(CHART,MONTHLY_LIST_NAME,NOTE)
POSITIONS={
    CHART:{"x":0,"y":0,"w":12,"h":10},
    MONTHLY_LIST_NAME:{"x":0,"y":11,"w":12,"h":13},
    NOTE:{"x":0,"y":25,"w":12,"h":8},
}

def inspect(payload):
    out={}
    for r in collect(payload):
        name=r.get("name")
        key=r.get("block_id") or r.get("id")
        # The CLI collection includes envelope objects; inspect only blocks.
        if not isinstance(key,str) or not key.startswith(("cht","blk")):
            continue
        if name not in ORDER:raise RuntimeError("MONTHLY_LAYOUT_UNEXPECTED_BLOCK")
        if name in out:raise RuntimeError("MONTHLY_LAYOUT_DUPLICATE_BLOCK")
        out[name]=(key,r.get("type"),r.get("position"))
    if set(out)!=set(ORDER):
        raise RuntimeError("MONTHLY_LAYOUT_REQUIRED_COMPONENT_MISSING")
    if any(out[n][1]!=t for n,t in ((CHART,"line"),(MONTHLY_LIST_NAME,"ranking"),(NOTE,"text"))):
        raise RuntimeError("MONTHLY_LAYOUT_BLOCK_TYPE_MISMATCH")
    return out

def validate(positions=POSITIONS):
    if set(positions)!=set(ORDER):
        raise RuntimeError("MONTHLY_LAYOUT_POSITION_MISSING")
    cells=set()
    for name in ORDER:
        v=positions[name]
        if not isinstance(v,dict) or set(v)!=set(("x","y","w","h")):
            raise RuntimeError("MONTHLY_LAYOUT_POSITION_INVALID")
        x,y,w,h=[v[k] for k in ("x","y","w","h")]
        if any(not isinstance(n,int) or isinstance(n,bool) for n in (x,y,w,h)):
            raise RuntimeError("MONTHLY_LAYOUT_INTEGER_REQUIRED")
        if x<0 or y<0 or w<1 or h<1 or x+w>12:
            raise RuntimeError("MONTHLY_LAYOUT_OUT_OF_BOUNDS")
        rect={(i,j) for i in range(x,x+w) for j in range(y,y+h)}
        if cells & rect:raise RuntimeError("MONTHLY_LAYOUT_OVERLAP")
        cells.update(rect)

def same(a,b):
    return isinstance(a,dict) and all(a.get(k)==b[k] for k in ("x","y","w","h"))

def move(did,bid,pos):
    cli("+dashboard-block-update","--base-token",BASE,"--dashboard-id",did,
        "--block-id",bid,"--position",json.dumps(pos,separators=(",",":")))

def apply(did,mode):
    validate()
    before=inspect(cli("+dashboard-block-list","--base-token",BASE,"--dashboard-id",did))
    pending=sum(not same(before[n][2],POSITIONS[n]) for n in ORDER)
    print("MONTHLY_REVENUE_LIST_LAYOUT_PLAN widgets=3 pending="+str(pending)+" mode="+mode,flush=True)
    if mode=="plan" or pending==0:return
    if mode!="apply":raise RuntimeError("MONTHLY_LAYOUT_INVALID_MODE")
    for i,n in enumerate(ORDER):
        move(did,before[n][0],{"x":0,"y":100+i*20,"w":12,"h":10})
    for n in ORDER:
        move(did,before[n][0],POSITIONS[n])
    after=inspect(cli("+dashboard-block-list","--base-token",BASE,"--dashboard-id",did))
    if any(after[n][0]!=before[n][0] or not same(after[n][2],POSITIONS[n]) for n in ORDER):
        raise RuntimeError("MONTHLY_LAYOUT_READBACK_MISMATCH")
    print("MONTHLY_REVENUE_NATIVE_LIST_BELOW_CHART_PASS months_source=Monthly_Tax_Invoice",flush=True)

def main():
    if os.getenv("FEISHU_BASE_APP_TOKEN")!=BASE:
        raise RuntimeError("MONTHLY_LAYOUT_BASE_NOT_ALLOWED")
    mode=os.getenv("FEISHU_PORTAL_MODE","plan")
    if mode not in ("plan","apply"):raise RuntimeError("MONTHLY_LAYOUT_BAD_MODE")
    did=find_named(cli("+dashboard-list","--base-token",BASE),DASHBOARD_TITLE)
    if not did or not did.startswith("blk"):raise RuntimeError("MONTHLY_LAYOUT_DASHBOARD_MISSING")
    apply(did,mode)

if __name__=="__main__":
    try:main()
    except Exception as e:
        print("MONTHLY_REVENUE_LAYOUT_FAILED="+(
            str(e) if isinstance(e,RuntimeError) else type(e).__name__),file=sys.stderr)
        sys.exit(1)
