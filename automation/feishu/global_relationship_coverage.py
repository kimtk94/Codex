#!/usr/bin/env python3
"""Read-only global source identifier coverage, independent of owner and Board.

Observation of identifiers in a source row is not certification of a business
relationship, current status, delivery, invoice issue or payment. No writes.
"""
from collections import Counter, defaultdict
import argparse
import os
from pathlib import Path
import datetime as dt
import json
import re
import sys
import urllib.parse
from zoneinfo import ZoneInfo

# Column identity is deliberate: report business IDs are not Salesforce object
# IDs. In particular SFDC Quote Export "AMEA Quotation ID" currently stores QID.
# Each spec is (book, max grid rows, observation role, field -> typed key).
SOURCES = {
    "CSS Project Dashboard": ("CSS", 2000, "CSS_SNAPSHOT", {
        "project_id":"AMEA", "h_project_numbers":"H*", "sam_numbers":"SAM*"}),
    "CSS Project Timeline": ("CSS", 10000, "CSS_HISTORY", {
        "project_id":"AMEA", "h_project_numbers":"H*", "sam_numbers":"SAM*"}),
    "CSS Contract-SIF Tracker": ("CSS", 3000, "CSS_SIF", {
        "project_id":"AMEA", "Contract No.":"H*", "SIF No.":"SIF"}),
    "Quote Portfolio": ("UNIFIED", 5000, "QUOTE_REFERENCE", {
        "Approved AMEA ID":"AMEA", "Quote QID":"QID",
        "Salesforce Quote ID (18)":"QUOTE_OBJECT", "Opportunity ID":"OPP_REF"}),
    "BI Project Lifecycle Overview": ("UNIFIED", 3000, "LIFECYCLE_REFERENCE", {
        "AMEA":"AMEA", "Project / Sub-project":"X_PROJECT"}),
    "Feishu Latest Online": ("UNIFIED", 3000, "ONLINE_CURRENT_SNAPSHOT", {
        "Contract Number":"H", "Sub-Project Number":"X_PROJECT"}),
    "Feishu Latest Outstanding": ("UNIFIED", 3000, "OUTSTANDING_SNAPSHOT", {
        "Quotation Number":"AMEA", "Project Number":"X_REPORTED", "CMS Invoice Number":"CMS"}),
    "Feishu Latest eTax": ("UNIFIED", 3000, "ETAX_SNAPSHOT", {
        "Quotation Number":"AMEA", "Project Number":"X_REPORTED", "CMS Invoice Num":"CMS"}),
    "Feishu Latest Prepayments": ("UNIFIED", 3000, "PREPAYMENT_SNAPSHOT", {
        "Quotation Number":"AMEA", "Project Number":"X_REPORTED", "CMS Invoice Number":"CMS"}),
    "Feishu Latest Receipts": ("UNIFIED", 3000, "RECEIPT_REFERENCE", {
        "CMS No.":"CMS*", "CMS No. [2]":"CMS*", "CMS No. [3]":"CMS*"}),
    "SFDC Quote Export": ("UNIFIED", 5000, "QUOTE_OBJECT_SNAPSHOT", {
        "Salesforce Record ID":"QUOTE_OBJECT", "AMEA Quotation ID":"QID",
        "Opportunity ID":"OPP_REF", "Account ID":"ACCOUNT_OBJECT", "Contact ID":"CONTACT_OBJECT"}),
    "SFDC Email Leads Raw": ("UNIFIED", 5000, "LEAD_REPORT", {
        "SFDC Lead ID":"LEAD_REF", "Lead ID":"LEAD_OBJECT", "Account ID":"ACCOUNT_OBJECT",
        "Contact ID":"CONTACT_OBJECT", "Opportunity ID":"OPP_REF", "Opportunity ID.1":"OPP_REF"}),
    "SFDC Email Opportunities Raw": ("UNIFIED", 5000, "OPPORTUNITY_REPORT", {
        "Opportunity ID":"OPP_REF", "Lead Converted ID":"LEAD_REF", "Account ID":"ACCOUNT_OBJECT"}),
    "SFDC Email Quotation Raw": ("UNIFIED", 10000, "QUOTE_LINE_REPORT", {
        "SFDC Quotation ID":"QID", "Quotation Product ID":"QUOTE_PRODUCT_REF",
        "Opportunity ID":"OPP_REF", "Contact ID":"CONTACT_OBJECT", "*Account Id":"ACCOUNT_OBJECT"}),
    "SFDC Raw - Account": ("UNIFIED", 5000, "ACCOUNT_OBJECT_REFERENCE", {"Account ID":"ACCOUNT_OBJECT"}),
    "SFDC Raw - Contact": ("UNIFIED", 5000, "CONTACT_OBJECT_REFERENCE", {
        "Contact ID":"CONTACT_OBJECT", "Account ID":"ACCOUNT_OBJECT"}),
    "SFDC Raw - Opportunity": ("UNIFIED", 5000, "OPPORTUNITY_OBJECT_REFERENCE", {
        "Opportunity ID":"OPP_OBJECT", "Account ID":"ACCOUNT_OBJECT"}),
    "SFDC Raw - Quote": ("UNIFIED", 5000, "QUOTE_OBJECT_REFERENCE", {
        "Quote Record ID":"QUOTE_OBJECT", "AMEA Quotation ID":"QUOTE_BUSINESS",
        "Opportunity ID":"OPP_OBJECT", "Account ID":"ACCOUNT_OBJECT"}),
    "SFDC Verified Relations": ("UNIFIED", 5000, "EXISTING_RELATION_REFERENCE", {
        "Quotation ID":"QID", "Opportunity ID":"OPP_REF", "Lead Converted ID":"LEAD_REF"}),
    "Unified 2025+ Relationships": ("UNIFIED", 10000, "EXISTING_RELATION_REFERENCE", {
        "account_id":"ACCOUNT_OBJECT", "contact_id":"CONTACT_OBJECT",
        "opportunity_id":"OPP_ANY", "sfdc_quote_id":"QUOTE_BUSINESS",
        "amea_quote_id":"QUOTE_BUSINESS", "invoice_number":"INVOICE_DOCUMENT_REF", "project_id":"PROJECT_ANY"}),
}

