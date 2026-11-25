#!/usr/bin/env python3
"""Read-only, owner-neutral canonical/Feishu mail relationship audit.

Keep every source identity. Only an exact QQ IMAP tuple is a record-key
crosswalk; Message-ID, participant address, subject tokens and thread links
are reference observations. No content, IDs or addresses leave aggregate logs.
"""
from collections import Counter, defaultdict
from email.utils import getaddresses
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
from zoneinfo import ZoneInfo

from global_relationship_coverage import FORMATS, keys, value, project_relationships

TAB = "Canonical Mail Ledger"
CANONICAL_HEADER = [
    "canonical_key","source_table","source_row","legacy_uid","imap_folder",
    "imap_uid","uidvalidity","message_id","received_at","from_name","from_email",
    "recipient_to","cc","reply_to","subject","attachments","attachment_count",
    "amea_numbers","h_project_numbers","sam_numbers","direction","fetched_at_utc",
    "in_reply_to","references","migration_state","owner_verification","invoice_numbers",
]
BASE = "IpMkbUD0vaFqtYs93a3csXtdn1b"
SMOKE = "__QQ_FEISHU_SMOKE_V1__"
QQ = "QQ Mail Intake"
CRM = "CRM Filtered Mail Intake"
IDENTITY = "Mail Identity 2026"
PO = "Contract PO Tracker"
SIF = "SIF Evidence Tracker"
MAIL_FIELDS = ("Mail Key","Message ID","Folder","Direction","Received At","From","To",
               "CC","Subject","AMEA","H Project","In Reply To")
TABLE_FIELDS = {
    QQ: MAIL_FIELDS,
    CRM: MAIL_FIELDS,
    IDENTITY: ("Mail Key","Project ID","Project Link","Contact ID","Relationship Status","Review State"),
    PO: ("Project ID","Contract Source","Contract Mail Key","PO Notice Source","PO Mail Key",
         "Downstream Source","Downstream Mail Key"),
    SIF: ("Project ID","SIF Source","SIF Mail Key"),
}
REFERENCE_FIELDS = {"AMEA":"amea_numbers","H":"h_project_numbers","SAM":"sam_numbers","CMS":"invoice_numbers"}
SUBJECT_KINDS = ("AMEA","H","X_PROJECT","SAM","QID")
SOURCE_CODES = {"All Emails":"LEGACY","CSS Git Ingest":"STAGING"}


class MailAuditError(RuntimeError):
    pass


def canonical_key(row):
    # Do not normalize folder, UIDVALIDITY or UID when deriving the hash.
    k = row.get("canonical_key","")
    source = row.get("source_table","")
    if not isinstance(k,str) or not k or k != k.strip():
        raise MailAuditError("MAIL_CANONICAL_KEY_INVALID")
    if k.startswith("imap:"):
        folder = row.get("imap_folder","")
        uv, uid = row.get("uidvalidity",""), row.get("imap_uid","")
        if (not folder or "|" in folder or not re.fullmatch(r"\d+",uv)
                or not re.fullmatch(r"\d+",uid) or k != "imap:"+folder+"|"+uv+"|"+uid
                or source != "CSS Git Ingest"):
            raise MailAuditError("MAIL_CANONICAL_TUPLE_MISMATCH")
        return k, hashlib.sha256(k[5:].encode("utf-8")).hexdigest()
    if source == "All Emails" and re.fullmatch(r"legacy:All Emails:\d+",k):
        return k, None
    raise MailAuditError("MAIL_CANONICAL_SOURCE_KEY_REVIEW")


def msgid(raw):
    # Exact observed text; no case folding, substring or subject-based merge.
    s = str(raw or "").strip()
    return s if re.fullmatch(r"<[^<>\s]+@[^<>\s]+>",s) else ""


def subject_refs(subject):
    # An explicit token is a reference, not a confirmed project assignment.
    # Boundaries prevent truncating a suffixed or malformed identifier.
    text = str(subject or "").upper()
    result = defaultdict(set)
    for kind in SUBJECT_KINDS:
        pattern = r"(?<![A-Z0-9_-])(?:" + FORMATS[kind] + r")(?![A-Z0-9_-])"
        result[kind].update(re.findall(pattern,text))
    # A bare 10-15 digit number may be a telephone or other identifier.
    result["CMS"].update(re.findall(r"\b(?:CMS(?:\s+INVOICE)?|INVOICE)\s*(?:NO\.?|NUMBER|#|:)?\s*[:#]?\s*(\d{10,15})(?![\d-])",text))
    return result


def structured_refs(row, fields):
    out = {}
    review = Counter()
    for kind,col in fields.items():
        tokens,state = keys(value(row,col),kind+"*")
        out[kind] = {ident for _,ident in tokens}
        if state in ("FORMAT_REVIEW","PARTIAL_FORMAT_REVIEW"):
            review[kind] += 1
    return out,review


