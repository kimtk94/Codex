#!/usr/bin/env python3
"""No mail contents or external credentials needed for catch-up tests."""
import os
import imaplib
import unittest
from unittest import mock
import qq_mail_catchup_drain as d

class CatchupTests(unittest.TestCase):
    def test_six_rounds_with_full_batches(self):
        calls=[]
        def run(mode):
            calls.append(mode)
            return {"added":3000,"scanned":3000}
        with mock.patch.dict(os.environ,{"QQ_CATCHUP_MAX_ROUNDS":"6",
                                         "FEISHU_MAIL_BACKFILL_TOTAL":"3000"}):
            result=d.drain(run)
        self.assertEqual(result,{"rounds":6,"added":18000})
        self.assertEqual(calls,["backfill2026"]*6)

    def test_early_stop_avoids_unnecessary_runs(self):
        batches=iter([{"added":2943,"scanned":3000},
                      {"added":2,"scanned":3000},
                      {"added":0,"scanned":200},
                      {"added":100,"scanned":100}])
        with mock.patch.dict(os.environ,{"QQ_CATCHUP_MAX_ROUNDS":"6",
                                         "FEISHU_MAIL_BACKFILL_TOTAL":"3000"}):
            result=d.drain(lambda mode:next(batches))
        self.assertEqual(result,{"rounds":3,"added":2945})

    def test_partial_batch_not_mistaken_for_completion(self):
        seq=iter([{"added":100,"scanned":120},
                  {"added":500,"scanned":600}])
        with mock.patch.dict(os.environ,{"QQ_CATCHUP_MAX_ROUNDS":"2",
                                         "FEISHU_MAIL_BACKFILL_TOTAL":"3000"}):
            self.assertEqual(d.drain(lambda _:next(seq))["rounds"],2)

    def test_fails_closed_on_invalid_counts(self):
        with mock.patch.dict(os.environ,{"QQ_CATCHUP_MAX_ROUNDS":"1",
                                         "FEISHU_MAIL_BACKFILL_TOTAL":"3000"}):
            for result in ({"added":3001,"scanned":3001},
                           {"added":-1,"scanned":1},None,
                           {"added":2,"scanned":1}):
                with self.subTest(result=result):
                    with self.assertRaises(d.q.SafeError):
                        d.drain(lambda _:result)

    def test_transient_imap_abort_retries_then_succeeds(self):
        attempts=[]
        def flaky(mode):
            attempts.append(mode)
            if len(attempts)==1:
                raise imaplib.IMAP4.abort("QQ socket dropped")
            return {"added":257,"scanned":260}
        with mock.patch.dict(os.environ,{"QQ_CATCHUP_MAX_ROUNDS":"1",
                                         "FEISHU_MAIL_BACKFILL_TOTAL":"3000"}), \
             mock.patch.object(d.time,"sleep") as delay:
            result=d.drain(flaky)
        self.assertEqual(result,{"rounds":1,"added":257})
        self.assertEqual(len(attempts),2)
        delay.assert_called_once_with(20)

    def test_repeated_imap_abort_stops_after_two_retries(self):
        attempts=[]
        def fail(mode):
            attempts.append(mode)
            raise imaplib.IMAP4.abort("QQ socket dropped")
        with mock.patch.dict(os.environ,{"QQ_CATCHUP_MAX_ROUNDS":"6",
                                         "FEISHU_MAIL_BACKFILL_TOTAL":"3000"}), \
             mock.patch.object(d.time,"sleep") as delay:
            with self.assertRaises(imaplib.IMAP4.abort):
                d.drain(fail)
        self.assertEqual(len(attempts),3)
        self.assertEqual(delay.call_count,2)

    def test_no_swallow_ingest_exceptions(self):
        def fail(_):
            raise d.q.SafeError("IMAP_FETCH_FAILED")
        with mock.patch.dict(os.environ,{"QQ_CATCHUP_MAX_ROUNDS":"6",
                                         "FEISHU_MAIL_BACKFILL_TOTAL":"3000"}):
            with self.assertRaisesRegex(d.q.SafeError,"IMAP_FETCH_FAILED"):
                d.drain(fail)

    def test_refuse_more_than_six_rounds_or_3000(self):
        for override in ({"QQ_CATCHUP_MAX_ROUNDS":"7"},
                         {"FEISHU_MAIL_BACKFILL_TOTAL":"3001"},
                         {"QQ_CATCHUP_MAX_ROUNDS":"0"}):
            with mock.patch.dict(os.environ,{"QQ_CATCHUP_MAX_ROUNDS":"6",
                 "FEISHU_MAIL_BACKFILL_TOTAL":"3000",**override}):
                with self.assertRaisesRegex(d.q.SafeError,"CATCHUP_LIMIT"):
                    d.drain(lambda _:{"added":0,"scanned":0})

if __name__=="__main__":
    unittest.main()