# Pairs only from explicit named columns of the SAME source row. Do not
# cross-product unrelated H/SAM/X fields, nor infer from a display name.
# An observed reference is weaker than an authoritative verified relation.
PAIRS = {
    "CSS Project Dashboard": (("project_id","h_project_numbers"), ("project_id","sam_numbers")),
    "CSS Project Timeline": (("project_id","h_project_numbers"), ("project_id","sam_numbers")),
    "CSS Contract-SIF Tracker": (("project_id","Contract No."), ("project_id","SIF No.")),
    "Quote Portfolio": (("Quote QID","Approved AMEA ID"), ("Quote QID","Salesforce Quote ID (18)"),
                        ("Quote QID","Opportunity ID")),
    "BI Project Lifecycle Overview": (("AMEA","Project / Sub-project"),),
    "Feishu Latest Online": (("Contract Number","Sub-Project Number"),),
    "Feishu Latest Outstanding": (("CMS Invoice Number","Quotation Number"), ("CMS Invoice Number","Project Number")),
    "Feishu Latest eTax": (("CMS Invoice Num","Quotation Number"), ("CMS Invoice Num","Project Number")),
    "Feishu Latest Prepayments": (("CMS Invoice Number","Quotation Number"), ("CMS Invoice Number","Project Number"),
                                    ("Quotation Number","Project Number")),
    "SFDC Quote Export": (("Salesforce Record ID","AMEA Quotation ID"),
                          ("AMEA Quotation ID","Opportunity ID"), ("AMEA Quotation ID","Account ID"),
                          ("AMEA Quotation ID","Contact ID")),
    "SFDC Email Leads Raw": (("SFDC Lead ID","Lead ID"), ("Lead ID","Account ID"),
                             ("Lead ID","Contact ID"), ("SFDC Lead ID","Opportunity ID"),
                             ("SFDC Lead ID","Opportunity ID.1")),
    "SFDC Email Opportunities Raw": (("Opportunity ID","Lead Converted ID"), ("Opportunity ID","Account ID")),
    "SFDC Email Quotation Raw": (("SFDC Quotation ID","Quotation Product ID"),
                                 ("SFDC Quotation ID","Opportunity ID"), ("SFDC Quotation ID","*Account Id"),
                                 ("SFDC Quotation ID","Contact ID")),
    "SFDC Raw - Contact": (("Contact ID","Account ID"),),
    "SFDC Raw - Opportunity": (("Opportunity ID","Account ID"),),
    "SFDC Raw - Quote": (("Quote Record ID","AMEA Quotation ID"), ("Quote Record ID","Opportunity ID"),
                         ("Quote Record ID","Account ID")),
    "SFDC Verified Relations": (("Quotation ID","Opportunity ID"), ("Opportunity ID","Lead Converted ID")),
}

FORMATS = {
    "AMEA": r"AMEA\d{7,}(?:-\d{1,3})?",
    "H": r"H\d+SC\d+(?:-B\d+)?",
    "X_PROJECT": r"X\d+SC\d+(?:-Z\d+)?",
    "X_REPORTED": r"X\d+SC\d+(?:-Z\d+)?",
    "SAM": r"(?:SAM\d{11}(?:-[A-Z0-9_]+)?|Z\d{9})",
    "CMS": r"\d{10,15}",
    # CSS invoice document identifiers are not automatically CMS keys.
    "INVOICE_DOCUMENT_REF": r"\d{10,15}",
    "QID": r"QID-[0-9-]{8,50}",
    "LEAD_REF": r"LEAD-[A-Z0-9-]{1,80}",
    "OPP_REF": r"OPP-[A-Z0-9-]{1,80}",
    "QUOTE_PRODUCT_REF": r"QD-[A-Z0-9-]{1,80}",
    "SIF": r"[A-Z0-9][A-Z0-9_.-]{0,79}",
    "LEAD_OBJECT": r"00Q[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?",
    "QUOTE_OBJECT": r"a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?",
    "ACCOUNT_OBJECT": r"001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?",
    # Contact identifiers can use nonstandard object prefixes in this export.
    "CONTACT_OBJECT": r"[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?",
    "OPP_OBJECT": r"006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?",
}
POLYMORPHIC = {
    "QUOTE_BUSINESS": ("AMEA","QID","QUOTE_OBJECT"),
    "OPP_ANY": ("OPP_REF","OPP_OBJECT"),
    "PROJECT_ANY": ("AMEA","H","X_REPORTED"),
}

# "One parent" means a review signal, not automatic rejection/correction;
# e.g. a quote can have multiple products and an AMEA multiple X/SAM.
SINGLE_PARENT = {
    ("QID","QUOTE_OBJECT"), ("QID","OPP_REF"), ("QID","ACCOUNT_OBJECT"),
    ("LEAD_REF","LEAD_OBJECT"), ("CONTACT_OBJECT","ACCOUNT_OBJECT"),
    ("OPP_REF","ACCOUNT_OBJECT"), ("CMS","AMEA"), ("X_PROJECT","AMEA"),
    ("X_PROJECT","H"),
}
REVERSE_PAIRS = {("AMEA","X_PROJECT"), ("H","X_PROJECT"), ("QUOTE_OBJECT","QID")}


class CoverageError(RuntimeError):
    pass


def value(row, field):
    raw = row.get(field)
    return "" if raw is None else str(raw).strip()


def typed(raw, kind):
    kinds = POLYMORPHIC.get(kind, (kind,))
    for k in kinds:
        text = raw if k.endswith("_OBJECT") else raw.upper()
        if re.fullmatch(FORMATS[k], text):
            # Keep Salesforce ID case; use the same 15-character convention
            # as existing quote matching. Never use a business ID as object ID.
            return k, text[:15] if k.endswith("_OBJECT") else text
    return None


def keys(raw, kind):
    if not raw:
        return set(), "EMPTY"
    pieces = re.split(r"[|;,\n]+", raw) if kind.endswith("*") else [raw]
    found, invalid = set(), 0
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        token = typed(piece, kind.rstrip("*"))
        if token:
            found.add(token)
        else:
            invalid += 1
    return found, ("PARTIAL_FORMAT_REVIEW" if found and invalid else
                   "OBSERVED" if found else "FORMAT_REVIEW")


