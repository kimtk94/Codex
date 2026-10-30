#!/usr/bin/env python3
"""Cache QQ Inbox and personal Sent bodies for the web from GitHub Actions.

Source of truth: QQ IMAP UIDVALIDITY/UID and CSS Git Ingest.
Destination: CSS Mail Inbox Raw derived body cache. Does not send mail,
modify IMAP, overwrite review decisions, or pretend headers contain a body.
"""
import datetime as dt
import email
import hashlib
import imaplib
import os
import re
import time
import requests
import unicodedata
import urllib.parse
from collections import Counter
from email import policy
from email.utils import getaddresses
from html.parser import HTMLParser
import incremental_sync as src

SFDC = '1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI'
RAW = 'CSS Mail Inbox Raw'
HEADERS = ['Mail UID','Message-ID','Thread Key','Received At KST','From Email',
           'From Name','To','Cc','Subject','Body Text']
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+$')
UID_RE = re.compile(r'^[0-9]{1,12}$')
MAX_BODY = 45000
MAX_FETCH_BYTES = 12 * 1024 * 1024


class Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.hidden=0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style'): self.hidden += 1
        if tag in ('br','p','div','tr','li'): self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script','style'): self.hidden=max(0,self.hidden-1)
    def handle_data(self, data):
        if not self.hidden: self.parts.append(data)


def normalize_body(value):
    """Canonicalize transport line endings and unsafe control characters.

    IMAP MIME and Google Sheets may represent CRLF differently. Use the same
    canonical form for both the written body and the post-write comparison.
    """
    value=unicodedata.normalize('NFC',str(value))
    value=value.replace('\r\n','\n').replace('\r','\n')
    return ''.join(ch for ch in value if ch in ('\n','\t')
                   or unicodedata.category(ch)[0]!='C')


def body_text(msg):
    plain=[]; html=[]
    for part in msg.walk():
        if part.get_content_disposition() == 'attachment': continue
        if part.get_content_type() not in ('text/plain','text/html'): continue
        try: content=part.get_content()
        except (ValueError,UnicodeError,LookupError): continue
        if part.get_content_type()=='text/plain': plain.append(str(content))
        else:
            parser=Text(); parser.feed(str(content)); html.append(''.join(parser.parts))
    return normalize_body('\n'.join(plain or html)).strip()[:MAX_BODY]


def url(book, span):
    return 'https://sheets.googleapis.com/v4/spreadsheets/'+book+'/values/'+urllib.parse.quote(span,safe='')


def value(row, index):
    return str(row[index]).strip() if len(row)>index and row[index] is not None else ''


def addresses(*parts):
    return {a.lower() for _,a in getaddresses([str(p or '') for p in parts]) if EMAIL_RE.fullmatch(a)}


def parsed_at(value):
    try:
        d=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return d.astimezone(dt.timezone.utc) if d.tzinfo else None
    except (ValueError,TypeError): return None


def candidate_key(data):
    folder=value(data,3)
    direction=value(data,15).upper()
    raw_uid=value(data,2)
    if not UID_RE.fullmatch(raw_uid): return None
    if folder.upper()=='INBOX': return 'inbox:'+raw_uid
    if direction=='OUTBOUND': return 'sent:'+raw_uid
    return None


