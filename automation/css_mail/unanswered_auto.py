#!/usr/bin/env python3
"""Advisory unanswered-email candidates from the QQ Mail staging ledger.

Reads existing exclusions; never replaces the manual Unanswered Emails sheet.
Headers only: missing replies outside collection window remain uncertain.
"""
import datetime as dt
import re
import sys
import urllib.parse
from email.utils import getaddresses
import incremental_sync as src

OUTPUT = "Unanswered Emails Auto"
SOURCE = "CSS Git Ingest"
EXCLUDED = "Unanswered Email Exclusions"
SENDER_EXCLUDED = "Unanswered Sender Exclusions"
HEADER = ["received_at","from_email","subject","project_ids","review_status",
          "reply_evidence","ingest_key","source_message_id","last_checked_utc"]
MAX_READ = 100000

def table(s, tab, columns, end):
    a1=urllib.parse.quote("'"+tab+"'!A1:"+columns+str(end),safe="")
    rows=src.api(s,"GET",src.endpoint("/values/"+a1)).get("values",[])
    if not rows:return []
    head=[str(x).strip() for x in rows[0]]
    return [dict(zip(head,r+[""]*(len(head)-len(r)))) for r in rows[1:] if any(r)]

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
        return parsed.astimezone(dt.timezone.utc) if parsed.tzinfo else None
    except (ValueError,TypeError):return None

def candidates(messages, exclusions, senders):
    banned_ids=set()
    for r in exclusions:
        if str(r.get("restore","")).upper() in ("TRUE","1","YES"):continue
        if r.get("uid"):banned_ids.add(r["uid"].strip())
    banned_sender=[]
    for r in senders:
        if str(r.get("restore","")).upper() in ("TRUE","1","YES"):continue
        pat=str(r.get("sender_pattern","")).strip().casefold()
        typ=str(r.get("match_type","")).strip().casefold()
        if pat and typ in ("exact","domain","contains"):banned_sender.append((pat,typ))
    outbound=[]
    inbound=[]
    for r in messages:
        direction=r.get("direction","")
        if direction not in ("INBOUND","OUTBOUND"):continue
        r["_at"]=when(r.get("received_at"))
        r["_sub"]=norm_subject(r.get("subject"))
        (inbound if direction=="INBOUND" else outbound).append(r)
    now=dt.datetime.now(dt.timezone.utc).isoformat()
    result=[]
    for m in sorted(inbound,key=lambda x:x["_at"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc),reverse=True):
        mail_from=addresses(m.get("from_email"))
        if not m["_at"] or not m["_sub"] or not mail_from:continue
        key=str(m.get("ingest_key","")).strip()
        legacy_uid="inbox:"+str(m.get("imap_uid","")).strip()
        if key in banned_ids or legacy_uid in banned_ids or m.get("imap_uid","") in banned_ids:continue
        excluded=False
        for address in mail_from:
            for pat,typ in banned_sender:
                if (typ=="exact" and address==pat) or (typ=="domain" and address.endswith("@"+pat.lstrip("@"))) or (typ=="contains" and pat in address):
                    excluded=True
                    break
            if excluded:break
        if excluded:continue
        matched=any(
            sent["_at"] and sent["_at"]>=m["_at"] and sent["_sub"]==m["_sub"]
            and bool(mail_from & (addresses(sent.get("recipient_to")) | addresses(sent.get("cc"))))
            for sent in outbound
        )
        if matched:continue
        projects=" | ".join(filter(None,[str(m.get(c,"")) for c in
            ("amea_numbers","h_project_numbers","sam_numbers","batch_numbers")]))
        result.append([m.get("received_at",""),m.get("from_email",""),m.get("subject",""),
                      projects,"REVIEW_ONLY","No matching later sent header within collected window",
                      key,m.get("message_id",""),now])
        if len(result)>=1500:break
    return result

def main():
    s=src.authorize()
    mail=table(s,SOURCE,"P",MAX_READ)
    excludes=table(s,EXCLUDED,"L",10000)
    senders=table(s,SENDER_EXCLUDED,"F",10000)
    result=candidates(mail,excludes,senders)
    props=src.api(s,"GET",src.endpoint()+"?fields=sheets.properties.title")
    titles={x["properties"]["title"] for x in props.get("sheets",[])}
    if OUTPUT not in titles:
        src.api(s,"POST",src.endpoint(":batchUpdate"),json={"requests":[{"addSheet":{"properties":{"title":OUTPUT,"gridProperties":{"frozenRowCount":1}}}}]})
    def rng(cell):return urllib.parse.quote("'"+OUTPUT+"'!"+cell,safe="")
    # Only this generated sheet is cleared. Existing manual lists remain intact.
    src.api(s,"POST",src.endpoint("/values/"+rng("A1:I1600")+":clear"),json={})
    src.api(s,"PUT",src.endpoint("/values/"+rng("A1"))+"?valueInputOption=RAW",
            json={"values":[HEADER]+result})
    print("CSS_UNANSWERED_AUTO_PASS candidates="+str(len(result))+
          " exclusions="+str(len(excludes))+" sender_rules="+str(len(senders))+
          " status=REVIEW_ONLY")
if __name__=="__main__":
    try:main()
    except Exception as e:
        print("CSS_UNANSWERED_AUTO_FAILED "+(str(e) if isinstance(e,RuntimeError) else type(e).__name__),file=sys.stderr)
        sys.exit(1)