def coverage(sources, specs=SOURCES, pairs=PAIRS):
    if set(sources) != set(specs):
        raise CoverageError("GLOBAL_SOURCE_SET_INCOMPLETE")
    populations, fields, edges = {}, {}, defaultdict(set)
    per_source_edges = defaultdict(set)
    all_nodes = defaultdict(set)
    for name, (_, _, role, schema) in specs.items():
        rows = sources[name]
        seen = defaultdict(set)
        states = {col: Counter() for col in schema}
        for row in rows:
            if not set(schema).issubset(row):
                raise CoverageError("GLOBAL_SOURCE_FIELDS_INCOMPLETE")
            refs = {}
            for col, kind in schema.items():
                refs[col], state = keys(value(row, col), kind)
                states[col][state] += 1
                for entity, ident in refs[col]:
                    seen[entity].add(ident)
                    all_nodes[entity].add(ident)
            for left, right in pairs.get(name, ()):
                # Only a singleton anchor can support multiple child references.
                # Do not cross-join two lists or promote malformed partial cells.
                if (len(refs[left]) != 1 or
                        keys(value(row, left), schema[left])[1] != "OBSERVED" or
                        keys(value(row, right), schema[right])[1] != "OBSERVED"):
                    continue
                a = next(iter(refs[left]))
                for b in refs[right]:
                    if a == b:
                        continue
                    x, y = (b, a) if (a[0], b[0]) in REVERSE_PAIRS else (a,b)
                    if x[0] == y[0]:
                        continue
                    edge = (x, y)
                    edges[edge].add(name)
                    per_source_edges[name].add(edge)
        populations[name] = {
            "role": role, "rows": len(rows), "distinct_keys": {k:len(v) for k,v in sorted(seen.items())},
            "observed_edges": len(per_source_edges[name]),
            "population_status": "OBSERVED_ROWS" if rows else "NO_ROWS_OBSERVED",
        }
        fields[name] = {col: dict(counter) for col,counter in states.items()}
        populations[name]["_amea"] = seen.get("AMEA", set())
    baseline = set()
    for name in ("CSS Project Dashboard", "CSS Contract-SIF Tracker"):
        baseline |= populations.get(name, {}).get("_amea", set())
    core_names = ("CSS Project Dashboard", "CSS Project Timeline", "CSS Contract-SIF Tracker",
                  "Quote Portfolio", "BI Project Lifecycle Overview",
                  "Feishu Latest Outstanding", "Feishu Latest eTax")
    core = set().union(*(populations.get(name, {}).get("_amea", set()) for name in core_names))
    for item in populations.values():
        item["amea_outside_css_sif"] = len(item.pop("_amea") - baseline)
    edge_counts, corroborated = Counter(), Counter()
    parents = defaultdict(set)
    for (a,b), observed_in in edges.items():
        label = a[0] + "->" + b[0]
        edge_counts[label] += 1
        if len(observed_in) > 1:
            corroborated[label] += 1
        if (a[0],b[0]) in SINGLE_PARENT:
            parents[(a,b[0])].add(b[1])
    review = Counter(a[0]+"->"+btype for (a,btype), p in parents.items() if len(p)>1)
    return {
        "mode":"READ_ONLY_GLOBAL_SOURCE_OBSERVATIONS",
        "sources_checked":len(specs), "sources":populations, "field_observation_counts":fields,
        "distinct_typed_identifiers":{k:len(v) for k,v in sorted(all_nodes.items())},
        "core_amea_union":len(core), "css_sif_amea_baseline":len(baseline),
        "core_amea_outside_css_sif":len(core-baseline),
        "all_observed_amea_outside_css_sif":len(all_nodes["AMEA"]-baseline),
        "observed_reference_edges":dict(edge_counts),
        "multi_source_observed_edges":dict(corroborated),
        "multiple_parent_candidate_review":dict(review),
        "relationship_certification":"NOT_ATTESTED_BY_THIS_AUDIT",
        "source_freshness":"NOT_ATTESTED_BY_THIS_AUDIT",
        "mail_ledger_coverage":"SEPARATE_AUDIT_REQUIRED",
        "business_writes":0, "owner_filter_applied":False,
    }


# Explicit AMEA anchors; no owner or Board restriction. Keep observed
# historical/reference and current data without promoting business status.
PROJECT_INPUTS = {
    "CSS Project Dashboard": ("project_id", {"H":"h_project_numbers","SAM":"sam_numbers"}),
    "CSS Project Timeline": ("project_id", {"H":"h_project_numbers","SAM":"sam_numbers"}),
    "CSS Contract-SIF Tracker": ("project_id", {"H":"Contract No.","SIF":"SIF No."}),
    "Quote Portfolio": ("Approved AMEA ID", {"QID":"Quote QID","QUOTE_OBJECT":"Salesforce Quote ID (18)"}),
    "BI Project Lifecycle Overview": ("AMEA", {"LIFECYCLE_X":"Project / Sub-project"}),
    "Feishu Latest Outstanding": ("Quotation Number", {"FINANCE_X":"Project Number","CMS":"CMS Invoice Number"}),
    "Feishu Latest eTax": ("Quotation Number", {"FINANCE_X":"Project Number","CMS":"CMS Invoice Num"}),
    "Feishu Latest Prepayments": ("Quotation Number", {"FINANCE_X":"Project Number","CMS":"CMS Invoice Number"}),
}
FINANCE = {"Feishu Latest Outstanding","Feishu Latest eTax"}
PREPAYMENT = "Feishu Latest Prepayments"
BASELINE = {"CSS Project Dashboard","CSS Contract-SIF Tracker"}
RECEIPTS = "Feishu Latest Receipts"
ONLINE = "Feishu Latest Online"


def h_root(h):
    return re.sub(r"-B\d+$", "", h)


def x_base(x):
    return re.sub(r"-Z\d+$", "", x)