def select_candidates(ingest, cache, queue, owner, now, lookback_days=60, batch=80):
    """Return prioritized metadata without disturbing cached messages/decisions."""
    if not ingest or ingest[0]!=src.COLS:
        raise RuntimeError('QQ_INGEST_SCHEMA_MISMATCH')
    if not cache or cache[0][:10]!=HEADERS:
        raise RuntimeError('WEB_MAIL_CACHE_SCHEMA_MISMATCH')
    owner=owner.strip().lower()
    if not EMAIL_RE.fullmatch(owner): raise RuntimeError('MAIL_OWNER_ADDRESS_INVALID')
    if not 1<=lookback_days<=60 or not 1<=batch<=200:
        raise RuntimeError('BODY_SYNC_LIMIT_OUT_OF_BOUNDS')
    stored={}
    for i,r in enumerate(cache[1:],start=2):
        uid=value(r,0).lower()
        if not uid:continue
        if uid in stored: raise RuntimeError('WEB_MAIL_DUPLICATE_UID')
        stored[uid]=(i,r)
    wanted={value(r,8).lower() for r in queue[1:] if len(r)>8
            and re.fullmatch(r'inbox:[0-9]{1,12}',value(r,8).lower())}
    seen={}
    cutoff=now-dt.timedelta(days=lookback_days)
    for row in ingest[1:]:
        uid=candidate_key(row)
        if not uid: continue
        folder=value(row,3)
        key=value(row,0)
        if key!=folder+'|'+value(row,4)+'|'+value(row,2):
            raise RuntimeError('QQ_INGEST_SOURCE_KEY_MISMATCH')
        when=parsed_at(value(row,5))
        own=(owner in addresses(value(row,6),value(row,7),value(row,8)))
        if not ((own and when and cutoff<=when<=now+dt.timedelta(hours=12))
                or (uid in wanted and when)):
            continue
        # A mismatched existing UID is a safety stop, never overwrite it.
        if uid in stored:
            old=stored[uid][1]
            if value(old,1) and value(row,1) and value(old,1)!=value(row,1):
                raise RuntimeError('WEB_MAIL_MESSAGE_ID_CONFLICT')
            if value(old,2) and value(old,2)!=key:
                raise RuntimeError('WEB_MAIL_INGEST_KEY_CONFLICT')
            if value(old,9) or value(old,21)=='BODY_EMPTY_MIME':continue
        if uid in seen and seen[uid]!=row:
            raise RuntimeError('QQ_INGEST_DUPLICATE_UID_CONFLICT')
        seen[uid]=row
    prioritized=sorted(seen.items(),key=lambda it:(
        it[0] in wanted,
        parsed_at(value(it[1],5)) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    ),reverse=True)
    return prioritized[:batch],stored,len(seen)


def validate_message(msg, meta):
    source_id=value(meta,1)
    actual_id=str(msg.get('Message-ID','')).strip()
    if source_id:
        return actual_id==source_id
    # Some mail system notices omit Message-ID; the UIDVALIDITY/UID key and
    # exact source subject/from provide independent header cross-checks.
    actual_subject=str(msg.get('Subject','')).strip()
    actual_from=addresses(str(msg.get('From','')))
    return bool(actual_subject and actual_subject==value(meta,9)
                and value(meta,6).lower() in actual_from)


def make_row(uid,meta,msg,body,now):
    when=parsed_at(value(meta,5))
    if not when:raise RuntimeError('QQ_MESSAGE_DATE_MISSING')
    received=when.astimezone(src.KST).isoformat()
    return [
        uid,value(meta,1),value(meta,0),received,value(meta,6),
        str(msg.get('From','')),value(meta,7),value(meta,8),value(meta,9),
        body,'OUTBOUND' if uid.startswith('sent:') else 'INBOUND',
        '','','','','','','','QQ_IMAP_UID_VERIFIED',
        now,now,'WEB_REVIEW_CACHE','',''
    ]


