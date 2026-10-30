"""Offline tests: MIME, owner-scoped staging, UID parity and partial-body safety."""
import datetime as dt
import importlib.util
import sys
import types
import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote

stub=types.ModuleType('incremental_sync')
stub.COLS=["ingest_key","message_id","imap_uid","folder","uidvalidity",
           "received_at","from_email","recipient_to","cc","subject",
           "amea_numbers","h_project_numbers","sam_numbers","batch_numbers",
           "fetched_at_utc","direction","in_reply_to","references"]
stub.KST=dt.timezone(dt.timedelta(hours=9))
stub.BOOK="1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY"
sys.modules['incremental_sync']=stub
spec=importlib.util.spec_from_file_location(
    'web_body_sync',Path(__file__).with_name('web_body_sync.py'))
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

OWNER="taehoon.kim@novogene.com"
NOW=dt.datetime(2026,10,30,8,0,tzinfo=dt.timezone.utc)
STAMP="2026-10-30T06:00:00+00:00"
CACHE_HEAD=mod.HEADERS+["Direction","Reply Evidence","Project IDs",
          "Lead ID","Opportunity ID","Quote ID","Tax Invoice Flag",
          "Invoice Amount KRW","Source Account","Ingested At KST",
          "Updated At KST","Classification","Exclude Flag","Other"]


def mail(uid,folder="INBOX",direction="INBOUND",owner=True,when=None):
    address=OWNER if owner else "colleague@novogene.com"
    to=address if direction=="INBOUND" else "customer@yonsei.ac.kr"
    sender="customer@yonsei.ac.kr" if direction=="INBOUND" else address
    date=when or STAMP
    return [folder+"|123|"+uid,"<m"+uid+"@test.example>",uid,folder,"123",
            date,sender,to,"","Subject "+uid,"","","","",STAMP,direction,"",""]


def cache_row(uid,body="",folder="INBOX"):
    r=[""]*24
    r[0]=("inbox:" if folder=="INBOX" else "sent:")+uid
    r[1]="<m"+uid+"@test.example>"
    r[2]=folder+"|123|"+uid
    r[9]=body
    r[21]="HEADER_ONLY_BODY_PENDING" if not body else "WEB_REVIEW_CACHE"
    return r