def project_relationships(sources):
    """Return aggregate counts and local-only evidence details.

    Direct reference = explicit valid identifier in an AMEA-anchored row.
    A shared key or root is not an instruction to merge AMEA entities.
    The candidate rules below never assign a sample or finance balance to X.
    """
    projects = {}
    reverse = defaultdict(set)
    without_amea = {}
    for name,(anchor,cols) in PROJECT_INPUTS.items():
        schema = SOURCES[name][3]
        missing = Counter()
        for row in sources[name]:
            pid = value(row,anchor).upper()
            if not re.fullmatch(FORMATS["AMEA"],pid):
                missing["EMPTY_AMEA" if not pid else "FORMAT_REVIEW_AMEA"] += 1
                for kind,col in cols.items():
                    refs,_ = keys(value(row,col),schema[col])
                    if refs:
                        missing["WITH_"+kind+"_REFERENCE"] += 1
                continue
            d = projects.setdefault(pid, {"sources":set(),"refs":defaultdict(lambda:defaultdict(set)),
                                          "field_review":Counter()})
            d["sources"].add(name)
            for kind,col in cols.items():
                refs,state = keys(value(row,col),schema[col])
                if state != "OBSERVED":
                    d["field_review"][(name,col,state)] += 1
                # Retain well-formed tokens in a partially malformed list as
                # observations; the source-cell review stays visible.
                for _,ident in refs:
                    d["refs"][kind][ident].add(name)
                    reverse[(kind,ident)].add(pid)
                    if kind == "H":
                        reverse[("H_ROOT",h_root(ident))].add(pid)
        without_amea[name] = dict(missing)
    online_h, online_base, online_parents = defaultdict(set), defaultdict(set), defaultdict(set)
    online_ids = set()
    for row in sources[ONLINE]:
        hs,hstate = keys(value(row,"Contract Number"),"H")
        xs,xstate = keys(value(row,"Sub-Project Number"),"X_PROJECT")
        for _,x in xs:
            online_ids.add(x)
            online_base[x_base(x)].add(x)
            if hstate == xstate == "OBSERVED" and len(hs) == 1:
                h = h_root(next(iter(hs))[1])
                online_h[h].add(x)
                online_parents[x].add(h)
    receipt_refs = defaultdict(set)
    for row in sources[RECEIPTS]:
        for col in SOURCES[RECEIPTS][3]:
            refs,state = keys(value(row,col),"CMS*")
            for _,cms in refs:
                receipt_refs[cms].add("SINGLE_CMS_CELL_REFERENCE" if state=="OBSERVED" and len(refs)==1
                                      else "GROUP_OR_PARTIAL_CMS_CELL_REFERENCE")
    results = []
    for pid,d in sorted(projects.items()):
        refs = d["refs"]
        life = set(refs["LIFECYCLE_X"])
        exact_online = {x for x in life if x in online_ids and reverse[("LIFECYCLE_X",x)]=={pid}}
        h_candidates = defaultdict(set)
        for h in refs["H"]:
            hr = h_root(h)
            for x in online_h[hr]:
                if x in exact_online:
                    continue
                code = ("SHARED_H_ROOT_REVIEW" if reverse[("H_ROOT",hr)]!={pid}
                        else "MULTIPLE_ONLINE_H_REVIEW" if len(online_parents[x])!=1
                        else "LIFECYCLE_PARENT_REVIEW" if reverse[("LIFECYCLE_X",x)]-{pid}
                        else "H_ROOT_CANDIDATE_ONLY")
                h_candidates[x].add(code)
        finance_x = []
        for x,names in sorted(refs["FINANCE_X"].items()):
            candidates = set(online_base.get(x_base(x),()))
            # An explicit suffixed reference must not fall back to a sibling.
            if re.search(r"-Z\d+$",x):
                candidates &= {x}
            finance_x.append({"reported_x":x,"sources":sorted(names),
                              "current_x_candidates":sorted(candidates),
                              "reference_state":("NO_CURRENT_CANDIDATE_OBSERVED" if not candidates
                                                 else "ONE_CURRENT_CANDIDATE_ONLY" if len(candidates)==1
                                                 else "MULTIPLE_CURRENT_CANDIDATES_ONLY")})
        receipt_cms = {c:sorted(receipt_refs[c]) for c in refs["CMS"] if c in receipt_refs}
        reviews = []
        for kind in ("QID","H_ROOT","LIFECYCLE_X","CMS","FINANCE_X","SAM"):
            identifiers = {h_root(h) for h in refs["H"]} if kind=="H_ROOT" else set(refs[kind])
            reviews.extend({"kind":kind,"identifier":ident,"observed_amea_count":len(reverse[(kind,ident)])}
                           for ident in sorted(identifiers) if len(reverse[(kind,ident)])>1)
        cms_finance = {c for c,names in refs["CMS"].items() if names & FINANCE}
        cms_prepay = {c for c,names in refs["CMS"].items() if PREPAYMENT in names}
        x_state = ("EXACT_CURRENT_LIFECYCLE_LITERAL" if exact_online
                   else "LIFECYCLE_X_NOT_EXACT_CURRENT" if life
                   else "FINANCE_X_REFERENCE_ONLY" if refs["FINANCE_X"]
                   else "H_CURRENT_CANDIDATE_ONLY" if h_candidates
                   else "NO_X_REFERENCE_OBSERVED")
        results.append({"amea":pid,"source_tables":sorted(d["sources"]),
                        "refs":{kind:{ident:sorted(names) for ident,names in sorted(ids.items())}
                                for kind,ids in sorted(refs.items()) if ids},
                        "baseline_member":bool(d["sources"] & BASELINE),
                        "current_online_exact_lifecycle_x":sorted(exact_online),
                        "current_h_candidates":{x:sorted(codes) for x,codes in sorted(h_candidates.items())},
                        "finance_x_candidates":finance_x,
                        "receipt_cms_references":receipt_cms,
                        "invoice_cms":sorted(cms_finance),"prepayment_cms":sorted(cms_prepay),
                        "shared_reference_review":reviews,"x_observation_state":x_state,
                        "field_review":[{"source":name,"field":col,"state":state,"rows":n}
                                        for (name,col,state),n in sorted(d["field_review"].items())]})
    def summarize(rows):
        def has(kind):
            return sum(bool(r["refs"].get(kind)) for r in rows)
        return {"amea":len(rows),"quote_qid":has("QID"),"h_contract":has("H"),"sam":has("SAM"),
                "sif":has("SIF"),"lifecycle_x":has("LIFECYCLE_X"),"finance_x":has("FINANCE_X"),
                "any_direct_x":sum(bool(r["refs"].get("LIFECYCLE_X") or r["refs"].get("FINANCE_X")) for r in rows),
                "cms":has("CMS"),"invoice_cms":sum(bool(r["invoice_cms"]) for r in rows),
                "prepayment_cms":sum(bool(r["prepayment_cms"]) for r in rows),
                "receipt_cms_reference":sum(bool(r["receipt_cms_references"]) for r in rows),
                "multiple_source":sum(len(r["source_tables"])>1 for r in rows),
                "single_source":sum(len(r["source_tables"])==1 for r in rows),
                "exact_current_lifecycle_literal":sum(bool(r["current_online_exact_lifecycle_x"]) for r in rows),
                "x_observation_states":dict(Counter(r["x_observation_state"] for r in rows)),
                "no_observed_q_h_x_sam_cms":sum(not any(r["refs"].get(k) for k in
                    ("QID","H","LIFECYCLE_X","FINANCE_X","SAM","CMS")) for r in rows)}
    core = [r for r in results if set(r["source_tables"])-{PREPAYMENT}]
    summary = {"core":summarize(core),"expanded":summarize(results),
               "baseline":summarize([r for r in results if r["baseline_member"]]),
               "outside_baseline":summarize([r for r in results if not r["baseline_member"]]),
               "source_amea_counts":{name:sum(name in r["source_tables"] for r in results) for name in PROJECT_INPUTS},
               "shared_reference_counts":dict(Counter(kind for (kind,_),owners in reverse.items()
                                                     if len(owners)>1)),
               "rows_without_valid_amea":without_amea,
               "receipt_distinct_cms_observed":len(receipt_refs),
               "online_distinct_x_observed":len(online_ids),
               "payment_status":"NOT_ATTESTED_BY_REFERENCE_OBSERVATION",
               "relationship_status":"OBSERVED_REFERENCES_AND_CANDIDATES_ONLY",
               "owner_filter_applied":False}
    return summary,results


