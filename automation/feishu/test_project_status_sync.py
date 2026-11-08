#!/usr/bin/env python3
"""Synthetic Feishu project-state tests; no external Feishu or Sheet credentials."""
import pathlib, sys, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from project_status_sync import group, pick, normalize, status
from project_status_sync import api
from unittest.mock import Mock, patch
from requests.exceptions import ReadTimeout, ConnectionError as RequestConnectionError
class ProjectStates(unittest.TestCase):
    def test_independent_flags_both(self):
        self.assertEqual(status(True,True)[0],"P0_BOTH")
        self.assertEqual(status(True,False)[0],"P1_ETAX")
        self.assertEqual(status(False,True)[0],"P1_PAYMENT")
    def test_exact_project_ids_and_dedup(self):
        rows=[{"fields":{"Project Number":"AMEA2026102149"}},{"fields":{"Project Number":"AMEA2026102149"}},{"fields":{"Project Number":"AMEA2026102149-01"}}]
        groups,missing=group(rows,"Project Number")
        self.assertEqual(missing,0)
        self.assertEqual(len(groups),2)
        self.assertEqual(groups["AMEA2026102149"],2)
    def test_unknown_project_quarantined(self):
        groups,missing=group([{"fields":{"Project Number":None}},{"fields":{"Project Number":"unknown"}}],"Project Number")
        self.assertEqual(missing,2)
        self.assertFalse(groups)
    def test_column_alias(self):
        self.assertEqual(pick([{"field_name":"Project Number"}]),"Project Number")

class TransportRetries(unittest.TestCase):
    def test_get_read_timeout_retries_without_data_loss(self):
        session=Mock()
        good=Mock(ok=True,status_code=200,content=b'{}')
        good.json.return_value={"values":[["original"]]}
        session.request.side_effect=[ReadTimeout("transient"),good]
        with patch("project_status_sync.time.sleep") as sleep:
            observed=api(session,"GET","/values/test")
        self.assertEqual(observed["values"],[["original"]])
        self.assertEqual(session.request.call_count,2)
        self.assertEqual(sleep.call_count,1)

    def test_put_timeout_idempotent_payload_retried(self):
        session=Mock()
        good=Mock(ok=True,status_code=200,content=b'{}')
        good.json.return_value={}
        session.request.side_effect=[RequestConnectionError("broken"),good]
        body={"values":[["a",1]]}
        with patch("project_status_sync.time.sleep"):
            api(session,"PUT","/values/test",json=body)
        self.assertEqual(session.request.call_count,2)
        self.assertEqual(session.request.call_args_list[0].kwargs["json"],body)
        self.assertEqual(session.request.call_args_list[1].kwargs["json"],body)

    def test_non_idempotent_batch_never_replayed_after_timeout(self):
        session=Mock()
        session.request.side_effect=ReadTimeout("commit status unknown")
        with patch("project_status_sync.time.sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError,"SHEETS_TRANSPORT_POST_ReadTimeout"):
                api(session,"POST",":batchUpdate",json={"requests":[{"addSheet":{}}]})
        self.assertEqual(session.request.call_count,1)
        sleep.assert_not_called()

    def test_retryable_503_and_nonretryable_post_503(self):
        failed=Mock(ok=False,status_code=503,content=b'')
        good=Mock(ok=True,status_code=200,content=b'{}')
        good.json.return_value={"sheets":[]}
        session=Mock()
        session.request.side_effect=[failed,good]
        with patch("project_status_sync.time.sleep"):
            self.assertEqual(api(session,"GET","?fields=sheets.properties.title"),{"sheets":[]})
        self.assertEqual(session.request.call_count,2)
        session2=Mock()
        session2.request.return_value=failed
        with self.assertRaisesRegex(RuntimeError,"SHEETS_HTTP_503"):
            api(session2,"POST",":batchUpdate",json={"requests":[{"addSheet":{}}]})
        self.assertEqual(session2.request.call_count,1)
if __name__=="__main__":unittest.main()
