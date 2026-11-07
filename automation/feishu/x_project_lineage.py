#!/usr/bin/env python3
"""Source-backed AMEA–H–X–SAM lineage and X-level invoice linkage.

All data are evidence-labelled, never cross-join ambiguous projects or samples.
No calls, writes, or secrets in this module.
"""
import collections
import re
from decimal import Decimal, InvalidOperation

AMEA_RE=re.compile(r"^AMEA\d{7,}(?:-\d{1,3})?$")
H_RE=re.compile(r"H\d+SC\d+(?:-B\d+)?")
X_RE=re.compile(r"^X\d+SC\d+(?:-Z\d+)?$")
SAM_RE=re.compile(r"(?:SAM\d{11}(?:-[A-Z0-9_]+)?|Z\d{9})")
CMS_RE=re.compile(r"^\d{10,15}$")
MINE="KIM TAEHOON"

LINK_SCHEMAS={
  "AMEA H X SAM Link": [
    ("Source Key",1),("Link Type",1),("AMEA",1),("H Contract",1),
    ("X Project",1),("SAM",1),("Link State",1),("Evidence",1),("Last Sync KST",1)
  ],
  "X Project Registry": [
    ("Source Key",1),("X Project",1),("X Base",1),("H Contract",1),
    ("AMEA",1),("AMEA Link State",1),("Sales",1),("Owner Scope",1),
    ("Contract Name",1),("Staging Number",1),("Staging Name",1),
    ("Project Status",1),("Progression Details",1),("Current Stage",1),
    ("Progress Phase",1),("Progress Bar",1),("Remaining TAT Days",2),
    ("SAM Linked",2),("SAM Review",2),("Invoice Linked",2),
    ("Invoice Gross KRW Incl VAT",2),("Outstanding KRW Verified",2),
    ("Invoice Link State",1),("Payment Followup",1),
    ("Next Action",1),("Evidence",1),("Last Sync KST",1)
  ],
  "X Invoice Ledger": [
    ("Source Key",1),("CMS Invoice",1),("X Base",1),("X Project",1),
    ("AMEA",1),("H Contract",1),("Sales",1),("Owner Scope",1),
    ("Invoice Gross KRW Incl VAT",2),("Outstanding Balance KRW",2),
    ("Receipt Match State",1),("Invoice Link State",1),
    ("Sources",1),("Next Action",1),("Evidence",1),("Last Sync KST",1)
  ],
}

def field(row,k):
    return str((row or {}).get(k) or "").strip()

def upper(row,k):
    return field(row,k).upper()

def tokens(value,pattern):
    # A token must be delimited to avoid silently inventing truncated IDs.
    found=[]
    for piece in re.split(r"[|;,\n]+",str(value or "").upper()):
        piece=piece.strip()
        if not piece:continue
        if pattern==H_RE:
            if not re.fullmatch(r"H\d+SC\d+(?:-B\d+)?",piece):
                continue
        elif not pattern.fullmatch(piece):continue
        found.append(piece)
    return set(found)

def h_root(value):
    hit=re.fullmatch(r"(H\d+SC\d+)(?:-B\d+)?",str(value).upper())
    return hit.group(1) if hit else ""

def x_base(value):
    hit=re.fullmatch(r"(X\d+SC\d+)(?:-Z\d+)?",str(value).upper())
    return hit.group(1) if hit else ""

def amount(value):
    try:
        number=Decimal(str(value or "").replace(",","").strip())
    except InvalidOperation:return None
    return number if number.is_finite() and number>=0 else None

def owner(sales):
    return "MY_VERIFIED" if str(sales or "").strip().casefold()==MINE.casefold() else (
        "OWNER_UNVERIFIED" if not str(sales or "").strip() else "OTHER_SALES"
    )

def x_phase(project_status):
    # 'Abnormal' and generic billing/forecast statuses are not a physical step.
    from project_progress_board import progress_phase
    return progress_phase(project_status)

def link_row(kind,amea="",h="",x="",sam="",state="",source=""):
    key="LINK:"+kind+":"+":".join(v for v in (amea,h,x,sam) if v)
    return {"Source Key":key,"Link Type":kind,"AMEA":amea,
            "H Contract":h,"X Project":x,"SAM":sam,
            "Link State":state,"Evidence":source}

def register(mapper,key,row):
    if key in mapper and mapper[key]!=row:
        raise ValueError("CONFLICTING_LINEAGE_RECORD")
    mapper[key]=row

