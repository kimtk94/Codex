"""Pure offline tests for bounded, privacy-safe serial MIME backfill."""
import importlib.util
import pathlib
import subprocess
import unittest
from types import SimpleNamespace

FILE=pathlib.Path(__file__).with_name("web_body_serial_runner.py")
spec=importlib.util.spec_from_file_location("web_body_serial_runner",FILE)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def result(selected=160,eligible=2221,fetched=150,errors=10,
           types="EMPTY_BODY",state="PARTIAL",exit_code=0):
    return SimpleNamespace(returncode=exit_code,
       stdout=(f"CSS_WEB_BACKFILL_STATUS state=BACKFILL_ACTIVE cache_total=1689\n"
               f"CSS_WEB_BODY_SYNC_{state} selected={selected} eligible={eligible}"
               f" fetched={fetched} updated=0 inserted=150 empty_mime=10"
               f" empty_existing=0 errors={errors} error_types={types}\n"))


def fake_runner(items,calls):
    def runner(argv,**kwargs):
        calls.append((argv,kwargs))
        return items[len(calls)-1]
    return runner


class SerialTests(unittest.TestCase):
    def test_three_verified_batches_recover_480_candidates(self):
        calls=[]
        responses=[result(eligible=2221),result(eligible=2061),result(eligible=1901)]
        outcome=m.execute(3,fake_runner(responses,calls),monotonic=lambda:0)
        self.assertEqual(outcome,0)
        self.assertEqual(len(calls),3)
        self.assertTrue(all(c[1]["timeout"]<=480 for c in calls))
        self.assertTrue(all(c[1]["check"] is False for c in calls))
        self.assertTrue(all(c[1]["text"] is True for c in calls))

    def test_stop_when_source_queue_is_empty_or_final_batch(self):
        for cases in [[result(selected=0,eligible=0,fetched=0,errors=0,types="",state="PASS")],
                      [result(selected=21,eligible=21,fetched=18,errors=3,types="EMPTY_BODY")]]:
            calls=[]
            self.assertEqual(m.execute(3,fake_runner(cases,calls),lambda:0),0)
            self.assertEqual(len(calls),1)

    def test_failed_first_or_second_batch_stops_without_duplicate_fetch(self):
        for responses in [[result(exit_code=1)],
                          [result(),result(exit_code=2)]]:
            calls=[]
            self.assertEqual(m.execute(3,fake_runner(responses,calls),lambda:0),2)
            self.assertEqual(len(calls),len(responses))

    def test_non_mime_fetch_errors_stop_and_mark_job_failed(self):
        calls=[]
        wrong=result(fetched=140,errors=20,types="EMPTY_BODY,FETCH_FAILED")
        self.assertEqual(m.execute(3,fake_runner([wrong],calls),lambda:0),2)
        self.assertEqual(len(calls),1)

    def test_ambiguous_or_fabricated_result_is_failure(self):
        calls=[]
        fake=SimpleNamespace(returncode=0,stdout="EMAIL UID: secret\n")
        self.assertEqual(m.execute(3,fake_runner([fake],calls),lambda:0),2)
        self.assertEqual(len(calls),1)
        with self.assertRaisesRegex(ValueError,"COUNTS_INVALID"):
            m.summary_from_output(result(selected=160,eligible=100).stdout)
        with self.assertRaisesRegex(ValueError,"SCHEMA_MISSING"):
            m.summary_from_output(result().stdout+result().stdout)

    def test_timeout_and_invalid_loop_count_fail_closed(self):
        def timeout_runner(*_args,**_kwargs):
            raise subprocess.TimeoutExpired("safe",5)
        self.assertEqual(m.execute(3,timeout_runner,lambda:0),3)
        with self.assertRaisesRegex(ValueError,"CYCLE_LIMIT"):
            m.execute(4,timeout_runner,lambda:0)

    def test_deadline_leaves_budget_for_health_reporting(self):
        calls=[]
        times=iter([0,0,1000])
        self.assertEqual(m.execute(3,fake_runner([result()],calls),
                                   monotonic=lambda:next(times)),0)
        self.assertEqual(len(calls),1)

    def test_source_workflow_lock_and_read_only_policy(self):
        repo=pathlib.Path(__file__).resolve().parents[2]
        w=(repo/".github/workflows/css-web-body-sync.yml").read_text()
        self.assertIn("css-qq-ci-",w)
        self.assertIn("'css-qq-mail-readonly'",w)
        self.assertIn("CSS_WEB_BODY_BATCH: '160'",w)
        self.assertIn("CSS_WEB_BODY_SERIAL_CYCLES: '3'",w)
        self.assertIn("python automation/css_mail/web_body_serial_runner.py",w)
        self.assertIn("if: always()",w)
        self.assertNotIn("send_customer_mail.py",w)


if __name__=="__main__":
    unittest.main()
