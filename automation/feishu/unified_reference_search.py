#!/usr/bin/env python3
"""Local-only typed reference lookup; not a canonical relation writer.

A result row shows observations from one source record. Only named source
pairs are emitted as edges, never transitive or all-column joins. The query
result contains business identifiers; it must stay outside the repository.
"""
import argparse
from collections import Counter, defaultdict
import datetime as dt
from getpass import getpass
import json
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

import global_relationship_coverage as g
import global_mail_relationship_coverage as m

DOC_KIND = "INVOICE_DOCUMENT_REF"
INVOICE_KINDS = ("EXPLICIT_CMS_NUMBER", "INVOICE_LABELLED_NUMBER", "STRUCTURED_INVOICE_NUMBER")
MAIL_KINDS = ("CANONICAL_MAIL_KEY", "QQ_MAIL_KEY", "CRM_MAIL_KEY")
ALIASES = {"X": ("X_PROJECT", "X_REPORTED"), "QUOTE": ("QUOTE_OBJECT", "QID")}
LIMIT = 5000
REGISTRY = "Unified 2025+ Relationships"
SCHEMAS = {name:dict(spec[3]) for name,spec in g.SOURCES.items()}
# Keep the invoice document-number domain separate even before #1079 merges.
SCHEMAS[REGISTRY]["invoice_number"] = DOC_KIND
SCHEMAS[REGISTRY]["sfdc_quote_id"] = "QUOTE_OBJECT"
SCHEMAS[REGISTRY]["amea_quote_id"] = "AMEA"


class SearchError(RuntimeError):
    pass


def sf18(raw,kind):
    """Validate checksum and preserve case; no unsafe first-15 truncation."""
    if not re.fullmatch(g.FORMATS[kind],raw):
        return ""
    first=raw[:15]
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"
    suffix="".join(alphabet[sum(1<<j for j in range(5) if first[i+j].isupper())]
                   for i in range(0,15,5))
    canonical=first+suffix
    return canonical if len(raw)==15 or raw==canonical else ""


def token(raw,kind):
    raw=str(raw or "").strip()
    for k in g.POLYMORPHIC.get(kind,(kind,)):
        if k in ("QQ_MAIL_KEY","CRM_MAIL_KEY"):
            if re.fullmatch(r"[0-9a-f]{64}",raw):
                return k,raw
        elif k=="CANONICAL_MAIL_KEY":
            if re.fullmatch(r"(?:legacy:All Emails:\d+|imap:[^|\r\n]+\|\d+\|\d+)",raw):
                return k,raw
        elif k.endswith("_OBJECT"):
            v=sf18(raw,k)
            if v:
                return k,v
        elif k in (DOC_KIND,*INVOICE_KINDS):
            if re.fullmatch(r"\d{10,15}",raw):
                return k,raw
        elif k in g.FORMATS:
            v=raw.upper()
            if re.fullmatch(g.FORMATS[k],v):
                return k,raw if k in ("OPP_REF","LEAD_REF","QID","QUOTE_PRODUCT_REF") else v
    return None


def cell(raw,kind):
    if not raw:
        return set(),"EMPTY"
    pieces=re.split(r"[|;,\n]+",raw) if kind.endswith("*") else [raw]
    found=set()
    invalid=False
    for p in pieces:
        if not p.strip():
            continue
        t=token(p,kind.rstrip("*"))
        if t is None:
            invalid=True
        else:
            found.add(t)
    return found,("PARTIAL_FORMAT_REVIEW" if found and invalid else
                  "FORMAT_REVIEW" if invalid or not found else "OBSERVED")


def as_ref(t):
    return {"type":t[0],"value":t[1]}


def queries(kind,raw):
    if kind in g.POLYMORPHIC:
        raise SearchError("SEARCH_EXPLICIT_TYPE_REQUIRED")
    matches={t for k in ALIASES.get(kind,(kind,)) if (t:=token(raw,k))}
    if not matches:
        raise SearchError("SEARCH_INVALID_TYPED_QUERY")
    return matches


