#!/usr/bin/env python3
"""Read-only Statement issuance pipeline reconciled with project Forecast.

One J+exact X is one billing reference. The expected issuance date is a
planning date, never an assertion that the invoice or payment has occurred.
Only source-verified Statement KRW is summed in the Statement lane; VAT
basis and owner certification remain separate. No source/chart writes.
"""
import datetime as dt
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import json
import re
import sys
import time
import urllib.parse
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
DAYS = 5
MAIL = "CSS Git Ingest"
STATEMENT = "CSS Statement Amount Extract"
INVOICE = "CSS Tax Invoice Extract"
PROJECT = "BI Project Lifecycle Overview"
MONTHLY = "BI Revenue Lifecycle Monthly"
SPECS = {
    MAIL: ("CSS", 30000, "Q", ("ingest_key","imap_uid","folder","uidvalidity","received_at",
                           "from_email","subject","direction","in_reply_to")),
    STATEMENT: ("CSS", 5000, "K", ("statement_key","project_x","statement_no","amount_krw","currency",
                                "notice_at","imap_uid","uidvalidity","validation_status","subject")),
    INVOICE: ("CSS", 5000, "L", ("invoice_number","amount_krw","attachment_filename","subject",
                              "received_at","imap_uid","validation_status")),
    PROJECT: ("UNIFIED", 5000, "X", ("Project / Sub-project","AMEA","Expected Revenue Month",
                                  "Invoice Count","Billing Classification","Estimated KRW (existing)",
                                  "Open Statement Numbers","Latest Statement Notice")),
    MONTHLY: ("UNIFIED", 1000, "Q", ("Month","Forecast KRW","Forecast Projects","Open Statement Count",
                                  "Pending Verified KRW","Snapshot KST")),
}
KEY = re.compile(r"(?<![A-Z0-9_-])J\d{3}-X\d+SC\d+-Z\d+(?![A-Z0-9_-])", re.I)
X = re.compile(r"X\d+SC\d+-Z\d+")
AMEA = re.compile(r"AMEA\d{7,}(?:-\d{1,3})?")
MONTH = re.compile(r"20\d\d-(?:0[1-9]|1[0-2])")
ISSUE = re.compile(r"^\s*❗?\ufe0f?\s*Notice:\s*Invoice Issued\s*&\s*Statement Confirmed\b",re.I)
REPLY = re.compile(r"^\s*(?:re|fw|fwd|회신|답장|전달)\s*[:：]",re.I)
FILENAME = re.compile(
    r"TAX\s+INVOICE[-_ ]+(\d{8,15})[-_ ]+(H\d{3}SC\d{5,}|H\d{5,})[-_ ]+([A-Za-z0-9]+)"
    r"[-_ ]+(AMEA\d{7,}(?:-\d{1,3})?)[-_ ]+KRW\s*([0-9]+(?:\.[0-9]{1,2})?)\.pdf",re.I)
ALLOWED = {"FILENAME_PARSED","VERIFIED_LEGACY_FILENAME","EXISTS_IN_LEGACY"}
FORECAST_STATES = {"PROJECT FORECAST","COMPLETED - STATEMENT NOT VERIFIED"}
CANCEL = re.compile(r"\b(?:cancel(?:led|ed|lation)?|void(?:ed)?|withdraw(?:n|al)?)\b",re.I)


class ReviewError(RuntimeError):
    pass


def fail(code):
    raise ReviewError("STATEMENT_FORECAST_"+code)


def val(row,key):
    x=row.get(key)
    return "" if x is None else str(x).strip()


def stamp(raw):
    try:
        t=dt.datetime.fromisoformat(raw.replace("Z","+00:00"))
        return t.astimezone(KST) if t.tzinfo is not None else None
    except (ValueError,TypeError,AttributeError,OverflowError):
        return None