def private_project_report(path,summary,details):
    # Optional explicit local output. Never write identifiers to repo or CI.
    if os.environ.get("GITHUB_ACTIONS"):
        raise CoverageError("GLOBAL_PRIVATE_REPORT_FORBIDDEN_IN_CI")
    target=Path(path)
    if not target.is_absolute():
        raise CoverageError("GLOBAL_PRIVATE_REPORT_ABSOLUTE_PATH_REQUIRED")
    target=target.resolve()
    repo=Path(__file__).resolve().parents[2]
    if target==repo or repo in target.parents:
        raise CoverageError("GLOBAL_PRIVATE_REPORT_OUTSIDE_REPO_REQUIRED")
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as stream:
        json.dump({"summary":summary,"projects":details},stream,ensure_ascii=False,indent=2)


# Extra inputs for the existing project-scope audit only. The mail audit
# still calls read_sources(session) with the original source set.
REGISTRY_EVIDENCE_SPECS = {
    "Payment & Tax Invoice": ("UNIFIED", 5000, "LEGACY_PAYMENT_RELATION_REFERENCE", {
        "Invoice Number":"INVOICE_DOCUMENT_REF", "SFDC Quote ID":"QUOTE_OBJECT", "AMEA Project ID":"AMEA"}),
    "CSS Tax Invoice List": ("CSS", 5000, "LEGACY_INVOICE_DOCUMENT_REFERENCE", {
        "invoice_number":"INVOICE_DOCUMENT_REF", "project_id":"AMEA"}),
    "CSS Tax Invoice Extract": ("CSS", 5000, "EXTRACTED_INVOICE_DOCUMENT_REFERENCE", {
        "invoice_number":"INVOICE_DOCUMENT_REF", "project_id":"AMEA"}),
}
REGISTRY_NAME = "Unified 2025+ Relationships"
REGISTRY_FIELDS = {"link_key","left_system","left_entity","left_record_id","right_system",
                   "right_entity","right_record_id","sfdc_quote_id","amea_quote_id",
                   "invoice_number","matching_method","verification_status","verified_at"}


def quote18(raw):
    """Case-sensitive Salesforce quote object key; validate supplied suffix."""
    if not re.fullmatch(FORMATS["QUOTE_OBJECT"],raw):
        return ""
    first=raw[:15]
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"
    suffix="".join(alphabet[sum(1<<j for j in range(5) if first[i+j].isupper())]
                   for i in range(0,15,5))
    canonical=first+suffix
    return canonical if len(raw)==15 or raw==canonical else ""


