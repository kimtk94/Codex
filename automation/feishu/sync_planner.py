"""Pure, fail-closed Feishu reconciliation planner. No network, no API writes."""
from collections import Counter
from datetime import date

FORMATS = frozenset(("Payment Outstanding","eTax Invoice","Payment Receipt","Prepayments"))

def plan(format_name, source_date, source_rows, target_rows, owned_fields, key_field="source_key"):
    """Return action counts and private change objects; caller must not log change objects."""
    if format_name not in FORMATS or not isinstance(source_date,date):
        raise ValueError("Unknown format or invalid date")
    if not owned_fields or key_field in owned_fields:
        raise ValueError("Invalid owned field configuration")
    def index(rows, side):
        result={}
        for row in rows:
            if not isinstance(row,dict):
                raise ValueError("Invalid "+side+" row")
            key=row.get(key_field)
            if not isinstance(key,str) or not key.strip() or key in result:
                raise ValueError("Missing/duplicate stable key in "+side)
            result[key]=row
        return result
    sources=index(source_rows,"source")
    targets=index(target_rows,"target")
    actions=[]
    for key,src in sources.items():
        if not set(owned_fields).issubset(src):
            raise ValueError("Unmapped field in source")
        dest=targets.get(key)
        if dest is None:
            actions.append({"kind":"create","key":key,"fields":{k:src[k] for k in owned_fields}})
            continue
        previous=dest.get("_source_date")
        if previous:
            if not isinstance(previous,date):
                raise ValueError("Invalid stored source date")
            if previous>source_date:
                actions.append({"kind":"stale","key":key})
                continue
        delta={k:src[k] for k in owned_fields if dest.get(k)!=src[k]}
        if delta:
            actions.append({"kind":"update","key":key,"fields":delta})
        else:
            actions.append({"kind":"unchanged","key":key})
    # A missing source row is not a deletion: source filtering and deletes are ambiguous.
    absent=sum(1 for key in targets if key not in sources)
    counts=dict(Counter(x["kind"] for x in actions))
    for kind in ("create","update","stale","unchanged"):
        counts.setdefault(kind,0)
    counts["target_only_preserved"]=absent
    return counts,actions

def summarize(counts):
    """Aggregates only: never prints identifiers or sensitive field values."""
    return {k:int(v) for k,v in counts.items()}
