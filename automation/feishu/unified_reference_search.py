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


def index_parity(index,sources,canonical_rows=None,tables=None):
    """Verify complete source membership and inverted postings, aggregate only.

    Reparse each raw row and compare against the indexed membership. This
    validates index assembly, not independent semantic correctness of the
    shared identifier parser or a transactional source snapshot. No raw
    values, query IDs, source records or per-key hashes are returned.
    """
    if (canonical_rows is None)!=(tables is None):
        raise SearchError("SEARCH_PARITY_MAIL_SCOPE_INCOMPLETE")
    if set(sources)!=set(SCHEMAS):
        raise SearchError("SEARCH_PARITY_SOURCE_SET")
    actual={}
    for i,row in enumerate(index.rows):
        marker=(row["source"],row["source_row_ordinal"])
        if marker in actual:
            raise SearchError("SEARCH_PARITY_DUPLICATE_SOURCE_ROW")
        actual[marker]=(i,row)

    seen=set()
    received=Counter()
    indexed=Counter()
    no_refs=Counter()
    reviewed=Counter()

    def check(source,ordinal,fields,pairs=(),stable=None,review=()):
        marker=(source,ordinal)
        if marker in seen:
            raise SearchError("SEARCH_PARITY_DUPLICATE_EXPECTED_ROW")
        seen.add(marker)
        received[source]+=1
        refs={t for values in fields.values() for t in values}
        if stable:
            refs.add(stable)
        if not refs:
            no_refs[source]+=1
            if marker in actual:
                raise SearchError("SEARCH_PARITY_UNEXPECTED_EMPTY_ROW")
            return
        entry=actual.get(marker)
        if entry is None:
            raise SearchError("SEARCH_PARITY_MISSING_SOURCE_ROW")
        _,row=entry
        if row["refs"]!=refs or row["stable_key"]!=stable or row["field_format_review"]!=set(review):
            raise SearchError("SEARCH_PARITY_ROW_MEMBERSHIP")
        expected_edges=set()
        for left,right in pairs:
            if left in review or right in review:
                continue
            aa=fields.get(left,set())
            bb=fields.get(right,set())
            if len(aa)==1:
                expected_edges.update((x,y) for x in aa for y in bb if x[0]!=y[0])
        if row["edges"]!=expected_edges:
            raise SearchError("SEARCH_PARITY_ROW_EDGES")
        indexed[source]+=1
        if review:
            reviewed[source]+=1

    for name,schema in SCHEMAS.items():
        # Include explicitly empty source tabs in the summary.
        received[name]=0
        for ordinal,row in enumerate(sources[name],1):
            if not set(schema)<=row.keys():
                raise SearchError("SEARCH_PARITY_SOURCE_SCHEMA")
            fields={}
            review=set()
            for col,kind in schema.items():
                refs,state=cell(g.value(row,col),kind)
                fields[col]=refs
                if state not in ("OBSERVED","EMPTY"):
                    review.add(col)
            check(name,ordinal,fields,g.PAIRS.get(name,()),review=review)
    if tables is not None:
        if set(tables)!=set(m.TABLE_FIELDS):
            raise SearchError("SEARCH_PARITY_MAIL_SOURCE_SET")
        received["Canonical Mail Ledger"]=0
        canonical_keys=set()
        tuple_hashes=set()
        for ordinal,row in enumerate(canonical_rows,1):
            key,derived=m.canonical_key(row)
            if key in canonical_keys or (derived and derived in tuple_hashes):
                raise SearchError("SEARCH_PARITY_CANONICAL_DUPLICATE")
            canonical_keys.add(key)
            fields,review=mail_fields(row,True)
            if derived:
                tuple_hashes.add(derived)
                fields["DERIVED_QQ_KEY"]={("QQ_MAIL_KEY",derived)}
            check("Canonical Mail Ledger",ordinal,fields,
                  stable=("CANONICAL_MAIL_KEY",key),review=review)
        for name,kind in ((m.QQ,"QQ_MAIL_KEY"),(m.CRM,"CRM_MAIL_KEY")):
            received[name]=0
            for ordinal,(key,row) in enumerate(m.keyed(tables[name],"Mail Key",True).items(),1):
                fields,review=mail_fields(row,False)
                check(name,ordinal,fields,stable=(kind,key),review=review)

    if set(actual)-seen or sum(indexed.values())!=len(index.rows):
        raise SearchError("SEARCH_PARITY_EXTRA_SOURCE_ROW")
    expected_postings=defaultdict(list)
    type_counts=Counter()
    for i,row in enumerate(index.rows):
        for t in row["refs"]:
            expected_postings[t].append(i)
            type_counts[t[0]]+=1
    # Compare every posting, including ordering/duplicates and unexpected
    # keys; an empty invented entry is a failure too.
    if dict(index.by_token)!=dict(expected_postings):
        raise SearchError("SEARCH_PARITY_INVERTED_POSTINGS")
    distinct_by_type=Counter(t[0] for t in expected_postings)
    # Probe one deterministic exact identifier per type against an
    # independent linear membership scan; no chosen values are emitted.
    probes=0
    for kind in sorted(distinct_by_type):
        t=min(v for v in expected_postings if v[0]==kind)
        want=[i for i,row in enumerate(index.rows) if t in row["refs"]]
        out=index.search(kind,t[1],offset=0,limit=1)
        expected_sources=Counter(index.rows[i]["source"] for i in want)
        if (out["matched_source_rows"]!=len(want)
                or out["source_row_counts"]!=dict(sorted(expected_sources.items()))
                or len(out["records"])!=1
                or out["records"][0]["source"]!=index.rows[want[0]]["source"]
                or out["records"][0]["source_row_ordinal"]!=index.rows[want[0]]["source_row_ordinal"]
                or out["records_remaining"]!=len(want)-1):
            raise SearchError("SEARCH_PARITY_QUERY_PROBE")
        probes+=1
    by_source={name:{"raw_rows":received[name],"indexed_rows":indexed[name],
                     "no_valid_typed_reference_rows":no_refs[name],"format_review_indexed_rows":reviewed[name]}
               for name in sorted(received)}
    if any(x["raw_rows"]!=x["indexed_rows"]+x["no_valid_typed_reference_rows"]
           for x in by_source.values()):
        raise SearchError("SEARCH_PARITY_SOURCE_COUNTS")
    return {"status":"INDEX_MEMBERSHIP_AND_POSTINGS_PASS",
            "sources":by_source,"sources_indexed":len(by_source),
            "source_rows":sum(received.values()),"indexed_rows":len(index.rows),
            "typed_identifiers":len(expected_postings),
            "distinct_identifiers_by_type":dict(distinct_by_type),
            "posting_memberships_by_type":dict(type_counts),"query_types_probed":probes,
            "source_snapshot_transactional":"NOT_ATTESTED",
            "identifier_parser_independent_validation":"NOT_ATTESTED",
            "owner_payment_delivery_certification":"NOT_ATTESTED",
            "business_writes":0}