def registry_reference_audit(sources,evidence):
    """Audit stored links without promoting them to canonical graph edges.

    All output is aggregate. A document reference is never a CMS join key,
    even when the numeric strings coincide in different source tables.
    """
    if set(evidence)!=set(REGISTRY_EVIDENCE_SPECS):
        raise CoverageError("REGISTRY_EVIDENCE_SET_INCOMPLETE")
    required={
        REGISTRY_NAME:REGISTRY_FIELDS,
        "Quote Portfolio":{"Salesforce Quote ID (18)","Approved AMEA ID","Quote QID","Opportunity ID","Active"},
        "SFDC Quote Export":{"Salesforce Record ID","AMEA Quotation ID","Opportunity ID"},
        "SFDC Verified Relations":{"Quotation ID","Opportunity ID"},
        "SFDC Email Opportunities Raw":{"Opportunity ID"},
    }
    for name,cols in required.items():
        if name not in sources or any(not cols<=r.keys() for r in sources[name]):
            raise CoverageError("REGISTRY_SOURCE_SCHEMA")
    for name,(_,_,_,cols) in REGISTRY_EVIDENCE_SPECS.items():
        if any(not set(cols)<=r.keys() for r in evidence[name]):
            raise CoverageError("REGISTRY_EVIDENCE_SCHEMA")

    def index(rows,field,normalize=lambda s:s):
        out=defaultdict(list)
        for r in rows:
            key=normalize(value(r,field))
            if key:
                out[key].append(r)
        return out

    portfolio=sources["Quote Portfolio"]
    exports=sources["SFDC Quote Export"]
    p_obj=index(portfolio,"Salesforce Quote ID (18)",quote18)
    p_amea=index(portfolio,"Approved AMEA ID",str.upper)
    p_qid=index(portfolio,"Quote QID")
    e_obj=index(exports,"Salesforce Record ID",quote18)
    e_qid=index(exports,"AMEA Quotation ID")
    relations=index(sources["SFDC Verified Relations"],"Quotation ID")
    opportunities=index(sources["SFDC Email Opportunities Raw"],"Opportunity ID")
    payment=defaultdict(set)
    for r in evidence["Payment & Tax Invoice"]:
        n=value(r,"Invoice Number")
        q=quote18(value(r,"SFDC Quote ID"))
        p=value(r,"AMEA Project ID").upper()
        if re.fullmatch(FORMATS["INVOICE_DOCUMENT_REF"],n):
            # Keep malformed parents in the comparison rather than letting a
            # valid row hide a conflicting or missing parent for the same key.
            payment[n].add((q,p))
    invoice_refs={}
    for name in ("CSS Tax Invoice List","CSS Tax Invoice Extract"):
        bynumber=defaultdict(set)
        for r in evidence[name]:
            n=value(r,"invoice_number")
            p=value(r,"project_id").upper()
            if re.fullmatch(FORMATS["INVOICE_DOCUMENT_REF"],n):
                # Retain malformed/empty parents as conflicting evidence.
                bynumber[n].add(p)
        invoice_refs[name]=bynumber

    counts=Counter()
    types=Counter()
    quote_states=Counter()
    payment_states=Counter()
    invoice_states={name:Counter() for name in invoice_refs}
    seen=set()
    triples=set()
    ameas=set()
    quote_ids=set()
    doc_ids=set()
    exact_ameas=set()
    exact_opps=set()
    exact_triples=set()
    report_states=Counter()
    registry_rows=sources[REGISTRY_NAME]
    for r in registry_rows:
        key=value(r,"link_key")
        if not key or key in seen:
            raise CoverageError("REGISTRY_LINK_KEY_INVALID_OR_DUPLICATE")
        seen.add(key)
        p=value(r,"amea_quote_id").upper()
        qraw=value(r,"sfdc_quote_id")
        q=quote18(qraw)
        n=value(r,"invoice_number")
        valid_p=bool(re.fullmatch(FORMATS["AMEA"],p))
        valid_n=bool(re.fullmatch(FORMATS["INVOICE_DOCUMENT_REF"],n))
        if valid_p:
            ameas.add(p)
        if q:
            quote_ids.add(q)
            counts["quote_id_15_normalized" if len(qraw)==15 else "quote_id_18_validated"]+=1
        else:
            counts["quote_id_format_review"]+=1
        if valid_n:
            doc_ids.add(n)
        if q and valid_p and valid_n:
            triples.add((q,p,n))
        kind=tuple(value(r,k) for k in ("left_system","left_entity","right_system","right_entity"))
        if kind==("CSS","Invoice","SFDC","Quote"):
            types["CSS_INVOICE_TO_SFDC_QUOTE"]+=1
            endpoints=(value(r,"left_record_id")==n and quote18(value(r,"right_record_id"))==q)
        elif kind==("CSS","QuoteApproval","CSS","Invoice"):
            types["CSS_APPROVAL_TO_CSS_INVOICE"]+=1
            endpoints=(value(r,"left_record_id").upper()==p and value(r,"right_record_id")==n)
        else:
            types["OTHER_RELATION_TYPE_REVIEW"]+=1
            endpoints=False
        endpoints=bool(endpoints and q and valid_p and valid_n)
        counts["exact_declared_endpoints" if endpoints else "endpoint_review"]+=1
        if value(r,"verification_status") in {"SOURCE_RESOLVED_ACTIVE_UNVERIFIED","ID_MATCH_ACTIVE_UNVERIFIED"}:
            counts["stored_active_unverified"]+=1
        if value(r,"verified_at"):
            counts["stored_verification_timestamp_present"]+=1

        if not endpoints:
            state="REGISTRY_ENDPOINT_REVIEW"
        elif len(p_obj.get(q,[]))!=1 or len(e_obj.get(q,[]))!=1:
            state=("QUOTE_OBJECT_NOT_OBSERVED" if q not in p_obj and q not in e_obj
                   else "QUOTE_OBJECT_PARTIAL_OR_MULTIPLE")
        else:
            a,b=p_obj[q][0],e_obj[q][0]
            qid=value(a,"Quote QID")
            opp=value(a,"Opportunity ID")
            if (value(a,"Approved AMEA ID").upper()!=p or len(p_amea.get(p,[]))!=1):
                state="PORTFOLIO_AMEA_REVIEW"
            elif (not re.fullmatch(FORMATS["QID"],qid) or not re.fullmatch(FORMATS["OPP_REF"],opp.upper())
                    or qid!=value(b,"AMEA Quotation ID") or opp!=value(b,"Opportunity ID")
                    or len(p_qid.get(qid,[]))!=1 or len(e_qid.get(qid,[]))!=1):
                state="QID_OPPORTUNITY_REFERENCE_REVIEW"
            else:
                state="EXACT_NORMALIZED_QUOTE_AMEA_QID_OPP"
                exact_ameas.add(p)
                exact_opps.add(opp)
                if value(a,"Active")=="ACTIVE":
                    counts["portfolio_active_label_observed"]+=1
                relation=relations.get(qid,[])
                if len(relation)==1 and value(relation[0],"Opportunity ID")==opp:
                    report_states["QID_OPP_EXACT_VERIFIED_RELATIONS_ROW"]+=1
                else:
                    report_states["QID_OPP_VERIFIED_RELATIONS_REVIEW"]+=1
                report_states["OPP_REPORT_UNIQUE" if len(opportunities.get(opp,[]))==1
                              else "OPP_REPORT_NOT_UNIQUE_OR_ABSENT"]+=1
        quote_states[state]+=1

        pm=payment.get(n,set())
        payment_state=("EXACT_INVOICE_DOCUMENT_QUOTE_AMEA" if q and valid_p and pm=={(q,p)}
                       else "INVOICE_DOCUMENT_NOT_OBSERVED" if not pm
                       else "INVOICE_DOCUMENT_PARENT_REVIEW")
        payment_states[payment_state]+=1
        for name,by_n in invoice_refs.items():
            parents=by_n.get(n,set())
            code=("EXACT_INVOICE_DOCUMENT_AMEA" if valid_p and parents=={p}
                  else "INVOICE_DOCUMENT_NOT_OBSERVED" if not parents
                  else "INVOICE_DOCUMENT_AMEA_REVIEW")
            invoice_states[name][code]+=1
        if (state=="EXACT_NORMALIZED_QUOTE_AMEA_QID_OPP"
                and payment_state=="EXACT_INVOICE_DOCUMENT_QUOTE_AMEA"):
            counts["quote_and_payment_reference_exact_rows"]+=1
            exact_triples.add((q,p,n))

    return {"rows":len(registry_rows),"unique_link_keys":len(seen),"unique_amea":len(ameas),
            "unique_quote_objects":len(quote_ids),"unique_invoice_document_refs":len(doc_ids),
            "unique_invoice_quote_amea_triples":len(triples),
            "unique_exact_quote_payment_triples":len(exact_triples),
            "exact_current_quote_reference_amea":len(exact_ameas),
            "exact_current_quote_reference_opportunities":len(exact_opps),
            "relation_types":dict(types),"quote_reference_states":dict(quote_states),
            "payment_reference_states":dict(payment_states),
            "invoice_document_reference_states":{k:dict(v) for k,v in invoice_states.items()},
            "report_reference_observations":dict(report_states),"diagnostic_counts":dict(counts),
            "reference_scope":"STORED_RELATION_AND_CURRENT_SOURCE_REFERENCES_ONLY",
            "cms_identity":"NOT_INFERRED_FROM_DOCUMENT_NUMBER",
            "owner_payment_issuance_certification":"NOT_ATTESTED",
            "business_writes":0}


