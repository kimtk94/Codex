#!/usr/bin/env python3
"""Stack Weekly Quote native dashboard widgets: graph, real rows, then footnotes.

Only layout coordinates of the three verified existing widgets may change.
No source tables or Quote inclusion flags are modified.
"""
import json
import os
import sys
from native_dashboard_cli import BASE, cli, collect, find_named
from shortcut_chart_dashboards import CHARTS
from quote_dashboard_preview import BLOCK_NAME

WEEKLY=next(row for row in CHARTS if row[0]=="WEEKLY_TREND")
DASHBOARD_TITLE=WEEKLY[2]
CHART_NAME=WEEKLY[3]
NOTE_NAME=WEEKLY[4]
ORDER=(CHART_NAME,BLOCK_NAME,NOTE_NAME)
POSITIONS={
    CHART_NAME:{"x":0,"y":0,"w":12,"h":10},
    BLOCK_NAME:{"x":0,"y":11,"w":12,"h":8},
    NOTE_NAME:{"x":0,"y":20,"w":12,"h":7},
}

def inspect(rows):
    found={}
    for row in collect(rows):
        name=row.get("name")
        ident=row.get("block_id") or row.get("id")
        if not isinstance(name,str) or not isinstance(ident,str) or not ident.startswith(("cht","blk")):
            continue
        if name in found:
            raise RuntimeError("WEEKLY_LAYOUT_DUPLICATE_BLOCK")
        found[name]=(ident,row.get("position"))
    if set(found)!=set(ORDER):
        raise RuntimeError("WEEKLY_LAYOUT_UNEXPECTED_WIDGET_SET")
    return found

def valid_pos(position):
    return isinstance(position,dict) and set(("x","y","w","h")).issubset(position) and all(
        isinstance(position.get(k),int) and not isinstance(position.get(k),bool)
        for k in ("x","y","w","h"))

def valid_layout(positions=POSITIONS):
    if set(positions)!=set(ORDER):
        raise RuntimeError("WEEKLY_LAYOUT_SCHEMA")
    cells=set()
    for pos in positions.values():
        if not valid_pos(pos):
            raise RuntimeError("WEEKLY_LAYOUT_INVALID_POSITION")
        x,y,w,h=[pos[k] for k in ("x","y","w","h")]
        if x<0 or y<0 or w<1 or h<1 or x+w>12:
            raise RuntimeError("WEEKLY_LAYOUT_OUT_OF_BOUNDS")
        rect={(col,row) for col in range(x,x+w) for row in range(y,y+h)}
        if cells & rect:
            raise RuntimeError("WEEKLY_LAYOUT_OVERLAP")
        cells.update(rect)
    return True

def equal_pos(current,goal):
    return valid_pos(current) and all(current[k]==goal[k] for k in ("x","y","w","h"))

def move(dashboard_id,block_id,position):
    cli("+dashboard-block-update","--base-token",BASE,
        "--dashboard-id",dashboard_id,"--block-id",block_id,
        "--position",json.dumps(position,separators=(",",":")))

def apply_layout(dashboard_id,mode="apply"):
    valid_layout()
    before=inspect(cli("+dashboard-block-list","--base-token",BASE,
                       "--dashboard-id",dashboard_id))
    pending=sum(not equal_pos(before[n][1],POSITIONS[n]) for n in ORDER)
    print("WEEKLY_LAYOUT_PREFLIGHT widgets=3 pending="+str(pending)+
          " desired=GRAPH_EDIT_SUMMARY_NOTES mode="+mode,flush=True)
    if mode=="plan" or pending==0:
        return pending
    if mode!="apply":
        raise RuntimeError("WEEKLY_LAYOUT_UNSUPPORTED_MODE")
    # Park at non-overlapping temporary positions to avoid automatic tile shuffles.
    for i,name in enumerate(ORDER):
        move(dashboard_id,before[name][0],{"x":0,"y":100+30*i,"w":12,"h":10})
    for name in ORDER:
        move(dashboard_id,before[name][0],POSITIONS[name])
    after=inspect(cli("+dashboard-block-list","--base-token",BASE,
                      "--dashboard-id",dashboard_id))
    if any(after[name][0]!=before[name][0] or not equal_pos(after[name][1],POSITIONS[name])
           for name in ORDER):
        raise RuntimeError("WEEKLY_LAYOUT_READBACK_MISMATCH")
    print("WEEKLY_QUOTE_GRAPH_EDIT_GUIDE_BELOW_PASS graph_y=0 guide_y=11 note_y=20",flush=True)
    return pending

def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN")!=BASE:
        raise RuntimeError("WEEKLY_LAYOUT_OTHER_BASE_BLOCKED")
    mode=os.environ.get("FEISHU_PORTAL_MODE","plan")
    if mode not in ("plan","apply"):
        raise RuntimeError("WEEKLY_LAYOUT_BAD_MODE")
    did=find_named(cli("+dashboard-list","--base-token",BASE),DASHBOARD_TITLE)
    if not did or not did.startswith("blk"):
        raise RuntimeError("WEEKLY_LAYOUT_DASHBOARD_MISSING")
    apply_layout(did,mode)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("WEEKLY_LAYOUT_FAILED="+str(exc) if isinstance(exc,RuntimeError)
              else "WEEKLY_LAYOUT_FAILED="+type(exc).__name__,file=sys.stderr)
        sys.exit(1)
