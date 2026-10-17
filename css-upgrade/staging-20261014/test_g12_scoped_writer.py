"""Offline G12 synthetic gspread-shaped adapter regression."""
import os
import unittest
from unittest.mock import patch
from g12_sheet_range_fence import WriteDenied
from g12_scoped_writer import ScopedWriter, SyntheticWorksheet

class WriterTests(unittest.TestCase):
    def setUp(self):
        flag = patch.dict(os.environ, {"G16_SYNTHETIC_ONLY":"1"})
        flag.start()
        self.addCleanup(flag.stop)
        self.ws = SyntheticWorksheet(1618938211,"CSS Contract-SIF Tracker",
                                     {2:"TEST-A",3:"TEST-B"})
        self.writer = ScopedWriter(self.ws)

    def test_valid_system_only_update(self):
        out = self.writer.update("D2:D3",[["SYN-A"],["SYN-B"]],
                                 record_ids=("TEST-A","TEST-B"))
        self.assertEqual(out["outcome"],"ACKNOWLEDGED_SYNTHETIC_WRITE")
        self.assertEqual(out["updatedCells"],2)

    def test_skip_prepayment_reason_and_full_row_denied(self):
        for rng in ("A2","B2","C2","A2:AL3"):
            with self.subTest(rng=rng):
                with self.assertRaises(WriteDenied):
                    self.writer.update(rng,[["SYN"]],
                                       record_ids=("TEST-A",))
        self.assertEqual(self.ws.calls,0)

    def test_reorder_denied_before_write(self):
        self.ws.registry[2] = "TEST-OTHER"
        with self.assertRaisesRegex(WriteDenied,"identity"):
            self.writer.update("D2",[["SYN"]],record_ids=("TEST-A",))
        self.assertEqual(self.ws.calls,0)

    def test_user_control_edited_at_write_preserved(self):
        self.ws.cells[(2,0)] = False
        original = self.ws.update
        def user_edit_then_update(*args,**kwargs):
            self.ws.cells[(2,0)] = True
            return original(*args,**kwargs)
        self.ws.update = user_edit_then_update
        self.writer.update("D2",[["SYN"]],record_ids=("TEST-A",))
        self.assertIs(self.ws.cells[(2,0)],True)

    def test_duplicate_or_real_record_key_denied(self):
        for keys in (("TEST-A","TEST-A"),("TEST-A","CUSTOMER-B")):
            with self.subTest(keys=keys):
                with self.assertRaises(WriteDenied):
                    self.writer.update("D2:D3",[["SYN"],["SYN"]],record_ids=keys)

    def test_row_shape_mismatch(self):
        with self.assertRaises(WriteDenied):
            self.writer.update("D2:D3",[["SYN"]],record_ids=("TEST-A","TEST-B"))

    def test_response_lost_requires_observation_not_replay(self):
        self.ws.fail_after=True
        out=self.writer.update("D2",[["SYN"]],record_ids=("TEST-A",))
        self.assertEqual(out["outcome"],"CURRENT_STATE_MATCHES_NOT_EXACTLY_ONCE")
        self.assertFalse(out["retry_automatically"])
        self.assertEqual(self.ws.calls,1)

    def test_unknown_response_does_not_replay(self):
        def before_write_fail(*args,**kwargs):
            raise RuntimeError("synthetic response missing")
        self.ws.update=before_write_fail
        out=self.writer.update("D2",[["SYN"]],record_ids=("TEST-A",))
        self.assertEqual(out["outcome"],"UNKNOWN_NEEDS_REVIEW")
        self.assertFalse(out["retry_automatically"])

    def test_unknown_title_id_denied(self):
        self.ws.id=0
        with self.assertRaises(WriteDenied):
            self.writer.update("D2",[["SYN"]],record_ids=("TEST-A",))

    def test_structural_mutation_denied(self):
        for name in ("clear","batch_clear","sort","resize","set_with_dataframe"):
            with self.subTest(name=name):
                with self.assertRaises(WriteDenied):
                    getattr(self.writer,name)

    def test_real_gspread_object_never_accepted(self):
        class FakeNetworkWorksheet:
            id=1618938211
            title="CSS Contract-SIF Tracker"
        with self.assertRaisesRegex(WriteDenied,"network-backed"):
            ScopedWriter(FakeNetworkWorksheet())

    def test_disabled_synthetic_flag_denied(self):
        with patch.dict(os.environ,{"G16_SYNTHETIC_ONLY":"0"}):
            with self.assertRaises(WriteDenied):
                ScopedWriter(self.ws)

    def test_other_manual_tabs(self):
        for sid,title,blocked,safe in [
            (948865119,"CSS Project Dashboard","A2","C2"),
            (692581491,"CSS Contract-SIF Skipped","A2","E2"),
            (1445506838,"CSS Manual Exclusions","A2","C2"),
        ]:
            with self.subTest(title=title):
                ws=SyntheticWorksheet(sid,title,{2:"TEST-A"})
                w=ScopedWriter(ws)
                with self.assertRaises(WriteDenied):
                    w.update(blocked,[["X"]],record_ids=("TEST-A",))
                self.assertEqual(w.update(safe,[["SYN"]],record_ids=("TEST-A",))
                                 ["outcome"],"ACKNOWLEDGED_SYNTHETIC_WRITE")
                self.assertEqual(ws.calls,1)

if __name__=="__main__":
    unittest.main()
