#!/usr/bin/env python3
"""Cache bodies for the current web review queue only; IMAP is read-only."""
import datetime as dt
import email
import imaplib
import os
import re
import urllib.parse
from email import policy
from html.parser import HTMLParser
import incremental_sync as src

SFDC = '1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI'
RAW = 'CSS Mail Inbox Raw'
HEADERS = ['Mail UID','Message-ID','Thread Key','Received At KST','From Email','From Name','To','Cc','Subject','Body Text']
class Text(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]; self.hidden=0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style'): self.hidden += 1
        if tag in ('br','p','div','tr','li'): self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script','style'): self.hidden=max(0,self.hidden-1)
    def handle_data(self, data):
        if not self.hidden: self.parts.append(data)
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
    return '\n'.join(plain or html).strip()[:45000]
def url(book, range):
    return 'https://sheets.googleapis.com/v4/spreadsheets/'+book+'/values/'+urllib.parse.quote(range,safe='')
def main():
    s=src.authorize()
    def read(book, range): return src.api(s,'GET',url(book,range)).get('values',[])
    queue=read(SFDC,"'Unanswered Emails'!A1:V1300")
    existing=read(SFDC,"'CSS Mail Inbox Raw'!A1:X10000")
    if not queue or queue[0][8]!='Thread UID': raise RuntimeError('Unexpected queue schema')
    if not existing or existing[0][:10]!=HEADERS: raise RuntimeError('Unexpected body cache schema')
    stored={r[0] for r in existing[1:] if len(r)>9 and r[9]}
    wanted={r[8] for r in queue[1:] if len(r)>8 and re.fullmatch(r'inbox:\d{1,12}',r[8]) and r[8] not in stored}
    ingest=read(src.BOOK,"'CSS Git Ingest'!A1:R100000")
    if not ingest or ingest[0]!=src.COLS: raise RuntimeError('Unexpected ingest schema')
    candidates={}
    for r in ingest[1:]:
        m=dict(zip(src.COLS,r))
        uid='inbox:'+m.get('imap_uid','')
        if uid in wanted and m.get('folder','').upper()=='INBOX': candidates[uid]=m
    limit=min(200,max(1,int(os.getenv('CSS_WEB_BODY_BATCH','100'))))
    now=dt.datetime.now(src.KST).isoformat()
    output=[]
    with imaplib.IMAP4_SSL('imap.exmail.qq.com',993,timeout=45) as im:
        im.login(os.environ['CSS_QQ_MAIL_ADDRESS'],os.environ['CSS_QQ_MAIL_AUTH_CODE'])
        state,_=im.select('INBOX',readonly=True)
        if state!='OK': raise RuntimeError('Inbox unavailable')
        _,uv=im.response('UIDVALIDITY'); valid=uv[0].decode() if uv and uv[0] else ''
        if not valid: raise RuntimeError('UIDVALIDITY missing')
        for uid,m in sorted(candidates.items(),key=lambda item:item[1].get('received_at',''),reverse=True)[:limit]:
            if m.get('uidvalidity')!=valid: continue
            state,data=im.uid('FETCH',m['imap_uid'],'(BODY.PEEK[])')
            if state!='OK': continue
            raw=b''.join(x[1] for x in data or [] if isinstance(x,tuple) and isinstance(x[1],bytes))
            if not raw: continue
            msg=email.message_from_bytes(raw,policy=policy.default)
            if str(msg.get('Message-ID','')).strip()!=m.get('message_id','').strip(): continue
            body=body_text(msg)
            if not body: continue
            output.append([uid,m.get('message_id',''),m.get('ingest_key',''),m.get('received_at',''),m.get('from_email',''),str(msg.get('From','')),m.get('recipient_to',''),m.get('cc',''),m.get('subject',''),body,'INBOUND','','','','','','','','',now,now,'WEB_REVIEW_CACHE','',''])
    # Recheck the queue before caching; never change any review/exclusion decisions.
    current={r[0] for r in read(SFDC,"'Unanswered Emails'!I2:I1300") if r}
    cache=read(SFDC,"'CSS Mail Inbox Raw'!A2:J10000")
    complete={r[0] for r in cache if len(r)>9 and r[9]}
    rows=[r for r in output if r[0] in current and r[0] not in complete]
    # Fill an existing empty-body row in place instead of creating duplicate UIDs.
    positions={r[0]:i+2 for i,r in enumerate(cache) if r}
    for row in rows:
        if row[0] in positions:
            src.api(s,'PUT',url(SFDC,"'CSS Mail Inbox Raw'!A"+str(positions[row[0]]))+ '?valueInputOption=RAW',json={'values':[row]})
    new=[r for r in rows if r[0] not in positions]
    if len(cache)+len(new)>9999: raise RuntimeError('Cache capacity exceeded')
    if new: src.api(s,'POST',url(SFDC,"'CSS Mail Inbox Raw'!A:X")+':append?valueInputOption=RAW&insertDataOption=INSERT_ROWS',json={'values':new})
    print('CSS_WEB_BODY_SYNC fetched='+str(len(output))+' cached='+str(len(rows))+' pending='+str(len(wanted)-len(rows)))
if __name__=='__main__': main()
