#!/usr/bin/env python3
"""Offline reply-evidence tests; never connect to mail or Sheets."""
import datetime as dt
import pathlib
import sys
import types
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# The business rules must run without secrets, SMTP, IMAP, or Google clients.
src = types.ModuleType("incremental_sync")
src.KST = dt.timezone(dt.timedelta(hours=9))
src.BOOK = "TEST_SHEET"
src.COLS = [
    "ingest_key","message_id","imap_uid","folder","uidvalidity","received_at",
    "from_email","recipient_to","cc","subject","amea_numbers","h_project_numbers",
    "sam_numbers","batch_numbers","fetched_at_utc","direction","in_reply_to",
    "references"
]
sys.modules["incremental_sync"] = src
sys.modules["canonical_mail_reader"] = types.ModuleType("canonical_mail_reader")

import unanswered_reply_review as review

NOW = dt.datetime(2026,11,10,8,tzinfo=dt.timezone.utc)
ME = "taehoon@novogene.com"
CLIENT = "contact@example.org"

def mail(key, when, *, direction="INBOUND", sender=CLIENT, to=ME,
         subject="Service quote", mid=None, reply="", refs="", cc=""):
    return dict(
        ingest_key="INBOX|abc|"+key, imap_uid=key, direction=direction,
        from_email=sender, recipient_to=to, cc=cc, subject=subject,
        message_id=mid if mid is not None else "<"+key+"@example.org>",
        in_reply_to=reply, references=refs, received_at=when.isoformat(),
        fetched_at_utc=NOW.isoformat(), amea_numbers="",h_project_numbers="",
        sam_numbers="",batch_numbers=""
    )

def run(messages, **kwargs):
    return review.analyze(messages, own_address=ME, now=NOW, **kwargs)

class ReplyAudit(unittest.TestCase):
    def test_reply_with_exact_message_id_suppresses_only_answered_thread(self):
        incoming=mail("101",NOW-dt.timedelta(days=4),mid="<abc@one>")
        reply=mail("205",NOW-dt.timedelta(days=3),direction="OUTBOUND",
                   sender=ME,to=CLIENT,mid="<our@one>",reply="<abc@one>")
        items,counts=run([incoming,reply])
        self.assertEqual(items,[])
        self.assertEqual(counts["EXACT_REPLY_EVIDENCE"],1)

    def test_subject_only_match_is_not_proof_of_reply(self):
        incoming=mail("101",NOW-dt.timedelta(days=4),mid="<abc@one>")
        # Deliberately unrelated message with same subject and recipient.
        unrelated=mail("205",NOW-dt.timedelta(days=3),direction="OUTBOUND",
                       sender=ME,to=CLIENT,reply="<other@one>")
        rows,counts=run([incoming,unrelated])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][6],"POSSIBLE_SUBJECT_MATCH")
        self.assertEqual(counts["EXACT_REPLY_EVIDENCE"],0)

    def test_new_customer_followup_reopens_thread(self):
        first=mail("101",NOW-dt.timedelta(days=8),mid="<root@one>")
        latest=mail("102",NOW-dt.timedelta(days=4),mid="<new@one>",
                    refs="<root@one>",reply="<root@one>")
        # This outbound mentions the older question but NOT the renewed one.
        old_reply=mail("205",NOW-dt.timedelta(days=3),direction="OUTBOUND",
                       sender=ME,to=CLIENT,reply="<root@one>")
        rows,counts=run([first,latest,old_reply])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][10],"inbox:102")
        self.assertEqual(rows[0][6],"POSSIBLE_SUBJECT_MATCH")
        self.assertEqual(counts["THREADS_REVIEWED"],1)

    def test_independent_same_subject_conversations_stay_separate(self):
        messages=[
            mail("101",NOW-dt.timedelta(days=7),mid="<first@one>"),
            mail("102",NOW-dt.timedelta(days=6),mid="<second@one>")
        ]
        rows,counts=run(messages)
        self.assertEqual(len(rows),2)
        self.assertEqual(counts["THREADS_REVIEWED"],2)

    def test_exclusion_and_exact_sender_pattern(self):
        messages=[
            mail("101",NOW-dt.timedelta(days=7)),
            mail("102",NOW-dt.timedelta(days=6),sender="spam@example.org")
        ]
        exclusions=[{"uid":"inbox:101","restore":"FALSE"}]
        senders=[{"sender_pattern":"spam@example.org","match_type":"exact",
                  "restore":"FALSE"}]
        rows,counts=run(messages,mail_exclusions=exclusions,sender_exclusions=senders)
        self.assertEqual(rows,[])
        self.assertEqual(counts["EXCLUDED_MESSAGES"],2)

    def test_60_day_maximum_and_own_recipient_filter(self):
        messages=[
            mail("101",NOW-dt.timedelta(days=61)),
            mail("102",NOW-dt.timedelta(days=3),to="somebody@novogene.com"),
            mail("103",NOW-dt.timedelta(days=3),cc=ME,to="team@novogene.com")
        ]
        rows,_=run(messages,lookback_days=180)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][10],"inbox:103")

    def test_delegated_customer_reply_is_evidence(self):
        incoming=mail("101",NOW-dt.timedelta(days=4),mid="<from-customer@x>")
        delegate=mail("205",NOW-dt.timedelta(days=3),direction="INBOUND",
                      sender="jiin.yoo@novogene.com",to=CLIENT,cc=ME,
                      reply="<from-customer@x>")
        rows,counts=run([incoming,delegate])
        self.assertEqual(rows,[])
        self.assertEqual(counts["EXACT_REPLY_EVIDENCE"],1)

    def test_priority_and_no_unverified_confirmation(self):
        messages=[
            mail("101",NOW-dt.timedelta(days=1)),
            mail("102",NOW-dt.timedelta(days=4)),
            mail("103",NOW-dt.timedelta(days=7))
        ]
        rows,counts=run(messages)
        self.assertEqual([r[0] for r in rows],["P0","P1","WATCH"])
        self.assertTrue(all(r[8]=="CANDIDATE_NOT_CONFIRMED" for r in rows))
        self.assertEqual(counts["NO_REPLY_EVIDENCE"],3)

    def test_thread_header_parsing_is_exact(self):
        self.assertEqual(review.ids("<abc@x> <def@y>"),{"<abc@x>","<def@y>"})
        self.assertNotIn("<abc@x>",review.ids("<abc@xyz>"))
        self.assertEqual(review.ids("abc@x"),{"<abc@x>"})

    def test_reject_missing_own_mailbox(self):
        with self.assertRaises(ValueError):
            review.analyze([],own_address="",now=NOW)

if __name__=="__main__":
    unittest.main()
