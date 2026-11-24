"""Unit contracts plus actual-market PR smoke for the first-seal rehearsal."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
import unittest
from zipfile import ZipFile

from first_seal_real_input_rehearsal import (
    make_test_journals, rehearse, VERSION,
)
from prospective_seal_attestation import _event_index, CORE, CONTEXT
from test_prospective_seal_attestation import fake_prospective, SESSION
from forward_shadow import journal_bytes

SPEC = {
    "core": list(CORE), "context": list(CONTEXT),
    "high_risk_shadow_only": ["QLD", "IONQ", "COIN", "MSTR"],
}


class RealInputRehearsalContracts(unittest.TestCase):
    def setUp(self):
        self.doc, *_ = fake_prospective()

    def test_all_synthetic_journals_well_formed_and_directly_linked(self):
        bulls, bears = make_test_journals(SPEC, self.doc, SESSION)
        self.assertEqual((len(bulls), len(bears)), (20, 40))
        with ZipFile(BytesIO(), "w") as z:
            z.writestr("research/forward_shadow/journal.jsonl", journal_bytes(bulls))
            z.writestr("research/bear_forward/journal.jsonl", journal_bytes(bears))
            keys = z.namelist()
        buf = BytesIO()
        with ZipFile(buf, "w") as z:
            z.writestr("research/forward_shadow/journal.jsonl", journal_bytes(bulls))
            z.writestr("research/bear_forward/journal.jsonl", journal_bytes(bears))
        with ZipFile(BytesIO(buf.getvalue())) as z:
            bull = _event_index(z, z.namelist(),
                                "research/forward_shadow/journal.jsonl", "BULL")
            bear = _event_index(z, z.namelist(),
                                "research/bear_forward/journal.jsonl", "BEAR")
        self.assertEqual(len(bull), 20)
        self.assertEqual(len(bear), 40)
        for symbol in CORE:
            be = bull[(SESSION, symbol, "BULL_LOGISTIC")]
            self.assertTrue(be["synthetic_test_event_never_tradable"])
            for family in ("BEAR_LOGISTIC", "BEAR_RULE"):
                e = bear[(SESSION, symbol, family)]
                self.assertEqual(e["baseline_signal_hash"], be["hash"])
                self.assertEqual(e["source_actions_run_id"],
                                 self.doc["source_actions_run_id"])

    def test_real_input_adapter_preserves_scored_values_and_rebinds_60_events(self):
        doc = self.doc

        def snapshot(**kwargs):
            raise AssertionError("call with positional first")

        def generator(spec, market, features, scores, day, bulls, bears):
            self.assertEqual(day, SESSION)
            self.assertEqual(spec["core"], list(CORE))
            item = deepcopy(doc)
            for symbol in CORE:
                item["models"][symbol]["frozen_signal_hashes"] = {
                    family: ((bulls[(day, symbol)] if family == "BULL_LOGISTIC"
                             else bears[(day, symbol, family)])["hash"])
                    for family in ("BULL_LOGISTIC", "BEAR_LOGISTIC", "BEAR_RULE")
                }
            return item

        with patch("first_seal_real_input_rehearsal.read_score_rows",
                   return_value={}), patch(
                       "first_seal_real_input_rehearsal.make_current_snapshot",
                       side_effect=generator):
            report = rehearse(SPEC, Path("n/a"), Path("n/a"),
                              Path("n/a.csv"), SESSION)
        self.assertEqual(report["version"], VERSION)
        self.assertEqual(report["status"], "REAL_INPUT_SYNTHETIC_EVENT_CONTRACT_PASS")
        self.assertEqual((report["price_assets_verified"],
                          report["feature_values_verified"],
                          report["real_model_fit_provenance_verified"],
                          report["synthetic_event_anchor_count"]),
                         (26, 420, 40, 60))
        self.assertTrue(report["historical_real_price_and_feature_values"])
        self.assertTrue(report["synthetic_event_hashes_only"])
        self.assertFalse(report["synthetic_events_written_to_drive"])
        self.assertFalse(report["prospective_first_seal_claimed"])
        self.assertFalse(report["official_close_certified"])

    def test_two_computations_cannot_disagree_on_price(self):
        doc = self.doc
        calls = [0]
        def changing(*args):
            calls[0] += 1
            item = deepcopy(doc)
            if calls[0] == 2:
                item["price_26"]["QQQ"]["close"] += 1
            return item
        with patch("first_seal_real_input_rehearsal.read_score_rows",
                   return_value={}), patch(
                       "first_seal_real_input_rehearsal.make_current_snapshot",
                       side_effect=changing):
            with self.assertRaisesRegex(RuntimeError, "RECOMPUTED_INPUT_NOT_STABLE"):
                rehearse(SPEC, Path("n/a"), Path("n/a"),
                         Path("n/a.csv"), SESSION)

    def test_two_computations_cannot_disagree_on_feature(self):
        doc = self.doc
        calls = [0]
        def changing(*args):
            calls[0] += 1
            item = deepcopy(doc)
            if calls[0] == 2:
                item["models"]["SPY"]["feature_values"][0] += 1
            return item
        with patch("first_seal_real_input_rehearsal.read_score_rows",
                   return_value={}), patch(
                       "first_seal_real_input_rehearsal.make_current_snapshot",
                       side_effect=changing):
            with self.assertRaisesRegex(RuntimeError, "RECOMPUTED_MODEL_NOT_STABLE"):
                rehearse(SPEC, Path("n/a"), Path("n/a"),
                         Path("n/a.csv"), SESSION)

    def test_incomplete_symbol_set_rejected_before_io(self):
        bad = dict(SPEC, core=["SPY"])
        with self.assertRaisesRegex(RuntimeError, "REHEARSAL_UNIVERSE_INCOMPLETE"):
            rehearse(bad, Path("n/a"), Path("n/a"), Path("n/a.csv"), SESSION)


if __name__ == "__main__":
    unittest.main()