class BodyTests(unittest.TestCase):
    def test_plain_preferred_over_html_and_attachment(self):
        raw=b'MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=x\n\n--x\nContent-Type: text/plain; charset=utf-8\n\nCustomer body\n--x\nContent-Type: text/html\n\n<p>Duplicate</p>\n--x\nContent-Type: text/plain\nContent-Disposition: attachment; filename="secret.txt"\n\nAttachment\n--x--'
        self.assertEqual(mod.body_text(BytesParser(policy=policy.default).parsebytes(raw)),'Customer body')

    def test_html_only_no_active_content(self):
        raw=b'Content-Type: text/html\n\n<p>Hello<br>World</p><script>bad()</script><style>hidden</style>'
        self.assertEqual(mod.body_text(BytesParser(policy=policy.default).parsebytes(raw)),'Hello\nWorld')

    def test_mime_crlf_unicode_and_google_sheets_line_ending_parity(self):
        self.assertEqual(mod.normalize_body(" A\r\nB\rC\x00\u0007 "), " A\nB\nC ")
        self.assertEqual(mod.normalize_body("e\u0301"), "\u00e9")

    def test_sheet_cell_limit(self):
        msg=BytesParser(policy=policy.default).parsebytes(b'Content-Type: text/plain\n\n'+b'a'*60000)
        self.assertEqual(len(mod.body_text(msg)),45000)
    def test_exact_readback_preserves_final_whitespace_on_45000_char_cells(self):
        # Previously value(...).strip() erased the final whitespace byte.
        source='x'*44999+' '
        self.assertEqual(len(source),45000)
        self.assertEqual(mod.exact_body_cell([source]),source)
        self.assertNotEqual(mod.value([source],0),source)
        self.assertTrue(mod.body_matches(source,mod.exact_body_cell([source])))
        self.assertFalse(mod.body_matches(source,source[:-1]))
        self.assertFalse(mod.body_matches(source,'x'*44999+chr(10)))
        self.assertTrue(mod.body_matches('a'+chr(13)+chr(10)+'b',
                                         'a'+chr(10)+'b'))
        self.assertTrue(mod.body_matches('e'+chr(0x301),chr(0xe9)))

    def test_new_owner_mail_inbox_sent_and_queue_not_just_unanswered(self):
        ingest=[stub.COLS,
                mail("41012"),
                mail("41013",folder="Sent Messages",direction="OUTBOUND"),
                mail("41014",owner=False),
                mail("40941",owner=False),
                mail("41015",owner=True)]
        cache=[CACHE_HEAD,cache_row("41015","already complete")]
        queue=[[""]*8+["Thread UID"],[""]*8+["inbox:40941"]]
        selected,positions,total=mod.select_candidates(
            ingest,cache,queue,OWNER,NOW,60,80)
        ids={x for x,_ in selected}
        self.assertEqual(ids,{"inbox:41012","sent:41013","inbox:40941"})
        self.assertEqual(total,3)
        self.assertEqual(len(positions),1)

    def test_verified_empty_mime_checkpoint_exits_retry_pool(self):
        empty=cache_row("41012")
        empty[21]="BODY_EMPTY_MIME"
        selected,positions,total=mod.select_candidates(
            [stub.COLS,mail("41012")],[CACHE_HEAD,empty],
            [[""]*8+["Thread UID"],[""]*8+["inbox:41012"]],
            OWNER,NOW)
        self.assertEqual((len(selected),total),(0,0))
        self.assertIn("inbox:41012",positions)

    def test_oversize_terminal_marker_requires_verified_bounded_header(self):
        meta=mail("41012")
        header=(b'Message-ID: <m41012@test.example>\n'
                b'From: customer@yonsei.ac.kr\n'
                b'Subject: Subject 41012\n\n')
        msg=mod.verified_oversize_header(header+b'A'*200000,meta)
        self.assertIsNotNone(msg)
        self.assertEqual(msg['Message-ID'],"<m41012@test.example>")
        self.assertFalse(msg.get_payload())
        self.assertIsNone(mod.verified_oversize_header(
            header.replace(b'm41012',b'm99999')+b'A'*200000,meta))
        self.assertIsNone(mod.verified_oversize_header(b'X'*mod.MAX_HEADER_BYTES+b'\n\n',meta))
        terminal=cache_row("41012")
        terminal[21]='BODY_OVERSIZE_MIME'
        selected,stored,total=mod.select_candidates(
            [stub.COLS,meta],[CACHE_HEAD,terminal],
            [[""]*8+["Thread UID"],[""]*8+["inbox:41012"]],
            OWNER,NOW)
        self.assertEqual((len(selected),total),(0,0))
        self.assertIn("inbox:41012",stored)

    def test_verified_oversize_mime_is_checkpointed_without_false_body(self):
        ingest=[stub.COLS,mail("41012"),mail("41013")]
        records=[CACHE_HEAD[:]]
        audit=[mod.BACKFILL_HEADER[:]]
        mailtext=(b'Message-ID: <m41012@test.example>\n'
                  b'From: customer@yonsei.ac.kr\n\nhello')
        large=(b'Message-ID: <m41013@test.example>\n'
               b'From: customer@yonsei.ac.kr\n\n'+b'X'*200)
        seen_fetch=[]
        class FakeImap:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def login(self,*args):return None
            def select(self,folder,readonly=False):
                self.readonly=readonly
                return 'OK',[]
            def response(self,name):return 'UIDVALIDITY',[b'123']
            def uid(self,method,uid,query):
                seen_fetch.append(str(uid))
                return 'OK',[(b'BODY.PEEK[]',large if str(uid)=='41013' else mailtext)]
        def api(_session,method,url,**kwargs):
            u=unquote(url)
            if method=='GET':
                if "'Unanswered Emails'!A1:V1300" in u:return {'values':[[""]*8+["Thread UID"]]}
                if "'CSS Git Ingest'!A1:R100000" in u:return {'values':ingest}
                if "'CSS Mail Backfill Status'!A1:O1" in u:return {'values':[audit[0]]}
                if "'CSS Mail Backfill Status'!A2:O2" in u:return {'values':audit[1:]}
                if "'CSS Mail Inbox Raw'!A1:X10000" in u:return {'values':records}
                if "'CSS Mail Inbox Raw'!A1:A" in u:return {'values':[[r[0]] for r in records]}
                if "'CSS Mail Inbox Raw'!J1:J" in u:return {'values':[[r[9]] for r in records]}
                if "'CSS Mail Inbox Raw'!V1:V" in u:return {'values':[[r[21]] for r in records]}
                raise AssertionError('Unexpected read')
            if method=='POST' and "'CSS Mail Inbox Raw'!A:X:append" in u:
                records.extend(kwargs['json']['values'])
                return {}
            if method=='PUT' and "'CSS Mail Backfill Status'!A2:O2" in u:
                audit[:]=[audit[0],kwargs['json']['values'][0]]
                return {}
            raise AssertionError('Unexpected write')
        with patch.object(stub,'authorize',return_value=object(),create=True), \
             patch.object(stub,'api',side_effect=api,create=True), \
             patch.object(mod.imaplib,'IMAP4_SSL',return_value=FakeImap()), \
             patch.object(mod,'MAX_FETCH_BYTES',110), \
             patch.dict(mod.os.environ,{'CSS_QQ_MAIL_ADDRESS':OWNER,
                                       'CSS_QQ_MAIL_AUTH_CODE':'TEST_DUMMY',
                                       'CSS_WEB_BODY_BATCH':'80'}):
            mod.sync()
        self.assertEqual(len(records),3)
        by_uid={r[0]:r for r in records[1:]}
        self.assertEqual(by_uid['inbox:41012'][21],'WEB_REVIEW_CACHE')
        self.assertEqual(by_uid['inbox:41013'][21],'BODY_OVERSIZE_MIME')
        self.assertEqual(by_uid['inbox:41013'][9],'')
        self.assertEqual(audit[1][1],'WINDOW_CAUGHT_UP')
        self.assertEqual(audit[1][3:8],[2,1,0,0,0])
        self.assertIn('oversize_MIME_body_unavailable=1',audit[1][14])
        self.assertEqual(sorted(seen_fetch),['41012','41013'])
        selected,_,total=mod.select_candidates(
            ingest,records,[[""]*8+["Thread UID"]],OWNER,NOW)
        self.assertEqual((len(selected),total),(0,0))

    def test_owner_matching_is_exact_not_substring(self):
        self.assertEqual(mod.addresses(OWNER.upper(),"Someone <"+OWNER+">"),{OWNER})
        self.assertNotIn(OWNER,mod.addresses("not-"+OWNER))

    def test_duplicate_cache_or_uid_mismatch_blocks(self):
        ingest=[stub.COLS,mail("41012")]
        cache=[CACHE_HEAD,cache_row("41012"),cache_row("41012")]
        with self.assertRaisesRegex(RuntimeError,"WEB_MAIL_DUPLICATE_UID"):
            mod.select_candidates(ingest,cache,[[""]*8+["Thread UID"]],OWNER,NOW)
        bad=mail("41012"); bad[0]="INBOX|123|99999"
        with self.assertRaisesRegex(RuntimeError,"QQ_INGEST_SOURCE_KEY_MISMATCH"):
            mod.select_candidates([stub.COLS,bad],[CACHE_HEAD],
                [[""]*8+["Thread UID"]],OWNER,NOW)

    def test_message_id_and_header_fallback(self):
        msg=BytesParser(policy=policy.default).parsebytes(
            b'Message-ID: <m41012@test.example>\nFrom: customer@yonsei.ac.kr\nSubject: Subject 41012\n\nHello')
        r=mail("41012")
        self.assertTrue(mod.validate_message(msg,r))
        r[1]="<wrong@test.example>"
        self.assertFalse(mod.validate_message(msg,r))
        r[1]=""
        self.assertTrue(mod.validate_message(msg,r))
        r[9]="Other subject"
        self.assertFalse(mod.validate_message(msg,r))

    def test_received_time_and_body_row_provenance(self):
        msg=BytesParser(policy=policy.default).parsebytes(
            b'From: Customer <customer@yonsei.ac.kr>\nSubject: Subject 41012\n\nHello')
        row=mod.make_row("inbox:41012",mail("41012"),msg,"Body",NOW.isoformat())
        self.assertEqual(row[0],"inbox:41012")
        self.assertEqual(row[3],"2026-10-30T15:00:00+09:00")
        self.assertEqual(row[9],"Body")
        self.assertEqual(row[18],"QQ_IMAP_UID_VERIFIED")
        self.assertEqual(row[21],"WEB_REVIEW_CACHE")
        self.assertEqual(len(row),24)

    def test_live_style_sync_fills_header_only_row_without_changing_exclusions(self):
        current=dt.datetime.now(dt.timezone.utc).isoformat()
        meta=mail("41012",when=current)
        raw_headers=cache_row("41012")
        raw_headers[18]="QQ_CSS_GIT_INGEST_HEADER"
        raw_headers[22]="KEEP_EXCLUSION"
        raw_headers[23]="HUMAN_REVIEW_UNCHANGED"
        records=[CACHE_HEAD,raw_headers]
        inbox=[[""]*8+["Thread UID"]]
        ingest=[stub.COLS,meta]
        mime=(b'Message-ID: <m41012@test.example>\n'
              b'From: customer@yonsei.ac.kr\n'
              b'To: taehoon.kim@novogene.com\n'
              b'Subject: Subject 41012\n'
              b'Content-Type: text/plain; charset=utf-8\n\n'
              b'Updated customer body.\r\nSecond line')
        operations=[]
        timeouts=[]
        audit=[mod.BACKFILL_HEADER]

        class FakeImap:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def login(self,*args):return None
            def select(self,folder,readonly=False):
                self.selected=folder
                self.readonly=readonly
                return ('OK',[])
            def response(self,kind):return ('UIDVALIDITY',[b'123'])
            def uid(self,method,uid,query):
                self.fetch=(method,uid,query)
                return ('OK',[(b'RFC822',mime)])

        imap=FakeImap()

        def api(_sess,method,url,**kwargs):
            operations.append((method,unquote(url)))
            u=unquote(url)
            if method=='GET':
                if "'Unanswered Emails'!A1:V1300" in u:return {'values':inbox}
                if "'CSS Git Ingest'!A1:R100000" in u:return {'values':ingest}
                if "'CSS Mail Backfill Status'!A1:O1" in u:
                    return {'values':[audit[0]]}
                if "'CSS Mail Backfill Status'!A2:O2" in u:
                    return {'values':[audit[1]] if len(audit)>1 else []}
                if "'CSS Mail Inbox Raw'!A1:X10000" in u:return {'values':records}
                if "'CSS Mail Inbox Raw'!A1:A" in u:
                    if not timeouts:
                        timeouts.append('transient_read_timeout')
                        raise TimeoutError('test transient Sheets read timeout')
                    return {'values':[[r[0]] for r in records]}
                if "'CSS Mail Inbox Raw'!J1:J" in u:
                    return {'values':[[r[9].replace('\n','\r\n')] for r in records]}
                if "'CSS Mail Inbox Raw'!V1:V" in u:
                    return {'values':[[r[21]] for r in records]}
                raise AssertionError("Unexpected read "+u)
            if method=='PUT' and "'CSS Mail Backfill Status'!A2:O2" in u:
                if len(audit)==1:audit.append(kwargs['json']['values'][0])
                else:audit[1]=kwargs['json']['values'][0]
                return {}
            if u.endswith('/values:batchUpdate'):
                for patch_row in kwargs['json']['data']:
                    rng=patch_row['range']
                    values=patch_row['values'][0]
                    if rng.endswith('!F2'):records[1][5]=values[0]
                    elif rng.endswith('!J2'):records[1][9]=values[0]
                    elif rng.endswith('!U2:V2'):
                        records[1][20:22]=values
                    else:raise AssertionError(rng)
                return {}
            raise AssertionError("No accidental append or unrelated mutation "+u)

        with patch.object(stub,'authorize',return_value=object(),create=True), \
             patch.object(stub,'api',side_effect=api,create=True), \
             patch.object(mod.imaplib,'IMAP4_SSL',return_value=imap), \
             patch.object(mod.time,'sleep',return_value=None), \
             patch.dict(mod.os.environ,{'CSS_QQ_MAIL_ADDRESS':OWNER,
                                       'CSS_QQ_MAIL_AUTH_CODE':'TEST_DUMMY',
                                       'CSS_WEB_BODY_BATCH':'80'}):
            mod.sync()
        self.assertEqual(timeouts,['transient_read_timeout'])
        self.assertEqual(audit[1][1],'WINDOW_CAUGHT_UP')
        self.assertEqual(audit[1][3:8],[1,1,0,0,0])
        self.assertTrue(imap.readonly)
        self.assertEqual(imap.fetch,('FETCH','41012','(BODY.PEEK[])'))
        self.assertEqual(records[1][9],'Updated customer body.\nSecond line')
        self.assertEqual(records[1][21],'WEB_REVIEW_CACHE')
        self.assertEqual(records[1][22],'KEEP_EXCLUSION')
        self.assertEqual(records[1][23],'HUMAN_REVIEW_UNCHANGED')
        self.assertEqual(records[1][18],'QQ_CSS_GIT_INGEST_HEADER')
        self.assertEqual(len([op for op in operations if op[0]=='POST']),1)
        self.assertTrue(any("'CSS Mail Inbox Raw'!A1:A4" in url for _,url in operations))
        self.assertFalse(any("'CSS Mail Inbox Raw'!J1:J10000" in url for _,url in operations))

    def test_progress_audit_distinguishes_mime_no_text_pending_and_source_backlog(self):
        records=[["uid"],["inbox:41012"],["inbox:41013"],["inbox:41014"]]
        bodies=[["body"],["hello"],[],[]]
        status=[["status"],["WEB_REVIEW_CACHE"],["BODY_EMPTY_MIME"],
                ["HEADER_ONLY_BODY_PENDING"]]
        row=mod.progress_record([stub.COLS,mail("41012")],records,bodies,status,
                                150,80,57,23,{},NOW,"12345")
        self.assertEqual(row[1],"BACKFILL_ACTIVE")
        self.assertEqual(row[3:12],[3,1,1,1,150,80,57,23,0])
        self.assertEqual(row[13],"12345")
        row2=mod.progress_record([stub.COLS,mail("41012")],records,bodies,status,
                                 0,0,0,0,{},NOW,"")
        self.assertEqual(row2[1],"WINDOW_CAUGHT_UP")
        with self.assertRaisesRegex(RuntimeError,"DUPLICATE_UID"):
            mod.progress_record([stub.COLS], [["uid"],["inbox:1"],["inbox:1"]],
                                [["body"],[],[]],[["status"],[],[]],
                                0,0,0,0,{},NOW,"")

    def test_old_queue_and_owner_outside_lookback(self):
        old=(NOW-dt.timedelta(days=80)).isoformat()
        inbox=mail("38233",owner=False,when=old)
        mine=mail("38234",owner=True,when=old)
        queue=[[""]*8+["Thread UID"],[""]*8+["inbox:38233"]]
        selected,_,_=mod.select_candidates(
            [stub.COLS,inbox,mine],[CACHE_HEAD],queue,OWNER,NOW)
        self.assertEqual([v[0] for v in selected],["inbox:38233"])


if __name__=='__main__':
    unittest.main()
