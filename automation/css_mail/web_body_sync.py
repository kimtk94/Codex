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
import unicodedata
import urllib.parse
from collections import Counter
from email import policy
from email.parser import BytesHeaderParser
from email.utils import getaddresses
from html.parser import HTMLParser
import incremental_sync as src

SFDC = '1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI'
BACKFILL_TAB = "CSS Mail Backfill Status"
BACKFILL_HEADER = [
    'Updated At KST','State','QQ Staged Headers','Web Cached UID',
    'Body Ready','Body Empty MIME','Header Pending','Remaining Eligible',
    'Batch Selected','Batch Body Fetched','Batch Empty MIME','Fetch Errors',
    'Latest Source At','GitHub Run','Notes'
]
RAW = 'CSS Mail Inbox Raw'
HEADERS = ['Mail UID','Message-ID','Thread Key','Received At KST','From Email',
           'From Name','To','Cc','Subject','Body Text']
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+$')
UID_RE = re.compile(r'^[0-9]{1,12}$')
MAX_BODY = 45000
MAX_FETCH_BYTES = 12 * 1024 * 1024
MAX_HEADER_BYTES = 128 * 1024


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

def exact_body_cell(row, index=0):
    """Preserve meaningful trailing whitespace during post-write body parity.

    Header/categorical values still use value(...).strip(). MIME content is
    never stripped when verifying what Google Sheets actually stored.
    """
    return str(row[index]) if len(row)>index and row[index] is not None else ''


def body_matches(source, stored):
    """Strict normalized MIME parity. A dropped whitespace character fails."""
    expected=normalize_body(source)
    observed=normalize_body(stored)
    return hashlib.sha256(expected.encode('utf-8')).digest()==hashlib.sha256(
        observed.encode('utf-8')).digest()


def verified_oversize_header(raw, meta):
    """Check a bounded original header without decoding huge attachment bytes.

    No MIME body is parsed, shortened or stored for oversized source mails.
    Missing or conflicting Message-ID/From/Subject refuses the terminal marker.
    """
    prefix=raw[:MAX_HEADER_BYTES]
    separators=[(prefix.find(sep),len(sep)) for sep in (b'\r\n\r\n',b'\n\n')]
    complete=[(at,width) for at,width in separators if at>=0]
    if not complete:
        return None
    at,width=min(complete)
    if at==0:
        return None
    msg=BytesHeaderParser(policy=policy.default).parsebytes(prefix[:at+width])
    return msg if validate_message(msg,meta) else None


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
            if value(old,9) or value(old,21) in ('BODY_EMPTY_MIME','BODY_OVERSIZE_MIME'):continue
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


def progress_record(ingest, uid_rows, body_rows, status_rows, remaining,
                    selected, text_fetched, empty_count, errors, now, run_id):
    """Return non-PII, source-scoped backfill status for the central workspace."""
    seen=set()
    ready=empty=oversize=0
    for i, record in enumerate(uid_rows[1:], start=1):
        uid=value(record,0).lower()
        if not uid:
            continue
        if uid in seen:
            raise RuntimeError('WEB_MAIL_PROGRESS_DUPLICATE_UID')
        seen.add(uid)
        body=value(body_rows[i],0) if i<len(body_rows) else ''
        state=value(status_rows[i],0) if i<len(status_rows) else ''
        if body:
            ready+=1
        elif state=='BODY_EMPTY_MIME':
            empty+=1
        elif state=='BODY_OVERSIZE_MIME':
            oversize+=1
    latest=max((t for record in ingest[1:]
                if (t:=parsed_at(value(record,5))) is not None),default=None)
    meaningful_errors=sum(v for k,v in errors.items() if k!='EMPTY_BODY')
    state=('PARTIAL_ERRORS' if meaningful_errors else
           'BACKFILL_ACTIVE' if remaining>0 else 'WINDOW_CAUGHT_UP')
    return [
        now.astimezone(src.KST).strftime('%Y-%m-%d %H:%M:%S KST'),
        state,len(ingest)-1,len(seen),ready,empty,
        len(seen)-ready-empty-oversize,max(0,remaining),selected,text_fetched,
        empty_count,meaningful_errors,
        latest.isoformat() if latest else '',str(run_id or ''),
        ('Source-snapshot scope: personal Inbox/Sent last 60 days plus unanswered queue; '
         'oversize_MIME_body_unavailable='+str(oversize))
    ]


def publish_progress(session, read, ingest, uid_rows, body_rows, status_rows,
                     remaining, selected, text_fetched, empty_count, errors, now):
    sheet_head=read(SFDC,"'CSS Mail Backfill Status'!A1:O1")
    if sheet_head!=[BACKFILL_HEADER]:
        raise RuntimeError('WEB_MAIL_BACKFILL_STATUS_SCHEMA_MISMATCH')
    row=progress_record(ingest,uid_rows,body_rows,status_rows,remaining,
                        selected,text_fetched,empty_count,errors,now,
                        os.getenv('GITHUB_RUN_ID',''))
    endpoint=url(SFDC,"'CSS Mail Backfill Status'!A2:O2")
    src.api(session,'PUT',endpoint+'?valueInputOption=RAW',
            json={'range':"'CSS Mail Backfill Status'!A2:O2",
                  'majorDimension':'ROWS','values':[row]})
    observed=read(SFDC,"'CSS Mail Backfill Status'!A2:O2")
    if not observed or [str(v) for v in observed[0][:14]]!=[str(v) for v in row[:14]]:
        raise RuntimeError('WEB_MAIL_BACKFILL_STATUS_READBACK_MISMATCH')
    return row


