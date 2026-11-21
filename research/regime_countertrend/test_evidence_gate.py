import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from research.regime_countertrend.evidence_gate import classify_evidence

class EvidenceGateTests(unittest.TestCase):
    def test_shadow_is_rejected_even_if_files_exist(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            trade=p/"trades.csv";bar=p/"bars.csv";e=p/"attestation.json"
            trade.write_text("fake,trade")
            bar.write_text("fake,bars")
            evidence={"origin":"SHADOW","execution_mode":"SHADOW",
              "independently_reconciled":False,
              "broker_observed_at_utc":"2026-10-16T18:45:00Z",
              "sha256_trades":hashlib.sha256(trade.read_bytes()).hexdigest(),
              "sha256_bars":hashlib.sha256(bar.read_bytes()).hexdigest()}
            e.write_text(json.dumps(evidence))
            r=classify_evidence(trade,bar,e)
            self.assertEqual(r["status"],"HOLD_SHADOW_OR_UNVERIFIED_MIRROR")
            self.assertFalse(r["real_fill_validated"])
    def test_file_hashes_are_bound(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);t=p/"t";b=p/"b";a=p/"a"
            t.write_bytes(b"orig");b.write_bytes(b"bar")
            a.write_text(json.dumps({"origin":"BROKER_INDEPENDENT","execution_mode":"LIVE","independently_reconciled":True,
                "broker_observed_at_utc":"2026-10-16T18:45:00Z",
                "sha256_trades":hashlib.sha256(t.read_bytes()).hexdigest(),
                "sha256_bars":hashlib.sha256(b.read_bytes()).hexdigest()}))
            self.assertEqual(classify_evidence(t,b,a)["status"],"PASS_EVIDENCE_CONTRACT_ONLY")
            t.write_bytes(b"changed")
            self.assertEqual(classify_evidence(t,b,a)["status"],"HOLD_ATTESTED_HASH_MISMATCH")
    def test_missing_attestation_is_hold(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);t=p/"t";b=p/"b";t.write_text("data");b.write_text("bars")
            r=classify_evidence(t,b,p/"missing")
            self.assertEqual(r["status"],"HOLD_MISSING_BROKER_ATTESTATION")
if __name__=="__main__":unittest.main()
