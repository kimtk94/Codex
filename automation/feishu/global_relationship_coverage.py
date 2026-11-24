#!/usr/bin/env python3
"""Read-only global source identifier coverage, independent of owner and Board.

Observation of identifiers in a source row is not certification of a business
relationship, current status, delivery, invoice issue or payment. No writes.
"""
from collections import Counter, defaultdict
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
        "amea_quote_id":"QUOTE_BUSINESS", "invoice_number":"CMS", "project_id":"PROJECT_ANY"}),
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


def read_sources(session):
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
    for name,(book,limit,_,schema) in SOURCES.items():
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
    started = dt.datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    summary = coverage(read_sources(sheets_session()))
    summary["read_started_kst"] = started
    summary["read_finished_kst"] = dt.datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    print("GLOBAL_RELATIONSHIP_COVERAGE " + json.dumps(summary,sort_keys=True))
    print("GLOBAL_RELATIONSHIP_READ_COMPLETED business_writes=0 owner_filter_applied=0")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("GLOBAL_RELATIONSHIP_READ_FAILED "+(str(exc) if isinstance(exc,CoverageError)
                                                   else type(exc).__name__),file=sys.stderr)
        sys.exit(1)