def sync():
    session=src.authorize()
    def read(book,span):
        # Google Sheets occasionally times out under concurrent report
        # writers; only replay idempotent GETs, never POST/append.
        for attempt in range(3):
            try:
                return src.api(session,'GET',url(book,span)).get('values',[])
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                if attempt==2:
                    raise
                time.sleep(1.0+2.0*attempt)
    queue=read(SFDC,"'Unanswered Emails'!A1:V1300")
    if not queue or value(queue[0],8)!='Thread UID':
        raise RuntimeError('WEB_REVIEW_QUEUE_SCHEMA_MISMATCH')
    cache=read(SFDC,"'CSS Mail Inbox Raw'!A1:X10000")
    ingest=read(src.BOOK,"'CSS Git Ingest'!A1:R100000")
    now=dt.datetime.now(dt.timezone.utc)
    owner=os.getenv('CSS_MAIL_OWNER_ADDRESS') or os.environ['CSS_QQ_MAIL_ADDRESS']
    batch=int(os.getenv('CSS_WEB_BODY_BATCH','80'))
    lookback=int(os.getenv('CSS_WEB_BODY_LOOKBACK_DAYS','60'))
    candidates,stored,total=select_candidates(
        ingest,cache,queue,owner,now,lookback,batch)
    stamp=now.astimezone(src.KST).isoformat()
    groups={}
    for uid,meta in candidates:
        folder=value(meta,3)
        groups.setdefault(folder,[]).append((uid,meta))
    results=[]
    empty_results=[]
    errors=Counter()
    with imaplib.IMAP4_SSL('imap.exmail.qq.com',993,timeout=45) as im:
        im.login(os.environ['CSS_QQ_MAIL_ADDRESS'],os.environ['CSS_QQ_MAIL_AUTH_CODE'])
        for folder,items in groups.items():
            state,_=im.select('"'+folder.replace('"','')+'"',readonly=True)
            if state!='OK':raise RuntimeError('QQ_IMAP_FOLDER_UNAVAILABLE')
            _,uv=im.response('UIDVALIDITY')
            valid=uv[0].decode() if uv and uv[0] else ''
            if not valid:raise RuntimeError('QQ_IMAP_UIDVALIDITY_MISSING')
            if any(value(meta,4)!=valid for _,meta in items):
                raise RuntimeError('QQ_IMAP_UIDVALIDITY_CHANGED')
            for uid,meta in items:
                status,data=im.uid('FETCH',value(meta,2),'(BODY.PEEK[])')
                if status!='OK':
                    errors['FETCH_FAILED']+=1;continue
                chunks=[part[1] for part in data or []
                        if isinstance(part,tuple) and isinstance(part[1],bytes)]
                size=sum(len(c) for c in chunks)
                if not size:
                    errors['EMPTY_FETCH']+=1;continue
                if size>MAX_FETCH_BYTES:
                    errors['MIME_TOO_LARGE']+=1;continue
                msg=email.message_from_bytes(b''.join(chunks),policy=policy.default)
                if not validate_message(msg,meta):
                    errors['HEADER_MISMATCH']+=1;continue
                body=body_text(msg)
                if not body:
                    errors['EMPTY_BODY']+=1
                    row=make_row(uid,meta,msg,'',stamp)
                    row[21]='BODY_EMPTY_MIME'
                    empty_results.append(row)
                    continue
                results.append(make_row(uid,meta,msg,body,stamp))
    # Double-check current cache before writing. A manually edited row wins.
    latest=read(SFDC,"'CSS Mail Inbox Raw'!A1:X10000")
    if latest[0][:10]!=HEADERS:raise RuntimeError('WEB_MAIL_CACHE_CHANGED_SCHEMA')
    positions={}
    for n,r in enumerate(latest[1:],start=2):
        key=value(r,0).lower()
        if not key:continue
        if key in positions:raise RuntimeError('WEB_MAIL_DUPLICATE_UID')
        positions[key]=(n,r)
    patches=[]
    fresh=[]
    for row in results:
        uid=row[0]
        if uid in positions:
            number,old=positions[uid]
            if value(old,1) and value(old,1)!=row[1]:
                raise RuntimeError('WEB_MAIL_MESSAGE_ID_CONFLICT')
            if value(old,2) and value(old,2)!=row[2]:
                raise RuntimeError('WEB_MAIL_INGEST_KEY_CONFLICT')
            if value(old,9):continue
            patches += [
                {'range':"'CSS Mail Inbox Raw'!F"+str(number),'values':[[row[5]]]},
                {'range':"'CSS Mail Inbox Raw'!J"+str(number),'values':[[row[9]]]},
                {'range':"'CSS Mail Inbox Raw'!U"+str(number)+":V"+str(number),
                 'values':[[stamp,'WEB_REVIEW_CACHE']]}
            ]
        else:
            fresh.append(row)
    empty_patches=[]
    empty_existing=0
    for row in empty_results:
        uid=row[0]
        if uid in positions:
            number,old=positions[uid]
            if value(old,1) and value(old,1)!=row[1]:
                raise RuntimeError('WEB_MAIL_MESSAGE_ID_CONFLICT')
            if value(old,2) and value(old,2)!=row[2]:
                raise RuntimeError('WEB_MAIL_INGEST_KEY_CONFLICT')
            if value(old,9):continue
            if value(old,21) not in ('','HEADER_ONLY_BODY_PENDING',
                                     'WEB_REVIEW_CACHE','BODY_EMPTY_MIME'):
                continue
            empty_patches.append({
                'range':"'CSS Mail Inbox Raw'!U"+str(number)+":V"+str(number),
                'values':[[stamp,'BODY_EMPTY_MIME']]})
            empty_existing+=1
        else:
            # The mail is a verified original, but contains no plain/html
            # body. Preserve its header, never invent text or mark BODY_READY.
            fresh.append(row)
    patches += empty_patches
    if patches:
        src.api(session,'POST',
            'https://sheets.googleapis.com/v4/spreadsheets/'+SFDC+'/values:batchUpdate',
            json={'valueInputOption':'RAW','data':patches})
    if fresh:
        if len(positions)+len(fresh)>9999:
            raise RuntimeError('WEB_MAIL_CACHE_CAPACITY_EXCEEDED')
        src.api(session,'POST',url(SFDC,"'CSS Mail Inbox Raw'!A:X")
                +':append?valueInputOption=RAW&insertDataOption=INSERT_ROWS',
                json={'values':fresh})
    # Read-back may lag a recently appended range. Compare normalized,
    # Sheets-safe strings and retry briefly before reporting a data mismatch.
    # Never log customer bodies, addresses, or raw message content.
    mismatches=[]
    # Read back only the occupied prefix plus a small margin, not 10,000
    # heavy formula-backed cells on every retry. The initial cache read
    # already established the occupied prefix; append runs under one lock.
    readback_end=min(10000,max(1000,len(latest)+len(fresh)+100))
    for retry in range(3):
        after_uid=read(SFDC,"'CSS Mail Inbox Raw'!A1:A"+str(readback_end))
        after_body=read(SFDC,"'CSS Mail Inbox Raw'!J1:J"+str(readback_end))
        after_status=read(SFDC,"'CSS Mail Inbox Raw'!V1:V"+str(readback_end))
        verified={value(r,0).lower():i for i,r in enumerate(after_uid)
                  if i>0 and value(r,0)}
        mismatches=[]
        for row in results:
            ix=verified.get(row[0])
            actual=(normalize_body(value(after_body[ix],0)) if ix is not None
                    and ix<len(after_body) else '')
            if hashlib.sha256(actual.encode()).digest()!=hashlib.sha256(
                    normalize_body(row[9]).encode()).digest():
                mismatches.append((row[0],len(row[9]),len(actual)))
        for row in empty_results:
            ix=verified.get(row[0])
            if ix is None or ix>=len(after_status):
                mismatches.append((row[0],0,-1))
                continue
            body_now=normalize_body(value(after_body[ix],0)) if ix<len(after_body) else ''
            if not body_now and value(after_status[ix],0)!='BODY_EMPTY_MIME':
                mismatches.append((row[0],0,-2))
        if not mismatches:break
        if retry<2:time.sleep(1.5)
    if mismatches:
        # Hash only UID identifiers, not mail bodies.
        samples=[(hashlib.sha256(uid.encode()).hexdigest()[:10],expected,observed)
                 for uid,expected,observed in mismatches[:5]]
        print('WEB_BODY_READBACK_MISMATCH count='+str(len(mismatches))+
              ' hashed_uid_expected_actual_lengths='+repr(samples),flush=True)
        raise RuntimeError('WEB_BODY_POSTWRITE_CONTENT_MISMATCH')
    status='PASS' if not errors and total==len(candidates) else 'PARTIAL'
    print('CSS_WEB_BODY_SYNC_'+status+
          ' selected='+str(len(candidates))+' eligible='+str(total)+
          ' fetched='+str(len(results))+' updated='+str((len(patches)-len(empty_patches))//3)+
          ' inserted='+str(len(fresh))+' empty_mime='+str(len(empty_results))+
          ' empty_existing='+str(empty_existing)+
          ' errors='+str(sum(errors.values()))+
          ' error_types='+','.join(sorted(errors)),flush=True)
    if errors and not results and any(k!='EMPTY_BODY' for k in errors):
        raise RuntimeError('WEB_BODY_ZERO_SUCCESS_WITH_FETCH_ERRORS')
    # Partial is explicitly named in logs; remaining candidates continue
    # next 30-minute run. No false "all mail synchronized" status.


if __name__=='__main__':
    sync()