def registry_expansion_audit(sources,evidence,projects):
    """Partition nonmail AMEA outside the stored registry, without proposing writes."""
    registry={value(r,"amea_quote_id").upper() for r in sources[REGISTRY_NAME]
              if re.fullmatch(FORMATS["AMEA"],value(r,"amea_quote_id").upper())}
    def index(rows,field,normalize=lambda x:x):
        result=defaultdict(list)
        for r in rows:
            key=normalize(value(r,field))
            if key:
                result[key].append(r)
        return result
    p=sources["Quote Portfolio"]
    e=sources["SFDC Quote Export"]
    by_amea=index(p,"Approved AMEA ID",str.upper)
    p_object=index(p,"Salesforce Quote ID (18)",quote18)
    e_object=index(e,"Salesforce Record ID",quote18)
    p_qid=index(p,"Quote QID")
    e_qid=index(e,"AMEA Quotation ID")
    opps=index(sources["SFDC Email Opportunities Raw"],"Opportunity ID")
    rels=index(sources["SFDC Verified Relations"],"Quotation ID")
    pay=defaultdict(set)
    pay_amea=defaultdict(set)
    for r in evidence["Payment & Tax Invoice"]:
        n=value(r,"Invoice Number")
        pid=value(r,"AMEA Project ID").upper()
        if re.fullmatch(FORMATS["INVOICE_DOCUMENT_REF"],n):
            pay[n].add((quote18(value(r,"SFDC Quote ID")),pid))
            pay_amea[pid].add(n)
    document=defaultdict(set)
    for name in ("CSS Tax Invoice List","CSS Tax Invoice Extract"):
        for r in evidence[name]:
            n=value(r,"invoice_number")
            if re.fullmatch(FORMATS["INVOICE_DOCUMENT_REF"],n):
                document[n].add(value(r,"project_id").upper())
    population={r["amea"] for r in projects}
    if len(population)!=len(projects):
        raise CoverageError("REGISTRY_EXPANSION_DUPLICATE_AMEA")
    groups=Counter()
    counts=Counter()
    references=Counter()
    source_counts=Counter()
    exact_opp=set()
    document_triples=set()
    for r in projects:
        pid=r["amea"]
        if pid in registry:
            continue
        refs=r["refs"]
        portfolio=by_amea.get(pid,[])
        for kind in ("QID","H","SAM","SIF","LIFECYCLE_X","FINANCE_X","CMS"):
            if refs.get(kind):
                references[kind]+=1
        if refs.get("LIFECYCLE_X") or refs.get("FINANCE_X"):
            references["ANY_X"]+=1
        if r["current_online_exact_lifecycle_x"]:
            references["EXACT_CURRENT_LIFECYCLE"]+=1
        if any(f["current_x_candidates"] for f in r["finance_x_candidates"]):
            references["FINANCE_CURRENT_X_CANDIDATE"]+=1
        if r["shared_reference_review"]:
            references["SHARED_REFERENCE_REVIEW"]+=1
        references["MULTIPLE_SOURCES" if len(r["source_tables"])>1 else "SINGLE_SOURCE"]+=1
        source_counts.update(r["source_tables"])
        if len(portfolio)>1:
            state="PORTFOLIO_MULTIPLE_REVIEW"
        elif portfolio:
            a=portfolio[0]
            q=quote18(value(a,"Salesforce Quote ID (18)"))
            qid=value(a,"Quote QID")
            opp=value(a,"Opportunity ID")
            if not q or len(p_object.get(q,[]))!=1 or len(e_object.get(q,[]))!=1:
                state="QUOTE_OBJECT_REVIEW"
            elif (not re.fullmatch(FORMATS["QID"],qid)
                    or not re.fullmatch(FORMATS["OPP_REF"],opp.upper())
                    or len(p_qid.get(qid,[]))!=1 or len(e_qid.get(qid,[]))!=1
                    or qid!=value(e_object[q][0],"AMEA Quotation ID")
                    or opp!=value(e_object[q][0],"Opportunity ID")):
                state="QID_OPPORTUNITY_REFERENCE_REVIEW"
            else:
                # Case-insensitive syntax checks above do not authorize
                # case-folded identity joins; source values must match exactly.
                exact_opp.add(opp)
                counts["exact_quote_reference_projects"]+=1
                if value(a,"Active")=="ACTIVE":
                    counts["portfolio_active_label_observed"]+=1
                if len(opps.get(opp,[]))==1:
                    counts["opportunity_report_unique"]+=1
                relation=rels.get(qid,[])
                if len(relation)==1 and value(relation[0],"Opportunity ID")==opp:
                    counts["verified_relation_reference_exact"]+=1
                if value(e_object[q][0],"Account ID"):
                    counts["export_account_reference_observed"]+=1
                if value(e_object[q][0],"Contact ID"):
                    counts["export_contact_reference_observed"]+=1
                docs={(q,pid,n) for n in pay_amea[pid] if pay[n]=={(q,pid)} and document[n]=={pid}}
                document_triples.update(docs)
                state=("EXACT_DOCUMENT_QUOTE_REFERENCE_CANDIDATE" if docs
                       else "EXACT_QUOTE_REFERENCE_ONLY")
        elif r["current_online_exact_lifecycle_x"]:
            state="EXACT_CURRENT_LIFECYCLE_NO_QUOTE"
        elif refs.get("LIFECYCLE_X") or refs.get("FINANCE_X"):
            state="X_REFERENCE_REVIEW_NO_QUOTE"
        elif any(refs.get(k) for k in ("H","SAM","SIF")):
            state="H_SAM_SIF_REFERENCE_NO_QUOTE"
        else:
            state="OTHER_REFERENCE_REVIEW"
        groups[state]+=1
    if sum(groups.values())!=len(population-registry):
        raise CoverageError("REGISTRY_EXPANSION_PARTITION_MISMATCH")
    return {"observed_nonmail_amea":len(population),"registry_amea":len(registry),
            "registry_amea_in_population":len(population & registry),
            "registry_amea_outside_population":len(registry-population),
            "outside_registry_amea":len(population-registry),"candidate_partition":dict(groups),
            "reference_coverage":dict(references),"source_coverage":dict(source_counts),
            "quote_reference_counts":dict(counts),"distinct_exact_opportunity_refs":len(exact_opp),
            "exact_document_quote_candidate_triples":len(document_triples),
            "status":"CANDIDATE_REFERENCES_ONLY_NOT_AUTHORIZED_FOR_WRITES","business_writes":0}