class ReferenceIndex:
    def __init__(self):
        self.rows=[]
        self.by_token=defaultdict(list)

    def add(self,source,ordinal,fields,pairs=(),stable_key=None,review=()):
        refs=set().union(*fields.values()) if fields else set()
        if stable_key:
            refs.add(stable_key)
        if not refs:
            return
        edges=set()
        for left,right in pairs:
            aa,bb=fields.get(left,set()),fields.get(right,set())
            if left in review or right in review or len(aa)!=1:
                continue
            a=next(iter(aa))
            for b in bb:
                if a[0]!=b[0]:
                    edges.add((a,b))
        row={"source":source,"source_row_ordinal":ordinal,"refs":refs,
             "edges":edges,"field_format_review":set(review),"stable_key":stable_key}
        i=len(self.rows)
        self.rows.append(row)
        for t in refs:
            self.by_token[t].append(i)

    def search(self,kind,raw,offset=0,limit=100):
        if type(offset)!=int or type(limit)!=int or offset<0 or not 1<=limit<=LIMIT:
            raise SearchError("SEARCH_PAGE_BOUND")
        wanted=queries(kind,raw)
        indices=sorted({i for t in wanted for i in self.by_token.get(t,[])})
        counts=Counter(self.rows[i]["source"] for i in indices)
        # Edges are explicitly incident to the query, not inferred transitively.
        direct=defaultdict(set)
        for i in indices:
            r=self.rows[i]
            for a,b in r["edges"]:
                if a in wanted or b in wanted:
                    direct[(a,b)].add(r["source"])
        # Include each page's matching row references as observations, not
        # as a claim that every pair of those identifiers is connected.
        records=[]
        for i in indices[offset:offset+limit]:
            r=self.rows[i]
            records.append({"source":r["source"],"source_row_ordinal":r["source_row_ordinal"],
                "stable_mail_key":as_ref(r["stable_key"]) if r["stable_key"] else None,
                "matched":[as_ref(t) for t in sorted(r["refs"]&wanted)],
                "same_record_observations":[as_ref(t) for t in sorted(r["refs"]-wanted)],
                "field_format_review":sorted(r["field_format_review"])})
        all_edges=sorted(direct)
        edge_page=all_edges[offset:offset+limit]
        return {"query":[as_ref(t) for t in sorted(wanted)],"matched_source_rows":len(indices),
                "source_row_counts":dict(sorted(counts.items())),
                "direct_reference_edges_total":len(all_edges),
                "direct_reference_edges":[{"left":as_ref(a),"right":as_ref(b),
                    "observed_in":sorted(direct[(a,b)])} for a,b in edge_page],
                "records":records,"offset":offset,"limit":limit,
                "records_remaining":max(0,len(indices)-offset-len(records)),
                "edges_remaining":max(0,len(all_edges)-offset-len(edge_page)),
                "row_ordinal":"READ_RESULT_ORDER_NOT_STABLE_SHEET_ROW_ID",
                "certification":"OBSERVED_REFERENCES_ONLY","business_writes":0}


def add_nonmail(index,sources):
    if set(sources)!=set(SCHEMAS):
        raise SearchError("SEARCH_SOURCE_SET_INCOMPLETE")
    for name,schema in SCHEMAS.items():
        for i,row in enumerate(sources[name],1):
            if not set(schema)<=set(row):
                raise SearchError("SEARCH_SOURCE_SCHEMA")
            fields={}
            review=set()
            for col,kind in schema.items():
                fields[col],state=cell(g.value(row,col),kind)
                if state not in ("OBSERVED","EMPTY"):
                    review.add(col)
            # Existing Registry endpoints require #1079's separate audit;
            # its identifiers remain searchable, but no edge is promoted.
            index.add(name,i,fields,g.PAIRS.get(name,()),review=review)


def mail_fields(row,canonical):
    fields={}
    review=set()
    mapping={"AMEA":"amea_numbers" if canonical else "AMEA",
             "H":"h_project_numbers" if canonical else "H Project"}
    if canonical:
        mapping.update({"SAM":"sam_numbers","STRUCTURED_INVOICE_NUMBER":"invoice_numbers"})
    for kind,col in mapping.items():
        fields[kind],state=cell(g.value(row,col),kind+"*")
        if state not in ("OBSERVED","EMPTY"):
            review.add(kind)
    subject=g.value(row,"subject" if canonical else "Subject")
    observed=m.subject_refs(subject)
    for k in ("AMEA","H","SAM","X_PROJECT","QID"):
        subject_tokens={t for v in observed[k] if (t:=token(v,k))}
        prior=fields.get(k,set())
        if prior and subject_tokens and prior!=subject_tokens:
            review.add(k)
        fields[k]=prior|subject_tokens
    label=r"\s*(?:NO\.?|NUMBER|#|:)?\s*[:#]?\s*(\d{10,15})(?![\d-])"
    cms=set(re.findall(r"\bCMS(?:\s+INVOICE)?"+label,subject.upper()))
    invoice=set(re.findall(r"\bINVOICE"+label,subject.upper()))-cms
    fields["EXPLICIT_CMS_NUMBER"]={("EXPLICIT_CMS_NUMBER",v) for v in cms}
    fields["INVOICE_LABELLED_NUMBER"]={("INVOICE_LABELLED_NUMBER",v) for v in invoice}
    # Mail observations remain rows only. No AMEA -> H/SAM/X edge from
    # merely appearing together, including singleton AMEA messages.
    return fields,review