def won(raw, allow_empty=False):
    raw=str(raw if raw is not None else "").strip().replace(",","").replace("₩","")
    if not raw and allow_empty:
        return None
    try:
        n=Decimal(raw)
    except InvalidOperation:
        fail("INVALID_AMOUNT")
    if not n.is_finite() or n<0 or n!=n.to_integral_value():
        fail("INVALID_AMOUNT")
    return int(n)


def statement_key(subject):
    hits={x.upper() for x in KEY.findall(subject)}
    return next(iter(hits)) if len(hits)==1 else ""


def ready(subject):
    low=subject.lower()
    return "statement" in low and ("ready for confirmation" in low or "revised statement" in low)


def valid_mail(row):
    return (val(row,"folder").upper()=="INBOX" and val(row,"direction")=="INBOUND"
            and val(row,"from_email").lower()=="css@novogene-amea.com"
            and not val(row,"in_reply_to") and not REPLY.match(val(row,"subject")))


def check_schema(source):
    if set(source)!=set(SPECS):
        fail("SOURCE_SET_INCOMPLETE")
    for tab,(_,_,_,fields) in SPECS.items():
        if any(not set(fields)<=row.keys() for row in source[tab]):
            fail("SOURCE_SCHEMA_MISMATCH")


def audit(source,as_of):
    check_schema(source)
    if as_of.tzinfo is None:
        fail("UNZONED_AS_OF")
    as_of=as_of.astimezone(KST)
    notices=defaultdict(list)
    issue_notices=defaultdict(list)
    cancellations=defaultdict(list)
    seen=set()
    review=Counter()
    for r in source[MAIL]:
        k=val(r,"ingest_key")
        if not k or k in seen:
            fail("MAIL_KEY_INVALID_OR_DUPLICATE")
        seen.add(k)
        if not valid_mail(r):
            continue
        subject=val(r,"subject")
        is_issue=bool(ISSUE.match(subject))
        is_ready=ready(subject)
        is_cancel=bool(CANCEL.search(subject))
        if not (is_ready or is_issue or is_cancel):
            continue
        j=statement_key(subject)
        t=stamp(val(r,"received_at"))
        if not j or t is None or not val(r,"imap_uid") or not val(r,"uidvalidity"):
            review["MAIL_REFERENCE_OR_TIME_REVIEW"]+=1
            continue
        if t>as_of:
            review["MAIL_AFTER_AS_OF"]+=1
            continue
        if is_issue:
            issue_notices[j].append(t)
        if is_cancel:
            cancellations[j].append(t)
        if is_ready and not is_issue and not is_cancel:
            notices[j].append((t,val(r,"imap_uid"),val(r,"uidvalidity"),
                               "revised statement" in subject.lower()))

    amounts={}
    for r in source[STATEMENT]:
        key=val(r,"statement_key").upper()
        if not KEY.fullmatch(key) or key in amounts:
            fail("STATEMENT_KEY_INVALID_OR_DUPLICATE")
        if val(r,"validation_status")!="AMOUNT_VERIFIED" or val(r,"currency")!="KRW":
            amounts[key]=None
            continue
        a=won(r.get("amount_krw"))
        t=stamp(val(r,"notice_at"))
        if (a<=0 or t is None or not val(r,"imap_uid") or not val(r,"uidvalidity")
                or val(r,"project_x").upper()!=key[5:] or val(r,"statement_no").upper()!=key[:4]
                or statement_key(val(r,"subject"))!=key or not ready(val(r,"subject"))
                or REPLY.match(val(r,"subject"))):
            fail("VERIFIED_STATEMENT_EVIDENCE_CONFLICT")
        amounts[key]=(a,t,val(r,"imap_uid"),val(r,"uidvalidity"))

    invoices=defaultdict(dict)
    invoice_identity={}
    for r in source[INVOICE]:
        n=val(r,"invoice_number")
        sub=val(r,"subject")
        if val(r,"validation_status") not in ALLOWED or not re.fullmatch(r"209126\d{6}",n) or not ISSUE.match(sub):
            continue
        f=FILENAME.search(re.sub(r"\s+"," ",val(r,"attachment_filename")))
        a=won(r.get("amount_krw"))
        t=stamp(val(r,"received_at"))
        if not f or f.group(1)!=n or won(f.group(5))!=a or a<=0 or not t or not val(r,"imap_uid"):
            fail("INVOICE_EVIDENCE_CONFLICT")
        if t>as_of:
            review["INVOICE_AFTER_AS_OF"]+=1
            continue
        k=statement_key(sub)
        if not k:
            review["INVOICE_WITHOUT_EXACT_STATEMENT_KEY"]+=1
            continue
        item=(k,a,t)
        if n in invoice_identity and invoice_identity[n]!=item:
            fail("INVOICE_IDENTITY_CONFLICT")
        invoice_identity[n]=item
        invoices[k][n]=(a,t)

    projects={}
    baseline={}
    projected=defaultdict(lambda:{"count":0,"krw":0})
    for row in source[PROJECT]:
        x=val(row,"Project / Sub-project").upper()
        if not X.fullmatch(x) or x in projects:
            fail("LIFECYCLE_X_INVALID_OR_DUPLICATE")
        projects[x]=row
        if (val(row,"Billing Classification") in FORECAST_STATES
                and not val(row,"Open Statement Numbers")
                and won(row.get("Invoice Count"),True) in (0,None)):
            raw=won(row.get("Estimated KRW (existing)"),True)
            month=val(row,"Expected Revenue Month")
            if raw and MONTH.fullmatch(month):
                baseline[x]=(month,raw)
                projected[month]["count"]+=1
                projected[month]["krw"]+=raw
            elif raw:
                review["FORECAST_AMOUNT_WITHOUT_MONTH"]+=1
            else:
                review["FORECAST_AMOUNT_UNKNOWN_OR_ZERO"]+=1

    # Keep open lifecycle keys even when the direct source notice is missing.
    lifecycle_open=set()
    for x,row in projects.items():
        for j in val(row,"Open Statement Numbers").split("|"):
            j=j.strip().upper()
            if not j:
                continue
            key=j+"-"+x
            if not KEY.fullmatch(key) or key in lifecycle_open:
                fail("LIFECYCLE_STATEMENT_KEY_INVALID_OR_DUPLICATE")
            lifecycle_open.add(key)
    for key in set(amounts)-set(notices)-set(invoices):
        review["AMOUNT_REFERENCE_WITHOUT_NOTICE_OR_INVOICE"]+=1
    rows=[]
    hold_x=set()
    active_x=set()
    expected=defaultdict(lambda:{"statement_count":0,"verified_amount_count":0,
                                 "verified_amount_krw_vat_basis_unknown":0,
                                 "amount_unknown_count":0,"due_or_past_count":0})
    keys=set(notices)|lifecycle_open
    for key in sorted(keys):
        x=key[5:]
        events=sorted(set(notices.get(key,[])))
        latest=events[-1] if events else None
        # Revisions may supersede the prior notice; the actual service clock
        # reset is unverified. Use latest explicit revision, otherwise first
        # original; do not restart the estimated SLA for duplicate notices.
        revisions=[e for e in events if e[3]]
        anchor=revisions[-1] if revisions else events[0] if events else None
        due=anchor[0].date()+dt.timedelta(days=DAYS) if anchor else None
        amount_record=amounts.get(key)
        known_amount=(amount_record[0] if amount_record and latest and
                      amount_record[1:]==latest[:3] else None)
        actual=invoices.get(key,{})
        actual_notice=issue_notices.get(key,[])
        conflict_after_issue=(latest is not None and any(t<latest[0] for _,t in actual.values()))
        cancelled=(latest is not None and any(t>=latest[0] for t in cancellations[key]))
        if actual:
            state="ISSUED_VERIFIED_REVIEW" if conflict_after_issue or cancelled or (
                known_amount is not None and sum(a for a,_ in actual.values())!=known_amount
            ) else "ISSUED_VERIFIED"
            # Even a conflicting later notice must never resurrect an
            # already-issued reference as a positive pending amount.
            hold_x.add(x)
        elif actual_notice:
            state="ISSUE_NOTICE_AMOUNT_REVIEW"
            hold_x.add(x)
        elif cancelled:
            state="CANCELLATION_REVIEW"
            hold_x.add(x)
        elif not latest:
            state="DIRECT_NOTICE_MISSING_REVIEW"
            hold_x.add(x)
        else:
            state="STATEMENT_PENDING_VERIFIED_AMOUNT" if known_amount is not None else "STATEMENT_PENDING_AMOUNT_UNKNOWN"
            hold_x.add(x)
            active_x.add(x)
            month=due.strftime("%Y-%m")
            m=expected[month]
            m["statement_count"]+=1
            if due<=as_of.date():
                m["due_or_past_count"]+=1
            if known_amount is None:
                m["amount_unknown_count"]+=1
            else:
                m["verified_amount_count"]+=1
                m["verified_amount_krw_vat_basis_unknown"]+=known_amount
        rows.append({"member_key":"STATEMENT:"+key,"statement_key":key,"x":x,
                     "amea":val(projects.get(x,{}),"AMEA"),"source_notice_count":len(events),
                     "latest_notice_kst":latest[0].isoformat() if latest else "",
                     "estimated_auto_issue_date":due.isoformat() if due else "",
                     "expected_issue_month":due.strftime("%Y-%m") if due else "",
                     "due_state":("DUE_OR_PAST_DATE" if due and due<=as_of.date() else
                                  "FUTURE" if due else "UNKNOWN"),
                     "state":state,"verified_statement_krw_vat_basis_unknown":known_amount,
                     "invoice_count":len(actual),"exact_lifecycle_x_observed":x in projects,
                     "lifecycle_open_key_observed":key in lifecycle_open,
                     "baseline_project_forecast_observed":x in baseline,
                     "revised_notice_observed":bool(revisions)})

    remaining=defaultdict(lambda:{"count":0,"krw":0})
    held=defaultdict(lambda:{"count":0,"krw":0})
    project_members=[]
    for x,(month,amount) in sorted(baseline.items()):
        group=held if x in hold_x else remaining
        group[month]["count"]+=1;group[month]["krw"]+=amount
        project_members.append({"member_key":"PROJECT_FORECAST:"+x,"x":x,"month":month,"krw_ex_tax_estimate":amount,
                                "state":"HELD_FOR_STATEMENT_OR_ISSUE_REVIEW" if x in hold_x else "GENERAL_PROJECT_FORECAST"})

    published={}
    for row in source[MONTHLY]:
        month=val(row,"Month")
        if not MONTH.fullmatch(month) or month in published:
            fail("MONTHLY_KEY_INVALID_OR_DUPLICATE")
        published[month]=row
    months={}
    for month in sorted(set(projected)|set(published)|set(expected)):
        p=published.get(month)
        original=projected[month]
        months[month]={
            "baseline_lifecycle_forecast":original,
            "published_forecast_parity":bool(p and original["count"]==won(p.get("Forecast Projects"))
                                             and original["krw"]==won(p.get("Forecast KRW"))),
            "general_forecast_after_statement_hold":remaining[month],
            "held_project_estimate_not_added_to_statement":held[month],
            "statement_expected_by_issue_month":expected[month],
            "published_open_statement_count":won(p.get("Open Statement Count")) if p else None,
        }
    summary={
        "as_of_kst":as_of.isoformat(),"auto_issue_days_assumed":DAYS,
        "statement_source_keys":len(notices),"mail_rows":len(source[MAIL]),
        "statement_states":dict(Counter(r["state"] for r in rows)),
        "pending_without_lifecycle":sum(r["state"].startswith("STATEMENT_PENDING") and
                                         not r["exact_lifecycle_x_observed"] for r in rows),
        "pending_without_open_projection":sum(r["state"].startswith("STATEMENT_PENDING") and
                                               not r["lifecycle_open_key_observed"] for r in rows),
        "active_pending_x":len(active_x),"baseline_forecast_held_x":len(set(baseline)&hold_x),
        "months":months,"source_review":dict(review),"business_writes":0,
        "statement_vat_basis":"UNKNOWN_DO_NOT_MIX_WITH_NET_REVENUE",
        "source_scope":"GLOBAL_OBSERVATIONS_NOT_OWNER_CERTIFICATION",
        "source_freshness":"NOT_ATTESTED_BY_THIS_AUDIT",
        "automatic_issuance":"EXPECTED_DATE_ONLY_NOT_CERTIFIED",
    }
    return summary,{"statement_members":rows,"project_members":project_members}