def addresses(raw):
    return {a.strip().lower() for _,a in getaddresses([str(raw or "")])
            if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",a.strip())}


def customer_refs(sources):
    contact,lead = defaultdict(set),defaultdict(set)
    for name in ("SFDC Email Leads Raw","SFDC Email Quotation Raw","SFDC Quote Export",
                 "SFDC Raw - Contact"):
        for row in sources[name]:
            addr = addresses(value(row,"Email"))
            for col,kind,index in (("Contact ID","CONTACT_OBJECT",contact),("Lead ID","LEAD_OBJECT",lead)):
                # Lead ID is only a CRM object ID in the lead report.
                if kind=="LEAD_OBJECT" and name!="SFDC Email Leads Raw":
                    continue
                token,_ = keys(value(row,col),kind)
                if len(addr)==1 and len(token)==1:
                    index[next(iter(addr))].add(next(iter(token))[1])
    return contact,lead


def keyed(rows, key, allow_smoke=False):
    out = {}
    for row in rows:
        k = value(row,key)
        if allow_smoke and k==SMOKE:
            continue
        if not re.fullmatch(r"[0-9a-f]{64}",k) or k in out:
            raise MailAuditError("MAIL_FEISHU_KEY_INVALID_OR_DUPLICATE")
        out[k]=row
    return out


def reference_metrics(rows, canonical, contact_index, lead_index):
    counts = Counter()
    distinct = defaultdict(set)
    field_review = Counter()
    parent_tokens = set()
    mids = defaultdict(set)
    for key,row in rows.items():
        mid = msgid(row.get("message_id" if canonical else "Message ID"))
        if mid:
            mids[mid].add(key)
        else:
            counts["MESSAGE_ID_NOT_VALID_OR_EMPTY"] += 1
        structured,review = structured_refs(row,REFERENCE_FIELDS if canonical else {"AMEA":"AMEA","H":"H Project"})
        field_review.update(review)
        subject = subject_refs(row.get("subject" if canonical else "Subject"))
        all_refs = {kind: structured.get(kind,set()) | subject.get(kind,set())
                    for kind in set(structured)|set(subject)}
        for kind,ids in all_refs.items():
            if ids:
                counts["ANY_"+kind] += 1
                distinct[kind].update(ids)
            if structured.get(kind):
                counts["STRUCTURED_"+kind] += 1
            if subject.get(kind):
                counts["SUBJECT_"+kind] += 1
            if structured.get(kind) and subject.get(kind) and structured[kind]!=subject[kind]:
                counts["STRUCTURED_SUBJECT_DIFFERENCE_"+kind] += 1
        if any(all_refs.values()):
            counts["ANY_IDENTIFIER_REFERENCE"] += 1
        direction = value(row,"direction" if canonical else "Direction").upper()
        sender = addresses(row.get("from_email" if canonical else "From"))
        recipients = addresses(row.get("recipient_to" if canonical else "To"))|addresses(row.get("cc" if canonical else "CC"))
        people = sender if direction=="INBOUND" else recipients if direction=="OUTBOUND" else set()
        contacts = set().union(*(contact_index[a] for a in people)) if people else set()
        leads = set().union(*(lead_index[a] for a in people)) if people else set()
        for name,ids in (("CONTACT_EMAIL_REFERENCE",contacts),("LEAD_EMAIL_REFERENCE",leads)):
            if ids:
                counts[name] += 1
                counts[name+("_ONE" if len(ids)==1 else "_MULTIPLE")] += 1
        parent = msgid(row.get("in_reply_to" if canonical else "In Reply To"))
        if parent:
            parent_tokens.add((key,parent))
            counts["THREAD_PARENT_REFERENCE"] += 1
    for key,parent in parent_tokens:
        candidates=mids.get(parent,set())-{key}
        counts["THREAD_PARENT_"+("ONE_CANDIDATE" if len(candidates)==1 else
                                  "MULTIPLE_CANDIDATES" if candidates else "NOT_IN_THIS_SOURCE")] += 1
    return ({"rows":len(rows),"reference_rows":dict(counts),
             "distinct_references":{k:len(v) for k,v in distinct.items()},
             "structured_format_review_rows":dict(field_review),
             "duplicate_message_id_groups":sum(len(v)>1 for v in mids.values())},distinct,mids)


def literal_coverage(tokens, observed):
    if not tokens:
        return "NO_DIRECT_TOKEN"
    overlap = tokens & observed
    return ("ALL_OBSERVED" if overlap == tokens else
            "PARTIAL_OBSERVED" if overlap else "NONE_OBSERVED")


def unmatched_project_reference_metrics(canonical, qq, identities, tuple_keys, projects):
    """Explain existing PROJECT_ID_UNMATCHED rows without reassigning them.

    Canonical membership is source observation, not independent evidence.
    A distinct keyed record excludes the same QQ tuple and any known equal
    Message-ID, but still does not prove a distinct real-world message.
    No inference from a name, sender, body, or untyped number. Never write.
    """
    known = {r["amea"] for r in projects}
    h_nonmail = defaultdict(set)
    for r in projects:
        for h in r["refs"].get("H", {}):
            h_nonmail[re.sub(r"-B\d+$", "", h)].add(r["amea"])
    canonical_by = {"AMEA":defaultdict(set), "H":defaultdict(set)}
    legacy_amea = set()
    canonical_h_amea = defaultdict(set)
    mids = {}
    for k,row in canonical.items():
        mids[k] = msgid(row.get("message_id"))
        ar, ast = keys(value(row, "amea_numbers"), "AMEA*")
        hr, hst = keys(value(row, "h_project_numbers"), "H*")
        a, h = {x for _,x in ar}, {x for _,x in hr}
        for kind, ids in (("AMEA",a),("H",h)):
            for ident in ids:
                canonical_by[kind][ident].add(k)
        if row.get("source_table") == "All Emails":
            legacy_amea.update(a)
        # Same-row co-observation is a candidate only. Do not cross-join
        # several AMEA to H, and never promote partially malformed cells.
        if ast == hst == "OBSERVED" and len(a)==1:
            for ident in h:
                canonical_h_amea[ident].update(a)

    out = {"population":Counter(), "nonmail_reference_state":Counter(),
           "canonical_amea_literal":Counter(), "canonical_h_literal":Counter(),
           "canonical_any_reference":Counter(), "legacy_amea_reference":Counter(),
           "canonical_h_amea_candidates":Counter(), "other_canonical_record":Counter(),
           "nonmail_and_canonical_reference":Counter()}
    for key, identity in identities.items():
        if value(identity,"Project Link") != "PROJECT_ID_UNMATCHED":
            out["population"]["OTHER_IDENTITY_STATE_NOT_ASSESSED"] += 1
            continue
        out["population"]["UNMATCHED_PROJECT_ID"] += 1
        row = qq.get(key)
        if row is None:
            out["population"]["SOURCE_QQ_NOT_OBSERVED"] += 1
            continue
        out["population"]["SOURCE_QQ_PRESENT"] += 1
        structured, review = structured_refs(row, {"AMEA":"AMEA","H":"H Project"})
        subject = subject_refs(row.get("Subject"))
        a = structured["AMEA"] | subject["AMEA"]
        h = structured["H"] | subject["H"]
        direct = a & known
        h_candidates = set().union(*(h_nonmail.get(re.sub(r"-B\d+$","",v),set())
                                     for v in h)) if h else set()
        candidates = direct | h_candidates
        # Match the operational gap categories, but keep them explicitly
        # observational. An unmatched H or malformed field is tracked below;
        # a direct AMEA does not certify every other identifier on the mail.
        if len(a)==1 and a==direct and h_candidates <= direct:
            nonmail = "DIRECT_AMEA_OBSERVED_NONMAIL"
        elif len(candidates)>1:
            nonmail = "MULTIPLE_KNOWN_CANDIDATES"
        elif direct and a-direct:
            nonmail = "PARTIAL_AMEA_CANDIDATE"
        elif not a and len(h_candidates)==1:
            nonmail = "H_ROOT_ONE_CANDIDATE"
        elif candidates:
            nonmail = "OTHER_REVIEW_CANDIDATE"
        elif a or h:
            nonmail = "NO_NONMAIL_MATCH"
        else:
            nonmail = "NO_STRICT_TOKEN"
        out["nonmail_reference_state"][nonmail] += 1
        if review:
            out["population"]["STRUCTURED_FORMAT_REVIEW"] += 1
        if len(a)>1:
            out["population"]["MULTIPLE_LITERAL_AMEA"] += 1
        if any(not h_nonmail.get(re.sub(r"-B\d+$","",v)) for v in h):
            out["population"]["H_NOT_OBSERVED_NONMAIL"] += 1
        found_a = a & canonical_by["AMEA"].keys()
        found_h = h & canonical_by["H"].keys()
        out["canonical_amea_literal"][literal_coverage(a,found_a)] += 1
        out["canonical_h_literal"][literal_coverage(h,found_h)] += 1
        out["canonical_any_reference"][
            "AMEA_AND_H_OBSERVED" if found_a and found_h else
            "AMEA_ONLY_OBSERVED" if found_a else
            "H_ONLY_OBSERVED" if found_h else "NO_STRUCTURED_CANONICAL_REFERENCE"] += 1
        out["legacy_amea_reference"][
            "AT_LEAST_ONE_AMEA_IN_LEGACY" if a & legacy_amea else "NO_AMEA_IN_LEGACY"] += 1
        hc = set().union(*(canonical_h_amea.get(v,set()) for v in h)) if h else set()
        out["canonical_h_amea_candidates"][
            "ONE_COOBSERVED_AMEA_CANDIDATE" if len(hc)==1 else
            "MULTIPLE_COOBSERVED_AMEA_CANDIDATES" if hc else "NO_COOBSERVED_AMEA"] += 1
        out["nonmail_and_canonical_reference"][
            "BOTH" if candidates and (found_a or found_h) else
            "NONMAIL_ONLY" if candidates else
            "CANONICAL_ONLY" if found_a or found_h else "NEITHER"] += 1
        same_key = tuple_keys.get(key)
        mid = msgid(row.get("Message ID"))
        refs = [(kind,ident) for kind,ids in (("AMEA",found_a),("H",found_h)) for ident in ids]
        other = any(k != same_key and (not mid or mids[k]!=mid)
                    for kind,ident in refs for k in canonical_by[kind][ident])
        out["other_canonical_record"][
            "OTHER_KEY_WITHOUT_KNOWN_SAME_MESSAGE_ID" if other else
            "ONLY_SAME_KEY_OR_KNOWN_SAME_MESSAGE_ID" if refs else
            "NO_CANONICAL_REFERENCE"] += 1

    assessed = out["population"]["SOURCE_QQ_PRESENT"]
    if (assessed + out["population"]["SOURCE_QQ_NOT_OBSERVED"] !=
            out["population"]["UNMATCHED_PROJECT_ID"]):
        raise MailAuditError("MAIL_GAP_POPULATION_MISMATCH")
    for axis, counts in out.items():
        if axis!="population" and sum(counts.values())!=assessed:
            raise MailAuditError("MAIL_GAP_AXIS_COUNT_MISMATCH")
    return {axis:dict(counts) for axis,counts in out.items()}


def mail_only_reference_audit(canonical,qq,crm,tuple_keys,projects,observed_amea):
    """Partition all mail-only AMEA by literal, same-record evidence.

    Exact QQ tuple crosswalks share a record-key observation; Message-ID is
    never an identity join. No cross-product of multi-AMEA rows. A numeric
    invoice label or structured invoice field is not a CMS crosswalk.
    """
    known={r["amea"] for r in projects}
    expected=set(observed_amea)-known
    members={}
    records=[]
    key_refs=defaultdict(set)
    typed_parents=defaultdict(set)

    def add_parent(kind,ident,pid):
        typed_parents[(kind,ident)].add(pid)
        if kind=="H":
            typed_parents[("H_ROOT",re.sub(r"-B\d+$","",ident))].add(pid)

    for r in projects:
        for kind,ids in r["refs"].items():
            mapped={"LIFECYCLE_X":"X_PROJECT","FINANCE_X":"X_PROJECT",
                    "CMS":"EXPLICIT_CMS_NUMBER"}.get(kind,kind)
            if mapped in {"H","SAM","X_PROJECT","QID","EXPLICIT_CMS_NUMBER"}:
                for ident in ids:
                    add_parent(mapped,ident,r["amea"])

    def collect(pool,canonical_source,source_label):
        for key,row in pool.items():
            source=SOURCE_CODES[row["source_table"]] if canonical_source else source_label
            if canonical_source:
                identity=("CANONICAL",key)
            elif source==QQ and key in tuple_keys:
                identity=("CANONICAL",tuple_keys[key])
            else:
                identity=(source,key)
            a_col="amea_numbers" if canonical_source else "AMEA"
            h_col="h_project_numbers" if canonical_source else "H Project"
            subj=value(row,"subject" if canonical_source else "Subject")
            observed=subject_refs(subj)
            a_tokens,a_state=keys(value(row,a_col),"AMEA*")
            structured_a={ident for _,ident in a_tokens}
            ids=structured_a|observed["AMEA"]
            if not ids:
                continue
            key_refs[identity].add(frozenset(ids))
            clean={}
            review=set()
            for kind,col in (("H",h_col),("SAM","sam_numbers" if canonical_source else "")):
                tokens,state=keys(value(row,col),kind+"*") if col else (set(),"EMPTY")
                structured={ident for _,ident in tokens}
                subject=observed[kind]
                if state not in ("EMPTY","OBSERVED") or (structured and subject and structured!=subject):
                    review.add(kind)
                elif structured or subject:
                    clean[kind]=structured|subject
            for kind in ("X_PROJECT","QID"):
                if observed[kind]:
                    clean[kind]=observed[kind]
            # Explicit CMS labels and generic invoice number labels remain
            # separate typed observations; never promote a bare number.
            label=r"\s*(?:NO\.?|NUMBER|#|:)?\s*[:#]?\s*(\d{10,15})(?![\d-])"
            cms=set(re.findall(r"\bCMS(?:\s+INVOICE)?"+label,subj.upper()))
            invoice=set(re.findall(r"\bINVOICE"+label,subj.upper()))-cms
            if cms:
                clean["EXPLICIT_CMS_NUMBER"]=cms
            if invoice:
                clean["INVOICE_LABELLED_NUMBER"]=invoice
            if canonical_source:
                num,state=keys(value(row,"invoice_numbers"),"CMS*")
                if state not in ("EMPTY","OBSERVED"):
                    review.add("STRUCTURED_INVOICE_NUMBER")
                elif num:
                    clean["STRUCTURED_INVOICE_NUMBER"]={ident for _,ident in num}
            date=value(row,"received_at" if canonical_source else "Received At")
            day=None
            if re.match(r"^\d{4}-\d{2}-\d{2}(?:$|[ T])",date):
                try:
                    day=dt.date.fromisoformat(date[:10])
                except ValueError:
                    pass
            records.append((identity,source,ids,structured_a,a_state,clean,review,day))

    collect(canonical,True,"")
    collect(qq,False,QQ)
    collect(crm,False,CRM)
    conflicting_keys={k for k,sets in key_refs.items() if len(sets)>1}
    for identity,source,ids,structured_a,a_state,clean,review,day in records:
        singleton=(len(ids)==1 and a_state in ("EMPTY","OBSERVED")
                   and identity not in conflicting_keys)
        if singleton:
            pid=next(iter(ids))
            for kind,refs in clean.items():
                if kind in {"H","SAM","X_PROJECT","QID","EXPLICIT_CMS_NUMBER"}:
                    for ident in refs:
                        add_parent(kind,ident,pid)
        for pid in ids & expected:
            m=members.setdefault(pid,{"rows":0,"keys":set(),"clean_keys":set(),
                "sources":set(),"refs":defaultdict(set),"flags":set(),"latest":None})
            m["rows"]+=1
            m["keys"].add(identity)
            m["sources"].add(source)
            m["flags"].add("STRUCTURED_AMEA_REFERENCE" if pid in structured_a else "SUBJECT_ONLY_AMEA_ON_ROW")
            if len(ids)>1:
                m["flags"].add("MULTIPLE_AMEA_ROW_REVIEW")
            if a_state not in ("EMPTY","OBSERVED"):
                m["flags"].add("AMEA_FORMAT_REVIEW")
            if identity in conflicting_keys:
                m["flags"].add("EXACT_TUPLE_AMEA_DIFFERENCE_REVIEW")
            if review:
                m["flags"].add("RELATED_FIELD_REVIEW")
            if singleton:
                m["clean_keys"].add(identity)
                for kind,refs in clean.items():
                    m["refs"][kind].update(refs)
            if day is not None:
                m["latest"]=max(m["latest"] or day,day)

    if set(members)!=expected:
        raise MailAuditError("MAIL_ONLY_POPULATION_MISMATCH")
    partition=Counter()
    flags=Counter()
    source_counts=Counter()
    surface_counts=Counter()
    reference_counts=Counter()
    latest_year=Counter()
    distinct=defaultdict(set)
    for pid,m in members.items():
        refs=m["refs"]
        if refs.get("X_PROJECT"):
            state="EXACT_X_LITERAL_COOBSERVATION"
        elif refs.get("H") or refs.get("SAM"):
            state="H_OR_SAM_LITERAL_COOBSERVATION"
        elif refs.get("QID"):
            state="QID_LITERAL_COOBSERVATION"
        elif any(refs.get(k) for k in ("EXPLICIT_CMS_NUMBER","INVOICE_LABELLED_NUMBER","STRUCTURED_INVOICE_NUMBER")):
            state="INVOICE_NUMBER_REFERENCE_ONLY"
        elif m["clean_keys"]:
            state="SINGLE_AMEA_NO_OTHER_CLEAN_REFERENCE"
        else:
            state="AMBIGUOUS_OR_FORMAT_REVIEW_ONLY"
        partition[state]+=1
        flags.update(m["flags"])
        if m["clean_keys"]:
            flags["HAS_CLEAN_SINGLETON_AMEA_RECORD_KEY"]+=1
        if len(m["clean_keys"])>1:
            flags["MULTIPLE_SINGLETON_RECORD_KEYS_NOT_INDEPENDENCE_PROOF"]+=1
        if any(len(typed_parents.get((kind,ident),set())-{pid})>0
               for kind,vals in refs.items() for ident in vals):
            flags["OTHER_AMEA_TYPED_LITERAL_REVIEW"]+=1
        if any(typed_parents.get(("H_ROOT",re.sub(r"-B\d+$","",h)),set())-{pid}
               for h in refs.get("H",set())):
            flags["OTHER_AMEA_H_ROOT_REVIEW"]+=1
        if refs.get("H") and refs.get("SAM"):
            flags["HAS_BOTH_H_AND_SAM_NO_PAIR_INFERRED"]+=1
        source_counts.update(m["sources"])
        surface_counts[str(len(m["sources"]))]+=1
        for kind,vals in refs.items():
            if vals:
                reference_counts[kind]+=1
                distinct[kind].update(vals)
        latest_year[str(m["latest"].year) if m["latest"] else "UNKNOWN"]+=1
    if sum(partition.values())!=len(expected):
        raise MailAuditError("MAIL_ONLY_PARTITION_MISMATCH")
    return {"mail_only_amea":len(expected),"candidate_partition":dict(partition),
            "source_population":dict(source_counts),"source_surfaces_per_amea":dict(surface_counts),
            "amea_with_typed_coobservations":dict(reference_counts),
            "distinct_typed_coobserved_references":{k:len(v) for k,v in distinct.items()},
            "review_and_evidence_flags":dict(flags),
            "latest_parseable_mail_date_year_counts":dict(latest_year),
            "same_row_observation_rule":"SINGLETON_VALID_AMEA_NO_EXACT_TUPLE_CONFLICT",
            "message_id_identity_merge":"NOT_PERFORMED",
            "invoice_number_cms_crosswalk":"NOT_INFERRED",
            "h_sam_pair_assignment":"NOT_INFERRED",
            "owner_payment_delivery_certification":"NOT_ATTESTED",
            "business_writes":0}


def audit(canonical_rows,tables,sources):
    canonical, tuple_keys = {},{}
    source_counts = Counter()
    for row in canonical_rows:
        k,h = canonical_key(row)
        if k in canonical or (h and h in tuple_keys):
            raise MailAuditError("MAIL_CANONICAL_DUPLICATE")
        canonical[k]=row
        source_counts[SOURCE_CODES[row["source_table"]]]+=1
        if h:
            tuple_keys[h]=k
    qq = keyed(tables[QQ],"Mail Key",True)
    crm = keyed(tables[CRM],"Mail Key",True)
    identities=keyed(tables[IDENTITY],"Mail Key")
    contact,lead=customer_refs(sources)
    cm,cn,mid_c=reference_metrics(canonical,True,contact,lead)
    qm,qn,mid_q=reference_metrics(qq,False,contact,lead)
    rm,rn,mid_r=reference_metrics(crm,False,contact,lead)
    cross=Counter()
    for h,row in qq.items():
        mid=msgid(row.get("Message ID"))
        if h in tuple_keys:
            other=msgid(canonical[tuple_keys[h]].get("message_id"))
            cross["EXACT_IMAP_TUPLE_KEY"]+=1
            cross[("EXACT_KEY_MESSAGE_ID_MATCH" if mid and other and mid==other else
                   "EXACT_KEY_MESSAGE_ID_CONFLICT" if mid and other else
                   "EXACT_KEY_MESSAGE_ID_UNAVAILABLE")]+=1
        else:
            candidates=mid_c.get(mid,set()) if mid else set()
            cross[("MESSAGE_ID_ONE_CANDIDATE_ONLY" if len(candidates)==1 else
                   "MESSAGE_ID_MULTIPLE_CANDIDATES_ONLY" if candidates else
                   "NO_CANONICAL_KEY_OR_MESSAGE_ID_OBSERVED")]+=1
    crm_cross=Counter()
    for row in crm.values():
        mid=msgid(row.get("Message ID"))
        n=len(mid_c.get(mid,set())) if mid else 0
        crm_cross["MESSAGE_ID_ONE_CANDIDATE_ONLY" if n==1 else
                  "MESSAGE_ID_MULTIPLE_CANDIDATES_ONLY" if n>1 else "NO_MESSAGE_ID_MATCH_OBSERVED"]+=1
    project_summary, project_rows = project_relationships(sources)
    known={r["amea"] for r in project_rows}
    observed_amea=cn.get("AMEA",set()) | qn.get("AMEA",set()) | rn.get("AMEA",set())
    identity_metrics=Counter()
    for k,row in identities.items():
        identity_metrics["SOURCE_QQ_PRESENT" if k in qq else "SOURCE_QQ_NOT_OBSERVED"]+=1
        if value(row,"Project Link")=="PROJECT_ID_EXACT" and value(row,"Relationship Status")=="LINKED" and value(row,"Review State")!="REVIEW":
            p=value(row,"Project ID").upper()
            if re.fullmatch(FORMATS["AMEA"],p):
                identity_metrics["EXACT_PROJECT_REFERENCE_IN_EXPANDED_POPULATION" if p in known|observed_amea
                                 else "EXACT_PROJECT_REFERENCE_OUTSIDE_OBSERVED_POPULATION"]+=1
    tracker=Counter()
    for tab,fields in ((PO,(("Contract Source","Contract Mail Key"),("PO Notice Source","PO Mail Key"),
                            ("Downstream Source","Downstream Mail Key"))),(SIF,(("SIF Source","SIF Mail Key"),))):
        for row in tables[tab]:
            for source_col,key_col in fields:
                key=value(row,key_col); source=value(row,source_col).upper()
                if not key:
                    tracker[tab+"|"+key_col+"|NO_REFERENCE"]+=1
                    continue
                pool=qq if source=="CSS" else crm if source=="CRM" else None
                state=("SOURCE_UNRECOGNIZED" if pool is None else "SOURCE_KEY_OBSERVED" if key in pool
                       else "SOURCE_KEY_NOT_OBSERVED")
                tracker[tab+"|"+key_col+"|"+state]+=1
    return {"canonical":cm,"canonical_source_counts":dict(source_counts),"qq":qm,"crm":rm,
            "qq_canonical_crosswalk":dict(cross),"crm_canonical_message_id_candidates":dict(crm_cross),
            "canonical_tuple_keys_not_in_qq":len(set(tuple_keys)-set(qq)),
            "identity_projection":dict(identity_metrics),"tracker_mail_references":dict(tracker),
            "unmatched_project_reference_audit":unmatched_project_reference_metrics(
                canonical,qq,identities,tuple_keys,project_rows),
            "mail_only_reference_audit":mail_only_reference_audit(
                canonical,qq,crm,tuple_keys,project_rows,observed_amea),
            "project_reference_population":{"nonmail":len(known),"mail":len(observed_amea),
                   "intersection":len(known&observed_amea),"mail_only":len(observed_amea-known),
                   "nonmail_only":len(known-observed_amea),"union":len(known|observed_amea)},
            "business_writes":0,"owner_filter_applied":False,
            "mailbox_completeness":"NOT_ATTESTED_BY_SOURCE_PROJECTION_AUDIT",
            "payment_delivery_sif_po_certification":"NOT_ATTESTED"}


# All diagnostics are fixed phases, integer counts and HTTP status only.
# Never emit request URLs, response bodies, exceptions or cell values.
READ_PHASES={"META","HEADER","KEY_SCAN","PAYLOAD","META_RECHECK"}
RETRY_HTTP={408,429,500,502,503,504}
SPLIT_HTTP={408,413,504}
KEY_CHUNK_ROWS=10000
PAYLOAD_CHUNK_ROWS=2000
MAX_SPLIT_DEPTH=3
MIN_SPLIT_ROWS=125
MAX_RANGE_BATCHES=350


class MailSheetsReadError(MailAuditError):
    def __init__(self,phase,rows,failure,can_split=False):
        self.can_split=can_split
        super().__init__(f"MAIL_SHEETS_READ_FAILED phase={phase} rows={rows} failure={failure}")


def get_json(session,url,phase,rows=0):
    if phase not in READ_PHASES or type(rows) is not int or rows<0:
        raise MailAuditError("MAIL_READ_DIAGNOSTIC_SCOPE")
    for attempt in range(5):
        try:
            r=session.get(url,timeout=60)
        except OSError:
            # requests transport exceptions inherit OSError; never expose
            # their messages, which may contain authenticated URLs.
            error=MailSheetsReadError(phase,rows,"TRANSPORT",True)
            retry=attempt<2
        else:
            if r.ok:
                try:
                    payload=r.json()
                except ValueError:
                    raise MailSheetsReadError(phase,rows,"INVALID_JSON") from None
                if not isinstance(payload,dict):
                    raise MailSheetsReadError(phase,rows,"INVALID_JSON_SHAPE")
                return payload
            status=r.status_code
            if type(status) is not int or not 100<=status<=599:
                raise MailSheetsReadError(phase,rows,"UNKNOWN_HTTP_STATUS")
            error=MailSheetsReadError(phase,rows,"HTTP_"+str(status),status in SPLIT_HTTP)
            # Oversize requests should be split, not retried unchanged.
            # Persistent timeouts can also benefit from smaller chunks.
            retry=status in RETRY_HTTP and attempt<(2 if status in SPLIT_HTTP else 4)
        if not retry:
            raise error from None
        print(f"MAIL_SHEETS_RETRY phase={phase} rows={rows} attempt={attempt+1} "
              f"failure={str(error).rsplit('failure=',1)[-1]}",flush=True)
        time.sleep(min(30,2**(attempt+1)))
    raise MailAuditError("MAIL_SHEETS_RETRY_BOUND")


def bounded_reads(read_ranges,phase,start,end,pieces,depth=0):
    """Yield contiguous complete batches or fail; never skip a failed row."""
    ranges=[f"{a}{start}:{b}{end}" for a,b in pieces]
    try:
        matrices=read_ranges(ranges,phase,end-start+1)
    except MailSheetsReadError as exc:
        count=end-start+1
        if not exc.can_split or depth>=MAX_SPLIT_DEPTH or count<2*MIN_SPLIT_ROWS:
            raise
        mid=(start+end)//2
        print(f"MAIL_SHEETS_SPLIT phase={phase} rows={count} depth={depth+1}",flush=True)
        yield from bounded_reads(read_ranges,phase,start,mid,pieces,depth+1)
        yield from bounded_reads(read_ranges,phase,mid+1,end,pieces,depth+1)
        return
    yield start,end,matrices


def read_canonical(session,book):
    root="https://sheets.googleapis.com/v4/spreadsheets/"+book
    def meta(phase):
        obj=get_json(session,root+"?fields=spreadsheetId,sheets(properties(title,sheetId,gridProperties))",phase)
        if obj.get("spreadsheetId")!=book:
            raise MailAuditError("MAIL_CATALOG_ID_MISMATCH")
        p=[s["properties"] for s in obj.get("sheets",[]) if s["properties"].get("title")==TAB]
        if len(p)!=1:
            raise MailAuditError("MAIL_TAB_MISSING_OR_AMBIGUOUS")
        g=p[0]["gridProperties"]
        n,w=g["rowCount"],g["columnCount"]
        if type(n)!=int or not 1<=n<=250000 or w!=27:
            raise MailAuditError("MAIL_GRID_OUT_OF_BOUND_OR_SCHEMA")
        return p[0]["sheetId"],n,w
    range_batches=0
    def read_ranges(ranges,phase,rows):
        nonlocal range_batches
        range_batches+=1
        if range_batches>MAX_RANGE_BATCHES:
            raise MailAuditError("MAIL_RANGE_BATCH_BOUND")
        query=urllib.parse.urlencode([("ranges","'"+TAB+"'!"+a) for a in ranges]+
                                     [("majorDimension","ROWS"),("valueRenderOption","FORMATTED_VALUE")])
        obj=get_json(session,root+"/values:batchGet?"+query,phase,rows)
        if obj.get("spreadsheetId")!=book or len(obj.get("valueRanges",[]))!=len(ranges):
            raise MailAuditError("MAIL_BATCH_RANGE_SET_MISMATCH")
        out=[]
        for expected,item in zip(ranges,obj["valueRanges"]):
            actual=item.get("range","")
            if actual not in (TAB+"!"+expected,"'"+TAB+"'!"+expected) or item.get("majorDimension")!="ROWS":
                raise MailAuditError("MAIL_BATCH_RANGE_BINDING_MISMATCH")
            vals=item.get("values",[])
            if not isinstance(vals,list) or any(not isinstance(r,list) for r in vals):
                raise MailAuditError("MAIL_BATCH_ROW_SCHEMA")
            out.append(vals)
        return out
    initial=meta("META")
    if read_ranges(["A1:AA1"],"HEADER",1)[0]!=[CANONICAL_HEADER]:
        raise MailAuditError("MAIL_CANONICAL_SCHEMA_MISMATCH")
    # Scan the entire allocated key/source columns first. Then read only
    # necessary fields over the populated key extent; no body/attachments.
    expected={}
    seen=set()
    for first in range(2,initial[1]+1,KEY_CHUNK_ROWS):
        last=min(first+KEY_CHUNK_ROWS-1,initial[1])
        for start,end,matrices in bounded_reads(read_ranges,"KEY_SCAN",first,last,(("A","B"),)):
            matrix=matrices[0]
            if len(matrix)>end-start+1 or any(len(row)>2 for row in matrix):
                raise MailAuditError("MAIL_KEY_SCAN_ROW_BOUND")
            for i,row in enumerate(matrix,start):
                k=str(row[0]) if row else ""
                s=str(row[1]) if len(row)>1 else ""
                if not k and not s:
                    continue
                if not k or not s or k in seen:
                    raise MailAuditError("MAIL_KEY_SCAN_INVALID_OR_DUPLICATE")
                expected[i]=(k,s);seen.add(k)
    if not expected:
        raise MailAuditError("MAIL_CANONICAL_NO_KEYED_ROWS")
    print(f"MAIL_CANONICAL_KEYS_COMPLETE allocated_rows={initial[1]} keyed_rows={len(expected)} "
          f"range_batches={range_batches}",flush=True)
    result=[]
    # ranges (column start/end, zero-based header indices)
    pieces=(("A","I",0,9),("K","M",10,13),("O","O",14,15),("R","U",17,21),
            ("W","X",22,24),("AA","AA",26,27))
    extent=max(expected)
    columns=tuple((a,b) for a,b,_,_ in pieces)
    for first in range(2,extent+1,PAYLOAD_CHUNK_ROWS):
        last=min(first+PAYLOAD_CHUNK_ROWS-1,extent)
        for start,end,matrices in bounded_reads(read_ranges,"PAYLOAD",first,last,columns):
            if any(len(m)>end-start+1 for m in matrices):
                raise MailAuditError("MAIL_PAYLOAD_ROW_BOUND")
            for i in range(end-start+1):
                row={}
                for matrix,(_,_,left,right) in zip(matrices,pieces):
                    cells=matrix[i] if i<len(matrix) else []
                    if len(cells)>right-left:
                        raise MailAuditError("MAIL_PAYLOAD_COLUMN_BOUND")
                    row.update({CANONICAL_HEADER[j]:str(cells[j-left]) if j-left<len(cells) and cells[j-left] is not None else ""
                                for j in range(left,right)})
                pair=(row["canonical_key"],row["source_table"])
                if start+i not in expected:
                    if any(row.values()):
                        raise MailAuditError("MAIL_PAYLOAD_WITHOUT_KEY")
                    continue
                if pair!=expected[start+i]:
                    raise MailAuditError("MAIL_KEY_CHANGED_DURING_READ")
                result.append(row)
    if len(result)!=len(expected) or meta("META_RECHECK")!=initial:
        raise MailAuditError("MAIL_CANONICAL_READ_CHANGED")
    print(f"MAIL_CANONICAL_PAYLOAD_COMPLETE keyed_rows={len(result)} range_batches={range_batches}",flush=True)
    return result


def read_feishu():
    from qq_mail_ingest import auth, api, plain_field
    from project_health_check import strict_pages
    if os.environ.get("FEISHU_BASE_APP_TOKEN")!=BASE:
        raise MailAuditError("MAIL_REFUSE_OTHER_BASE")
    token,root=auth()
    def get_only(method,path,token,**kwargs):
        if method!="GET":
            raise MailAuditError("MAIL_WRITE_REFUSED")
        return api(method,path,token,**kwargs)
    catalog=strict_pages(get_only,token,root+"/tables","mail_audit_catalog")
    result={}
    for name,fields in TABLE_FIELDS.items():
        hits=[r for r in catalog if r.get("name")==name]
        if len(hits)!=1 or not re.fullmatch(r"tbl[A-Za-z0-9]+",str(hits[0].get("table_id",""))):
            raise MailAuditError("MAIL_TABLE_MISSING_OR_AMBIGUOUS")
        path=root+"/tables/"+hits[0]["table_id"]
        metadata=strict_pages(get_only,token,path+"/fields","mail_audit_fields")
        for field in fields:
            matches=[r for r in metadata if r.get("field_name")==field]
            if len(matches)!=1 or matches[0].get("type")!=1:
                raise MailAuditError("MAIL_FIELD_SCHEMA_UNVERIFIED")
        def selected_get(method,url,token,**kwargs):
            if method!="GET":
                raise MailAuditError("MAIL_WRITE_REFUSED")
            if url.startswith(path+"/records?"):
                url+="&"+urllib.parse.urlencode({"field_names":json.dumps(list(fields))})
            return get_only(method,url,token,**kwargs)
        records=strict_pages(selected_get,token,path+"/records","mail_audit_records",
                             max_pages=1000 if name in (QQ,CRM,IDENTITY) else 200)
        seen=set(); output=[]
        for record in records:
            rid=record.get("record_id"); raw=record.get("fields")
            if not rid or rid in seen or not isinstance(raw,dict):
                raise MailAuditError("MAIL_RECORD_ID_OR_SCHEMA")
            seen.add(rid)
            row={f:plain_field(raw.get(f)) for f in fields}
            if any(row.values()):
                output.append(row)
        result[name]=output
    return result


def main():
    from sales_metrics_sync import CSS_SHEET,sheets_session
    from global_relationship_coverage import read_sources
    started=dt.datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    session=sheets_session()
    sources=read_sources(session)
    print(f"MAIL_NONMAIL_REFERENCES_COMPLETE sources={len(sources)}",flush=True)
    canonical=read_canonical(session,CSS_SHEET)
    tables=read_feishu()
    print(f"MAIL_FEISHU_READ_COMPLETE tables={len(tables)}",flush=True)
    summary=audit(canonical,tables,sources)
    summary["read_started_kst"]=started
    summary["read_finished_kst"]=dt.datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    print("GLOBAL_MAIL_RELATIONSHIP_COVERAGE "+json.dumps(summary,sort_keys=True))
    print("GLOBAL_MAIL_RELATIONSHIP_READ_COMPLETED business_writes=0 owner_filter_applied=0")


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print("GLOBAL_MAIL_RELATIONSHIP_FAILED "+(str(exc) if isinstance(exc,MailAuditError)
                                                 else type(exc).__name__),file=sys.stderr)
        sys.exit(1)
