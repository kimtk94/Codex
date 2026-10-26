#!/usr/bin/env python3
"""Advisory unanswered-email candidates from the QQ Mail staging ledger.

Reads existing exclusions; never replaces the manual Unanswered Emails sheet.
Headers only: missing replies outside collection window remain uncertain.
"""
import datetime as dt
import re
import os
import sys
import urllib.parse
from email.utils import getaddresses
import incremental_sync as src

OUTPUT = "Unanswered Emails Auto"
SOURCE = "CSS Git Ingest"
EXCLUDED = "Unanswered Email Exclusions"
SENDER_EXCLUDED = "Unanswered Sender Exclusions"
HEADER = ["waiting_days","received_at","from_name","subject","source_link","work_status","category","owner","from_email","exclude_reason","exclude","exclude_sender","to","cc","project_ids","reply_status","thread_subject","uid","source_row","last_checked_utc","review_status"]
MAX_READ = 100000

def table(s, tab, columns, end):
    # Bounded reads avoid request timeouts as QQ history grows.
    page_size=1000
    header=None
    result=[]
    for start in range(1,end+1,page_size):
        last=min(end,start+page_size-1)
        a1=urllib.parse.quote("'"+tab+"'!A"+str(start)+":"+columns+str(last),safe="")
        rows=src.api(s,"GET",src.endpoint("/values/"+a1)).get("values",[])
        if start==1:
            if not rows:return []
            header=[str(x).strip() for x in rows[0]]
            rows=rows[1:]
        for row in rows:
            if any(row):
                result.append(dict(zip(header,row+[""]*(len(header)-len(row)))))
        # Sheets trims trailing empty rows. A short page can still contain blank
        # interior rows, so stop only when the final requested row is absent.
        if len(rows)<last-start+1-(1 if start==1 else 0):
            break
    return result

def norm_subject(value):
    value=str(value or "").strip()
    prev=None
    while value!=prev:
        prev=value
        value=re.sub(r"^(?:re|fw|fwd|답장|전달)\s*[:：]\s*","",value,flags=re.I).strip()
    return re.sub(r"\s+"," ",value).casefold()

def addresses(value):
    return {addr.casefold() for _,addr in getaddresses([str(value or "")]) if addr}

def when(value):
    try:
        parsed=dt.datetime.fromisoformat(str(value))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=src.KST)).astimezone(dt.timezone.utc)
    except (ValueError,TypeError):return None

def truth(value):
    return str(value or "").strip().upper() in ("TRUE", "YES", "1")

def config_from_rows(rows):
    config = {"unanswered_lookback_days": 180, "action_unanswered_max_age_days": 30, "action_unanswered_min_age_days": 2}
    for row in rows:
        key = row.get("rule_key", "")
        if row.get("rule_group") == "Mail" and truth(row.get("enabled")) and key in config:
            try:
                config[key] = max(1, min(365, int(row.get("value", ""))))
            except (ValueError, TypeError):
                pass
    return config