def build(sources):
    css=sources.get("CSS Project Dashboard") or []
    timeline=sources.get("CSS Project Timeline") or []
    lifecycle=sources.get("BI Project Lifecycle Overview") or []
    online=sources.get("Feishu Latest Online") or []
    etax=sources.get("Feishu Latest eTax") or []
    outstanding=sources.get("Feishu Latest Outstanding") or []
    if not css or not online:raise ValueError("REQUIRED_LINEAGE_SOURCE_EMPTY")

    ah=collections.defaultdict(set)
    amsam_current=collections.defaultdict(set)
    amsam_history=collections.defaultdict(set)
    sam_owners=collections.defaultdict(set)
    for row in css:
        amea=upper(row,"project_id")
        if not AMEA_RE.fullmatch(amea):continue
        for h in tokens(field(row,"h_project_numbers"),H_RE):
            ah[amea].add(h_root(h))
        for sam in tokens(field(row,"sam_numbers"),SAM_RE):
            amsam_current[amea].add(sam)
            sam_owners[sam].add(amea)
    for row in timeline:
        amea=upper(row,"project_id")
        if not AMEA_RE.fullmatch(amea):continue
        for sam in tokens(field(row,"sam_numbers"),SAM_RE):
            amsam_history[amea].add(sam)
            sam_owners[sam].add(amea)

    h_to_amea=collections.defaultdict(set)
    links={}
    for amea, hs in ah.items():
        for h in sorted(hs):
            h_to_amea[h].add(amea)
            r=link_row("AMEA_H",amea=amea,h=h,
                       state="EXACT_CSS",source="CSS Project Dashboard h_project_numbers")
            register(links,r["Source Key"],r)

    online_by_x={}
    h_to_x=collections.defaultdict(set)
    base_to_x=collections.defaultdict(set)
    for row in online:
        x=upper(row,"Sub-Project Number")
        h=h_root(upper(row,"Contract Number"))
        if not X_RE.fullmatch(x) or not h:
            continue
        # Same X with contradictory H is a hard blocker.
        if x in online_by_x and h_root(upper(online_by_x[x],"Contract Number"))!=h:
            raise ValueError("ONLINE_X_MULTIPLE_CONTRACTS")
        if x in online_by_x and online_by_x[x]!=row:
            raise ValueError("ONLINE_X_DUPLICATE_CONFLICT")
        online_by_x[x]=row
        base_to_x[x_base(x)].add(x)
        h_to_x[h].add(x)
        r=link_row("H_X",h=h,x=x,
                   state="EXACT_FEISHU_ONLINE",
                   source="Feishu Latest Online Contract Number + Sub-Project Number")
        register(links,r["Source Key"],r)

    explicit_x=collections.defaultdict(set)
    explicit_amea=collections.defaultdict(set)
    for row in lifecycle:
        amea=upper(row,"AMEA")
        x=upper(row,"Project / Sub-project")
        if not AMEA_RE.fullmatch(amea) or not X_RE.fullmatch(x):continue
        explicit_x[x].add(amea)
        explicit_amea[amea].add(x)

    x_am={}
    for x,row in sorted(online_by_x.items()):
        h=h_root(upper(row,"Contract Number"))
        officials=explicit_x.get(x,set())
        inferred=h_to_amea.get(h,set())
        if len(officials)>1:
            chosen=""
            status="CONFLICT_MULTIPLE_AMEA"
        elif len(officials)==1:
            chosen=next(iter(officials))
            if inferred and chosen not in inferred:
                status="CONFLICT_LIFECYCLE_CSS_H"
            else:
                status="EXACT_LIFECYCLE"
        elif len(inferred)==1:
            chosen=next(iter(inferred))
            status="UNIQUE_H_CANDIDATE"
        else:
            chosen=""
            status="AMBIGUOUS_H" if len(inferred)>1 else "X_UNMATCHED"
        x_am[x]=(chosen,status)
        if chosen:
            r=link_row("AMEA_X",amea=chosen,h=h,x=x,state=status,
                       source=("BI Project Lifecycle Overview exact X" if officials
                               else "Unique H-root candidate; not officially verified"))
            register(links,r["Source Key"],r)

    # Avoid cross-pairing every SAM with every H or X. Only attach a sample
    # to a unique, *officially* linked X under its AMEA, with unshared SAM.
    sam_link_counts=collections.Counter()
    sam_review_counts=collections.Counter()
    for amea in sorted(set(amsam_current)|set(amsam_history)):
        current=amsam_current.get(amea,set())
        hist=amsam_history.get(amea,set())
        exact_x={x for x in explicit_amea.get(amea,set())
                 if x in x_am and x_am[x]==(amea,"EXACT_LIFECYCLE")}
        for sam in sorted(current|hist):
            linked_x=""
            if sam not in current:
                state="TIMELINE_ONLY_REVIEW"
            elif len(sam_owners[sam])!=1:
                state="SHARED_SAM_REVIEW"
            elif len(exact_x)==1:
                linked_x=next(iter(exact_x))
                state="EXACT_SINGLE_X_CHAIN"
                sam_link_counts[linked_x]+=1
            elif len(exact_x)>1:
                state="MULTI_X_REVIEW"
            else:
                state="X_NOT_VERIFIED"
            if state!="EXACT_SINGLE_X_CHAIN":
                for x in exact_x:
                    sam_review_counts[x]+=1
            r=link_row("AMEA_SAM",amea=amea,x=linked_x,sam=sam,state=state,
                       source=("CSS Project Dashboard SAM + BI Lifecycle X + "
                               "Feishu Online H" if linked_x
                               else "CSS Project Dashboard / Timeline; no X assignment"))
            register(links,r["Source Key"],r)

    # Invoice records are keyed by CMS invoice. They are never joined on a
    # customer name, and a parent X base with multiple -Z projects is REVIEW.
    raw_invoice=collections.defaultdict(list)
    for source,records,no_col in (
        ("ETAX",etax,"CMS Invoice Num"),
        ("OUTSTANDING",outstanding,"CMS Invoice Number")):
        for row in records:
            number=upper(row,no_col)
            if CMS_RE.fullmatch(number):
                raw_invoice[number].append((source,row))

    invoices={}
    inv_counts=collections.Counter()
    inv_total=collections.defaultdict(lambda:Decimal("0"))
    out_total=collections.defaultdict(lambda:Decimal("0"))
    inv_x_owner=collections.defaultdict(list)
    invoice_states=collections.defaultdict(set)
    for cms,records in sorted(raw_invoice.items()):
        projects={upper(r,"Project Number") for _,r in records}
        amounts={amount(field(r,"Amount" if src=="ETAX" else "Invoice Amount"))
                 for src,r in records}
        ams={upper(r,"Quotation Number") for _,r in records}
        sales={field(r,"Sales").strip().casefold() for _,r in records}
        bases={x_base(v) for v in projects}
        matches={x for base in bases for x in base_to_x.get(base,set())}
        gross=next(iter(amounts)) if len(amounts)==1 else None
        base=next(iter(bases)) if len(bases)==1 else ""
        mea=next(iter(ams)) if len(ams)==1 else ""
        sales_name=field(records[0][1],"Sales") if len(sales)==1 else ""
        scope=owner(sales_name) if len(sales)==1 and all(sales) else "OWNER_UNVERIFIED"
        if (len(projects)!=1 or len(ams)!=1 or len(amounts)!=1 or gross is None
                or len(sales)!=1 or not all(sales)):
            state="INVOICE_SOURCE_CONFLICT"
        elif len(matches)>1:
            state="MULTI_Z_REVIEW"
        elif len(matches)==0:
            state="X_NOT_IN_ONLINE"
        elif not (len(explicit_x.get(next(iter(matches)),set()))==1 and
                  mea in explicit_x.get(next(iter(matches)),set())):
            state="AMEA_X_NOT_VERIFIED"
        elif x_am[next(iter(matches))][1]!="EXACT_LIFECYCLE":
            state="AMEA_X_CONFLICT"
        else:
            state="EXACT_X_AMEA_CMS"
        x=next(iter(matches)) if state=="EXACT_X_AMEA_CMS" else ""
        if x:
            inv_counts[x]+=1
            inv_total[x]+=gross
            inv_x_owner[x].append(scope)
        balances={amount(field(r,"Balance")) for src,r in records
                  if src=="OUTSTANDING"}
        if len(balances)==1 and None not in balances:
            balance=next(iter(balances))
        else:
            balance=None
        if x and balance is not None:
            out_total[x]+=balance
        if x:
            invoice_states[x].add(
                "OPEN_OUTSTANDING" if balance is not None and balance>0
                else "BALANCE_ZERO_RECEIPT_NOT_VERIFIED" if balance==0
                else "OUTSTANDING_UNKNOWN"
            )
        invoice={
            "Source Key":"INVOICE:"+cms,
            "CMS Invoice":cms,"X Base":base,
            "X Project":x,"AMEA":mea,
            "H Contract":h_root(upper(online_by_x.get(x,{}),"Contract Number")) if x else "",
            "Sales":sales_name if len(sales)==1 else "",
            "Owner Scope":scope,
            "Receipt Match State":"NOT_VERIFIED_AT_X",
            "Invoice Link State":state,
            "Sources":"+".join(sorted({src for src,_ in records})),
            "Next Action":("Match X and AMEA manually" if not x else
                           "Follow up outstanding" if balance is not None and balance>0
                           else "Verify receipt before paid archive"),
            "Evidence":"CMS Invoice + X Base + AMEA + gross match; no PO/name inference",
        }
        if gross is not None:invoice["Invoice Gross KRW Incl VAT"]=float(gross)
        if balance is not None:invoice["Outstanding Balance KRW"]=float(balance)
        invoices[invoice["Source Key"]]=invoice

    registry={}
    for x,row in sorted(online_by_x.items()):
        amea,status=x_am[x]
        h=h_root(upper(row,"Contract Number"))
        rem=amount(field(row,"Remaining Lead Time-Calendar Days"))
        sales=field(row,"Sales")
        owner_scope=owner(sales)
        invn=inv_counts[x]
        follow="INVOICE_REVIEW" if invn==0 else (
            "OPEN_OUTSTANDING" if "OPEN_OUTSTANDING" in invoice_states[x]
            else "RECEIPT_NOT_VERIFIED"
        )
        if status!="EXACT_LIFECYCLE":
            next_action="Check AMEA↔X identity; no inferred revenue allocation"
        elif upper(row,"Project Status")=="ABNORMAL":
            next_action="Review Feishu abnormal status and progression detail"
        else:
            next_action="Confirm current physical milestone and remaining TAT"
        reg={
            "Source Key":"X:"+x,"X Project":x,"X Base":x_base(x),
            "H Contract":h,"AMEA":amea,"AMEA Link State":status,
            "Sales":sales,"Owner Scope":owner_scope,
            "Contract Name":field(row,"Contract Name"),
            "Staging Number":field(row,"Staging Number"),
            "Staging Name":field(row,"Staging Name"),
            "Project Status":field(row,"Project Status"),
            "Progression Details":field(row,"Progression Details")[:10000],
            "Current Stage":field(row,"Project Status") or "NOT_VERIFIED",
            "Progress Phase":x_phase(field(row,"Project Status")),
            "Progress Bar":"미확인",  # AMEA percentage must not be assigned to X
            "SAM Linked":sam_link_counts[x],"SAM Review":sam_review_counts[x],
            "Invoice Linked":invn,"Invoice Link State":(
                "EXACT_INVOICES" if invn else "NO_EXACT_INVOICE"),
            "Payment Followup":follow,
            "Next Action":next_action,
            "Evidence":"Feishu Latest Online exact X/H; lifecycle AMEA only when exact",
        }
        if rem is not None:reg["Remaining TAT Days"]=float(rem)
        if invn:reg["Invoice Gross KRW Incl VAT"]=float(inv_total[x])
        if x in out_total:reg["Outstanding KRW Verified"]=float(out_total[x])
        registry[reg["Source Key"]]=reg

    audit={
        "x":len(registry),"lineage":len(links),"invoice":len(invoices),
        "exact_amea_x":sum(v[1]=="EXACT_LIFECYCLE" for v in x_am.values()),
        "candidate_amea_x":sum(v[1]=="UNIQUE_H_CANDIDATE" for v in x_am.values()),
        "x_identity_review":sum(v[1] not in {"EXACT_LIFECYCLE","UNIQUE_H_CANDIDATE"}
                                for v in x_am.values()),
        "linked_sam":sum(sam_link_counts.values()),
        "sam_review":sum(r["Link State"]!="EXACT_SINGLE_X_CHAIN"
                         for r in links.values() if r["Link Type"]=="AMEA_SAM"),
        "exact_invoices":sum(v["Invoice Link State"]=="EXACT_X_AMEA_CMS"
                              for v in invoices.values()),
        "invoice_review":sum(v["Invoice Link State"]!="EXACT_X_AMEA_CMS"
                              for v in invoices.values()),
        "my_x":sum(r["Owner Scope"]=="MY_VERIFIED" for r in registry.values()),
    }
    return {"AMEA H X SAM Link":list(links.values()),
            "X Project Registry":list(registry.values()),
            "X Invoice Ledger":list(invoices.values())},audit