def read_sources(session,specs=SOURCES):
    # Reuse existing authorized GET-only reader. Prove bounds against actual
    # grid metadata first; a sparse tab cannot silently exceed a fixed limit.
    from sales_metrics_sync import CSS_SHEET, UNIFIED_SHEET, req_sheet
    books = {"CSS":CSS_SHEET, "UNIFIED":UNIFIED_SHEET}
    catalogs = {}
    for key, ident in books.items():
        url = ("https://sheets.googleapis.com/v4/spreadsheets/"+ident+
               "?fields=spreadsheetId,sheets(properties(title,sheetId,gridProperties))")
        resp = session.get(url, timeout=45)
        if not resp.ok:
            raise CoverageError("GLOBAL_CATALOG_READ_FAILED")
        data = resp.json()
        if data.get("spreadsheetId") != ident:
            raise CoverageError("GLOBAL_CATALOG_ID_MISMATCH")
        found = {}
        for entry in data.get("sheets", []):
            prop = entry.get("properties", {})
            name = prop.get("title")
            if not isinstance(name,str) or name in found:
                raise CoverageError("GLOBAL_CATALOG_DUPLICATE_OR_INVALID")
            found[name] = prop
        catalogs[key] = found
    result = {}
    for name,(book,limit,_,schema) in specs.items():
        prop = catalogs[book].get(name)
        if prop is None:
            raise CoverageError("GLOBAL_REQUIRED_TAB_MISSING")
        grid = prop.get("gridProperties", {})
        n,w = grid.get("rowCount"),grid.get("columnCount")
        if type(n) is not int or type(w) is not int or not 1<=n<=limit or not 1<=w<=52:
            raise CoverageError("GLOBAL_SOURCE_GRID_OUT_OF_BOUNDS")
        rows = req_sheet(session,books[book],name,n)
        if len(rows)>n-1 or any(not set(schema).issubset(r) for r in rows):
            raise CoverageError("GLOBAL_SOURCE_SCHEMA_OR_ROW_BOUND")
        if not rows:
            # A header-only table is an explicit empty observation, but its
            # declared fields must still be verified, not assumed present.
            address = urllib.parse.quote("'"+name.replace("'","''")+"'!A1:AZ1",safe="")
            resp = session.get("https://sheets.googleapis.com/v4/spreadsheets/"+
                               books[book]+"/values/"+address,timeout=45)
            if not resp.ok:
                raise CoverageError("GLOBAL_EMPTY_TAB_HEADER_READ_FAILED")
            matrix = resp.json().get("values") or []
            if len(matrix)!=1 or not set(schema).issubset({str(v).strip() for v in matrix[0]}):
                raise CoverageError("GLOBAL_EMPTY_TAB_SCHEMA_UNVERIFIED")
        result[name] = rows
    return result


def main():
    from sales_metrics_sync import sheets_session
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-project-report", default="")
    args = parser.parse_args()
    if args.private_project_report and os.environ.get("GITHUB_ACTIONS"):
        raise CoverageError("GLOBAL_PRIVATE_REPORT_FORBIDDEN_IN_CI")
    started = dt.datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    combined = read_sources(sheets_session(), {**SOURCES, **REGISTRY_EVIDENCE_SPECS})
    sources = {name:combined[name] for name in SOURCES}
    evidence = {name:combined[name] for name in REGISTRY_EVIDENCE_SPECS}
    summary = coverage(sources)
    summary["registry_reference_audit"] = registry_reference_audit(sources,evidence)
    summary["project_reference_coverage"], details = project_relationships(sources)
    summary["registry_expansion_audit"] = registry_expansion_audit(sources,evidence,details)
    summary["read_started_kst"] = started
    summary["read_finished_kst"] = dt.datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    if args.private_project_report:
        private_project_report(args.private_project_report,summary,details)
    print("GLOBAL_RELATIONSHIP_COVERAGE " + json.dumps(summary,sort_keys=True))
    print("GLOBAL_RELATIONSHIP_READ_COMPLETED business_writes=0 owner_filter_applied=0")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("GLOBAL_RELATIONSHIP_READ_FAILED "+(str(exc) if isinstance(exc,CoverageError)
                                                   else type(exc).__name__),file=sys.stderr)
        sys.exit(1)