def add_mail(index,canonical_rows,tables):
    if set(tables)!=set(m.TABLE_FIELDS):
        raise SearchError("SEARCH_MAIL_SOURCE_SET_INCOMPLETE")
    seen=set()
    derived=set()
    for i,row in enumerate(canonical_rows,1):
        key,qqkey=m.canonical_key(row)
        if key in seen or (qqkey and qqkey in derived):
            raise SearchError("SEARCH_CANONICAL_DUPLICATE")
        seen.add(key)
        fields,review=mail_fields(row,True)
        if qqkey:
            derived.add(qqkey)
            # The derived tuple hash supports lookup, not proof that QQ
            # currently contains a row. The source is still Canonical.
            fields["DERIVED_QQ_KEY"]={("QQ_MAIL_KEY",qqkey)}
        index.add("Canonical Mail Ledger",i,fields,stable_key=("CANONICAL_MAIL_KEY",key),review=review)
    for source,kind in ((m.QQ,"QQ_MAIL_KEY"),(m.CRM,"CRM_MAIL_KEY")):
        for i,(key,row) in enumerate(m.keyed(tables[source],"Mail Key",True).items(),1):
            fields,review=mail_fields(row,False)
            index.add(source,i,fields,stable_key=(kind,key),review=review)
    # Identity and tracker projections are intentionally excluded as
    # authoritative edges. Existing audit covers those relationship states.


def private_target(path):
    if os.environ.get("GITHUB_ACTIONS") or os.environ.get("CI"):
        raise SearchError("SEARCH_LOCAL_ONLY")
    target=Path(path)
    if not target.is_absolute():
        raise SearchError("SEARCH_ABSOLUTE_OUTPUT_REQUIRED")
    target=target.resolve()
    repo=Path(__file__).resolve().parents[2]
    if target==repo or repo in target.parents:
        raise SearchError("SEARCH_OUTSIDE_REPO_REQUIRED")
    if not target.parent.is_dir() or target.exists():
        raise SearchError("SEARCH_NEW_LOCAL_FILE_REQUIRED")
    return target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope",choices=("project","all"),default="project")
    parser.add_argument("--type",required=True,help="Exact typed identifier (X or QUOTE aliases allowed)")
    parser.add_argument("--output",required=True,help="New absolute path in a private local folder outside Git")
    parser.add_argument("--offset",type=int,default=0)
    parser.add_argument("--limit",type=int,default=100)
    args=parser.parse_args()
    target=private_target(args.output)
    if not sys.stdin.isatty():
        raise SearchError("SEARCH_INTERACTIVE_TERMINAL_REQUIRED")
    if args.offset<0 or not 1<=args.limit<=LIMIT:
        raise SearchError("SEARCH_PAGE_BOUND")
    raw=getpass("Enter identifier (hidden): ")
    queries(args.type,raw)
    from sales_metrics_sync import CSS_SHEET,sheets_session
    started=dt.datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    session=sheets_session()
    index=ReferenceIndex()
    add_nonmail(index,g.read_sources(session))
    if args.scope=="all":
        add_mail(index,m.read_canonical(session,CSS_SHEET),m.read_feishu())
    result=index.search(args.type,raw,args.offset,args.limit)
    result.update({"scope":args.scope,"read_started_kst":started,
                   "read_finished_kst":dt.datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
                   "source_freshness":"NOT_ATTESTED","owner_filter_applied":False})
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
    print("REFERENCE_SEARCH_COMPLETE matched_rows="+str(result["matched_source_rows"])+
          " direct_edges="+str(result["direct_reference_edges_total"])+" business_writes=0")


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        # Never print values, exceptions from API clients, local paths or tokens.
        print("REFERENCE_SEARCH_FAILED "+(str(exc) if isinstance(exc,SearchError)
                                           else type(exc).__name__),file=sys.stderr)
        sys.exit(1)
