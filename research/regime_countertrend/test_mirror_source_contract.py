import unittest
from pathlib import Path
from research.regime_countertrend.mirror_source_contract import classify

class MirrorSourceContractTests(unittest.TestCase):
    def test_unsafe_source_detected(self):
        txt="""def _round_trip_quality(entry_quality, exit_quality):
    return {}
def main():
    return _round_trip_quality({}, {})
"""
        self.assertEqual(classify(txt)["status"],"HOLD_NO_FULL_POSITION_AND_BROKER_PROVENANCE_CONTRACT")
    def test_signature_alone_does_not_pass(self):
        txt="""def _round_trip_quality(entry_quality, exit_quality, *, position=None, broker_fills_verified=False):
    return {}
def main():
    return _round_trip_quality({}, {})
"""
        self.assertEqual(classify(txt)["status"],"HOLD_NO_FULL_POSITION_AND_BROKER_PROVENANCE_CONTRACT")
    def test_safe_signature_remains_review_only(self):
        txt="""def _round_trip_quality(entry_quality, exit_quality, *, position=None, broker_fills_verified=False):
    return {}
def main(p):
    return _round_trip_quality({}, {}, position=p, broker_fills_verified=True)
"""
        result=classify(txt)
        self.assertEqual(result["status"],"REVIEW_CONTRACT_PRESENT_NOT_DEPLOYMENT_PROVEN")
        self.assertFalse(result["broker_verified"])
        self.assertFalse(result["production_compatible"])
    def test_current_source_writes_review_artifact(self):
        import json
        src=Path("kalman-toss-gateway/engine/trade_mirror.py")
        result=classify(src.read_text())
        out=Path("results/regime_countertrend/mirror_source")
        out.mkdir(parents=True,exist_ok=True)
        (out/"source_gate.json").write_text(json.dumps(result,indent=2))
        print("MIRROR_SOURCE_GATE",result["status"])
        self.assertIn(result["status"],{
            "HOLD_NO_FULL_POSITION_AND_BROKER_PROVENANCE_CONTRACT",
            "REVIEW_CONTRACT_PRESENT_NOT_DEPLOYMENT_PROVEN"})
if __name__=="__main__":unittest.main()