def candidates(messages, exclusions, senders, rules=None, sender_rules=None):
    config = config_from_rows(rules or [])
    now_utc = dt.datetime.now(dt.timezone.utc)
    today = now_utc.astimezone(src.KST).date()
    previous_thread_exclusions = []
    auto_exclusions=[]
    for rule in (sender_rules or []):
        if not truth(rule.get("active")):continue
        if rule.get("default_action","").upper() not in ("IGNORE","ARCHIVE","SALESFORCE_PIPELINE"):continue
        p=str(rule.get("sender_pattern","")).strip().casefold()
        kind=str(rule.get("match_type","")).strip().casefold()
        if p:auto_exclusions.append((p,kind))
    own_addresses=addresses(os.environ.get('CSS_QQ_MAIL_ADDRESS',''))
    banned_ids=set()
    for r in exclusions:
        if truth(r.get("restore")): continue
        if r.get("uid"): banned_ids.add(r["uid"].strip().casefold())
        cutoff = when(r.get("excluded_through_at")) or when(r.get("excluded_at"))
        if cutoff and r.get("from_email") and (r.get("thread_subject") or r.get("subject")):
            previous_thread_exclusions.append((addresses(r["from_email"]), norm_subject(r.get("thread_subject") or r.get("subject")), cutoff))
    banned_sender=[]
    for r in senders:
        if truth(r.get("restore")):continue
        pat=str(r.get("sender_pattern","")).strip().casefold()
        typ=str(r.get("match_type","")).strip().casefold()
        if pat and typ in ("exact","domain","contains"):banned_sender.append((pat,typ))
    outbound=[]
    inbound=[]
    delegates={"masiyuan8900@novogene.com","jiin.yoo@novogene.com"}
    system_senders={"css@novogene-amea.com"}
    def internal_address(addr):
        return addr.endswith("@novogene.com") or addr.endswith("@novogene-amea.com")
    for r in messages:
        direction=r.get("direction","")
        if direction not in ("INBOUND","OUTBOUND"):continue
        r["_at"]=when(r.get("received_at"))
        r["_sub"]=norm_subject(r.get("subject"))
        (inbound if direction=="INBOUND" else outbound).append(r)
        # Delegates' customer-directed messages may be delivered to this inbox
        # via CC. Treat them as reply evidence, never as customer enquiries.
        if direction=="INBOUND" and addresses(r.get("from_email")) & delegates:
            recipients=addresses(r.get("recipient_to")) | addresses(r.get("cc"))
            if any(not internal_address(addr) for addr in recipients):
                outbound.append(r)
    now=dt.datetime.now(dt.timezone.utc).isoformat()
    result=[]
    seen_conversations=set()
    buckets={"CUSTOMER_REVIEW":0}
    for m in sorted(inbound,key=lambda x:x["_at"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc),reverse=True):
        mail_from=addresses(m.get("from_email"))
        if not m["_at"] or not m["_sub"] or not mail_from:continue
        # Internal threads are not the customer's unanswered requests.
        # The delegated outbound evidence above remains usable.
        if mail_from & system_senders:continue
        if all(internal_address(addr) for addr in mail_from):continue
        if own_addresses and not (own_addresses & (addresses(m.get("recipient_to")) | addresses(m.get("cc")))):continue
        if not dt.timedelta(0) <= now_utc - m["_at"] <= dt.timedelta(days=config["unanswered_lookback_days"]):continue
        key=str(m.get("ingest_key","")).strip()
        legacy_uid="inbox:"+str(m.get("imap_uid","")).strip()
        if key.casefold() in banned_ids or legacy_uid.casefold() in banned_ids or str(m.get("imap_uid","")).casefold() in banned_ids:continue
        if any((mail_from & senders_set) and m["_sub"]==subject and m["_at"]<=cutoff
               for senders_set,subject,cutoff in previous_thread_exclusions):continue
        excluded=False
        for address in mail_from:
            for pat,typ in banned_sender:
                if (typ=="exact" and address==pat) or (typ=="domain" and address.endswith("@"+pat.lstrip("@"))) or (typ=="contains" and pat in address):
                    excluded=True
                    break
            if excluded:break
        if excluded:continue
        if any((kind=="exact" and address==p) or
               (kind=="prefix" and address.split("@")[0].startswith(p)) or
               (kind=="contains" and p in address)
               for address in mail_from for p,kind in auto_exclusions):continue
        matched=any(
            sent["_at"] and sent["_at"]>=m["_at"] and sent["_sub"]==m["_sub"]
            and bool(mail_from & (addresses(sent.get("recipient_to")) | addresses(sent.get("cc"))))
            for sent in outbound
        )
        if matched:continue
        conversation=(tuple(sorted(mail_from)),m["_sub"])
        if conversation in seen_conversations:continue
        seen_conversations.add(conversation)
        projects=" | ".join(filter(None,[str(m.get(c,"")) for c in
            ("amea_numbers","h_project_numbers","sam_numbers","batch_numbers")]))
        local = m["_at"].astimezone(src.KST)
        days = max(0, (today-local.date()).days)
        weekday = "월화수목금토일"[local.weekday()]
        display_date = local.strftime("%m/%d")+"("+weekday+") "+local.strftime("%H:%M")
        bucket = "CUSTOMER_REVIEW"
        buckets[bucket] += 1
        review_note = "회신 여부 검토 필요 (수집 범위 한정)"
        if days < config["action_unanswered_min_age_days"]:
            review_note = "관찰 중 (최소 경과일 미달)"
        elif days > config["action_unanswered_max_age_days"]:
            review_note = "30일 초과: Action Center 대상 제외"
        else:
            review_note = "2~30일: 후속조치 검토 (확정 아님)"
        result.append([str(days)+"일",display_date,m.get("from_email",""),m.get("subject",""),
                       "","신규",bucket,"",m.get("from_email",""),"","FALSE","FALSE",
                       m.get("recipient_to",""),m.get("cc",""),projects,review_note,
                       m["_sub"],"inbox:"+str(m.get("imap_uid","")),"",now,bucket])
        if len(result)>=1500:break
    return result

def main():
    s=src.authorize()
    mail=table(s,SOURCE,"P",MAX_READ)
    excludes=table(s,EXCLUDED,"L",10000)
    senders=table(s,SENDER_EXCLUDED,"F",10000)
    rules=table(s,"CSS Rules & SLA","I",300)
    sender_rules=table(s,"CSS Sender Rules","G",200)
    if not mail:
        raise RuntimeError("CSS Git Ingest empty; preserving previous review results")
    result=candidates(mail,excludes,senders,rules,sender_rules)
    props=src.api(s,"GET",src.endpoint()+"?fields=sheets.properties.title")
    titles={x["properties"]["title"] for x in props.get("sheets",[])}
    if OUTPUT not in titles:
        src.api(s,"POST",src.endpoint(":batchUpdate"),json={"requests":[{"addSheet":{"properties":{"title":OUTPUT,"gridProperties":{"frozenRowCount":1}}}}]})
    def rng(cell):return urllib.parse.quote("'"+OUTPUT+"'!"+cell,safe="")
    # Only this generated sheet is cleared. Existing manual lists remain intact.
    src.api(s,"POST",src.endpoint("/values/"+rng("A1:U1600")+":clear"),json={})
    src.api(s,"PUT",src.endpoint("/values/"+rng("A1"))+"?valueInputOption=RAW",
            json={"values":[HEADER]+result})
    print("CSS_UNANSWERED_AUTO_PASS candidates="+str(len(result))+
          " exclusions="+str(len(excludes))+" sender_rules="+str(len(senders))+
          " status=CLASSIFIED_ADVISORY")
if __name__=="__main__":
    try:main()
    except Exception as e:
        print("CSS_UNANSWERED_AUTO_FAILED "+(str(e) if isinstance(e,RuntimeError) else type(e).__name__),file=sys.stderr)
        sys.exit(1)