def get_json(session,url):
    for attempt in range(5):
        response=session.get(url,timeout=60)
        if response.ok:
            return response.json()
        if response.status_code not in (429,500,502,503,504) or attempt==4:
            fail("SOURCE_READ_FAILED")
        time.sleep(min(30,2**(attempt+1)))
    fail("SOURCE_READ_FAILED")


def read_sources(session):
    from sales_metrics_sync import CSS_SHEET,UNIFIED_SHEET
    books={"CSS":CSS_SHEET,"UNIFIED":UNIFIED_SHEET}
    def catalog(book):
        url="https://sheets.googleapis.com/v4/spreadsheets/"+book+"?fields=spreadsheetId,sheets(properties(title,sheetId,gridProperties))"
        data=get_json(session,url)
        if data.get("spreadsheetId")!=book:
            fail("CATALOG_ID")
        entries=[s.get("properties",{}) for s in data.get("sheets",[])]
        if len({p.get("title") for p in entries})!=len(entries):
            fail("CATALOG_DUPLICATE")
        return {p.get("title"):p for p in entries}
    initial={k:catalog(b) for k,b in books.items()}
    out={}
    for name,(book,limit,last,fields) in SPECS.items():
        p=initial[book].get(name)
        if not p:
            fail("TAB_MISSING")
        n=p["gridProperties"].get("rowCount")
        w=p["gridProperties"].get("columnCount")
        if type(n) is not int or not 1<=n<=limit or type(w) is not int or not ord(last)-64<=w<=52:
            fail("GRID_BOUND")
        root="https://sheets.googleapis.com/v4/spreadsheets/"+books[book]+"/values/"
        def read(a,b):
            rg="'"+name+"'!A"+str(a)+":"+last+str(b)
            obj=get_json(session,root+urllib.parse.quote(rg,safe="")+"?valueRenderOption=UNFORMATTED_VALUE")
            vals=obj.get("values",[])
            if not isinstance(vals,list) or len(vals)>b-a+1 or any(not isinstance(r,list) or len(r)>ord(last)-64 for r in vals):
                fail("PAYLOAD_BOUND")
            return vals
        h=read(1,1)
        if len(h)!=1 or not set(fields)<=set(h[0]) or len(h[0])!=len(set(h[0])):
            fail("HEADER_SCHEMA")
        out[name]=[]
        for a in range(2,n+1,2000):
            for row in read(a,min(a+1999,n)):
                if any(str(v or "").strip() for v in row):
                    out[name].append({key:row[i] if i<len(row) else "" for i,key in enumerate(h[0]) if key in fields})
    # Metadata is not a transactional snapshot; detect grid/identity drift.
    after={k:catalog(b) for k,b in books.items()}
    if any(after[b].get(n)!=initial[b].get(n) for n,(b,*_) in SPECS.items()):
        fail("CATALOG_CHANGED")
    return out


def main():
    from sales_metrics_sync import sheets_session
    started=dt.datetime.now(KST)
    source=read_sources(sheets_session())
    summary,_=audit(source,dt.datetime.now(KST))
    summary["read_started_kst"]=started.isoformat()
    print("STATEMENT_FORECAST_AUDIT "+json.dumps(summary,sort_keys=True))
    print("STATEMENT_FORECAST_READ_ONLY business_writes=0")


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print("STATEMENT_FORECAST_FAILED "+(str(exc) if isinstance(exc,ReviewError) else type(exc).__name__),file=sys.stderr)
        sys.exit(1)