def aggregate_environment():
    """Permit credentialed CI only in the manual main-branch audit."""
    if os.environ.get("GITHUB_ACTIONS"):
        if (os.environ.get("GITHUB_REF")!="refs/heads/main"
                or os.environ.get("GITHUB_EVENT_NAME")!="workflow_dispatch"):
            raise SearchError("SEARCH_PARITY_MAIN_MANUAL_ONLY")
    elif os.environ.get("CI"):
        raise SearchError("SEARCH_PARITY_UNRECOGNIZED_CI")


def read_index_inputs(scope):
    from sales_metrics_sync import CSS_SHEET,sheets_session
    session=sheets_session()
    sources=g.read_sources(session)
    canonical_rows=tables=None
    if scope=="all":
        canonical_rows=m.read_canonical(session,CSS_SHEET)
        tables=m.read_feishu()
    index=ReferenceIndex()
    add_nonmail(index,sources)
    if tables is not None:
        add_mail(index,canonical_rows,tables)
    return index,sources,canonical_rows,tables


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
    parser.add_argument("--type",help="Exact typed identifier (X or QUOTE aliases allowed)")
    parser.add_argument("--output",help="New absolute path in a private local folder outside Git")
    parser.add_argument("--verify-index",action="store_true",
                        help="Aggregate-only membership and posting parity; no query or output file")
    parser.add_argument("--offset",type=int,default=0)
    parser.add_argument("--limit",type=int,default=100)
    args=parser.parse_args()
    if args.verify_index:
        if args.type is not None or args.output is not None or args.offset!=0 or args.limit!=100:
            raise SearchError("SEARCH_PARITY_NO_QUERY_OR_OUTPUT")
        aggregate_environment()
        started=dt.datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
        index,sources,canonical_rows,tables=read_index_inputs(args.scope)
        result=index_parity(index,sources,canonical_rows,tables)
        result.update({"scope":args.scope,"read_started_kst":started,
                       "read_finished_kst":dt.datetime.now(ZoneInfo("Asia/Seoul")).isoformat()})
        print("REFERENCE_INDEX_PARITY "+json.dumps(result,sort_keys=True))
        return
    if args.type is None or args.output is None:
        raise SearchError("SEARCH_QUERY_AND_OUTPUT_REQUIRED")
    target=private_target(args.output)
    if not sys.stdin.isatty():
        raise SearchError("SEARCH_INTERACTIVE_TERMINAL_REQUIRED")
    if args.offset<0 or not 1<=args.limit<=LIMIT:
        raise SearchError("SEARCH_PAGE_BOUND")
    raw=getpass("Enter identifier (hidden): ")
    queries(args.type,raw)
    started=dt.datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    index,_,_,_=read_index_inputs(args.scope)
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