def sync():
    session=src.authorize()
    def read(book,span):
        # AuthorizedSession and Sheets may sporadically time out after a
        # successful append. Retry *reads only*; all writes remain idempotent.
        for attempt in range(3):
            try:
                return src.api(session,'GET',url(book,span)).get('values',[])
            except Exception as exc:
                transient=('Timeout' in type(exc).__name__
                           or type(exc).__name__ in ('ConnectionError',))
                if not transient or attempt==2:
                    raise
                time.sleep(1.5*(2**attempt))
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
    oversize_results=[]
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
                raw=b''.join(chunks)
                if size>MAX_FETCH_BYTES:
                    verified=verified_oversize_header(raw,meta)
                    if not verified:
                        errors['OVERSIZE_HEADER_UNVERIFIED']+=1;continue
                    row=make_row(uid,meta,verified,'',stamp)
                    row[21]='BODY_OVERSIZE_MIME'
                    oversize_results.append(row)
                    continue
                msg=email.message_from_bytes(raw,policy=policy.default)
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
    oversize_existing=0
    for row in empty_results+oversize_results:
        uid=row[0]
        if uid in positions:
            number,old=positions[uid]
            if value(old,1) and value(old,1)!=row[1]:
                raise RuntimeError('WEB_MAIL_MESSAGE_ID_CONFLICT')
            if value(old,2) and value(old,2)!=row[2]:
                raise RuntimeError('WEB_MAIL_INGEST_KEY_CONFLICT')
            if value(old,9):continue
            if value(old,21) not in ('','HEADER_ONLY_BODY_PENDING',
                                     'WEB_REVIEW_CACHE','BODY_EMPTY_MIME',
                                     'BODY_OVERSIZE_MIME'):
                continue
            empty_patches.append({
                'range':"'CSS Mail Inbox Raw'!U"+str(number)+":V"+str(number),
                'values':[[stamp,row[21]]]})
            if row[21]=='BODY_EMPTY_MIME':
                empty_existing+=1
            else:
                oversize_existing+=1
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
    # Bound the verification to actual occupied rows. Avoid 10k-row
    # scans after every append, which can exceed Sheets read timeouts.
    # New evidence is verified after each idempotent read/write cycle.
    max_row=len(latest)+len(fresh)+2
    mismatches=[]
    for retry in range(3):
        after_uid=read(SFDC,"'CSS Mail Inbox Raw'!A1:A"+str(max_row))
        after_body=read(SFDC,"'CSS Mail Inbox Raw'!J1:J"+str(max_row))
        after_status=read(SFDC,"'CSS Mail Inbox Raw'!V1:V"+str(max_row))
        verified={value(r,0).lower():i for i,r in enumerate(after_uid)
                  if i>0 and value(r,0)}
        mismatches=[]
        for row in results:
            ix=verified.get(row[0])
            actual=(exact_body_cell(after_body[ix]) if ix is not None
                    and ix<len(after_body) else '')
            if not body_matches(row[9],actual):
                mismatches.append((row[0],len(row[9]),len(actual)))
        for row in empty_results+oversize_results:
            ix=verified.get(row[0])
            if ix is None or ix>=len(after_status):
                mismatches.append((row[0],0,-1))
                continue
            body_now=normalize_body(exact_body_cell(after_body[ix])) if ix<len(after_body) else ''
            if body_now or value(after_status[ix],0)!=row[21]:
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
    progress=publish_progress(
        session,read,ingest,after_uid,after_body,after_status,
        max(0,total-len(results)-len(empty_results)-len(oversize_results)),len(candidates),
        len(results),len(empty_results),errors,now)
    print('CSS_WEB_BACKFILL_STATUS state='+progress[1]+
          ' cache_total='+str(progress[3])+
          ' ready='+str(progress[4])+
          ' no_text='+str(progress[5])+
          ' header_only='+str(progress[6])+
          ' remaining_eligible='+str(progress[7]),flush=True)
    status='PASS' if not errors and total==len(candidates) else 'PARTIAL'
    print('CSS_WEB_BODY_SYNC_'+status+
          ' selected='+str(len(candidates))+' eligible='+str(total)+
          ' fetched='+str(len(results))+' updated='+str((len(patches)-len(empty_patches))//3)+
          ' inserted='+str(len(fresh))+' empty_mime='+str(len(empty_results))+
          ' empty_existing='+str(empty_existing)+
          ' oversize_mime='+str(len(oversize_results))+
          ' oversize_existing='+str(oversize_existing)+
          ' errors='+str(sum(errors.values()))+
          ' error_types='+','.join(sorted(errors)),flush=True)
    if errors and not results and any(k!='EMPTY_BODY' for k in errors):
        raise RuntimeError('WEB_BODY_ZERO_SUCCESS_WITH_FETCH_ERRORS')
    # Partial is explicitly named in logs; remaining candidates continue
    # next 30-minute run. No false "all mail synchronized" status.


if __name__=='__main__':
    sync()
