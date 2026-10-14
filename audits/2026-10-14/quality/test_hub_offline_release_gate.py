"""Pure bundle guard regression, no building or external calls."""
import base64
import json
import unittest
from hub_offline_release_gate import (
    EXPECTED_NAMES, ReleaseGateError, decode_manifest, verify_source, VERSION,
)


def synthetic_bundle():
    bundle = {p: b"// synthetic" for p in EXPECTED_NAMES}
    bundle["index.html"] = ("<html>" + VERSION + "</html>").encode()
    bundle["api/health.js"] = (
        "const x={investment_hub_version:'" + VERSION +
        "',trade_enabled:false,account_trade_execution:false};"
    ).encode()
    bundle["api/assets.js"] = (
        "const query='FROM v_live_trade_ledger';const x='net_return';"
    ).encode()
    bundle["app.js"] = (
        "function renderExecutionLedger(ctl){"
        "function verifiedNet(x){"
        "return x.net_return_evidence_status==='BROKER_RECONCILED'"
        "&&x.independent_order_manifest_verified===true"
        "&&x.fee_currency_verified===true"
        "&&x.position_fill_coverage_verified===true?x.net_return:null;}"
        "const net=verifiedNet(x);const message='검증 전';}"
    ).encode()
    bundle["vercel.json"] = b"{}"
    return bundle


class FullBundleGateUnitTests(unittest.TestCase):
    def test_synthetic_fixture_valid(self):
        p = verify_source(synthetic_bundle())
        self.assertEqual(p["decision"], "OFFLINE_BUILD_PASS_RELEASE_HOLD")
        self.assertFalse(p["release_authorized"])
        self.assertEqual(p["manifest_files"], 30)

    def test_invalid_or_legacy_ui_blocks(self):
        f = synthetic_bundle()
        f["app.js"] = b"function renderExecutionLedger(ctl){const net=x.net_return;}"
        with self.assertRaisesRegex(ReleaseGateError, "FINAL_UI_P1_GUARD_MISSING"):
            verify_source(f)

    def test_readonly_server_contract_required(self):
        f = synthetic_bundle()
        f["api/health.js"] = VERSION.encode()
        with self.assertRaisesRegex(ReleaseGateError, "WEB_READ_ONLY_CONTRACT_MISSING"):
            verify_source(f)

    def test_no_live_ledger_api_blocks(self):
        f = synthetic_bundle()
        f["api/assets.js"] = b"const values=[];"
        with self.assertRaisesRegex(ReleaseGateError, "LIVE_LEDGER_API_CONTRACT_MISSING"):
            verify_source(f)

    def test_exact_whitelisted_manifest_paths(self):
        f = synthetic_bundle()
        lines = [json.dumps({"file": k, "data_b64": base64.b64encode(v).decode()})
                 for k, v in sorted(f.items())]
        loaded = decode_manifest("\n".join(lines))
        self.assertEqual(set(loaded), EXPECTED_NAMES)

    def test_manifest_path_traversal_rejected(self):
        f = synthetic_bundle()
        lines = [json.dumps({"file": k, "data_b64": base64.b64encode(v).decode()})
                 for k, v in sorted(f.items())]
        first=json.loads(lines[0]);first["file"]="../../secrets.env"
        lines[0]=json.dumps(first)
        with self.assertRaises(ReleaseGateError):
            decode_manifest("\n".join(lines))

    def test_duplicate_entry_rejected(self):
        f=synthetic_bundle()
        lines = [json.dumps({"file": k, "data_b64": base64.b64encode(v).decode()})
                 for k,v in sorted(f.items())]
        item=json.loads(lines[1]);item["file"]=json.loads(lines[0])["file"]
        lines[1]=json.dumps(item)
        with self.assertRaises(ReleaseGateError):
            decode_manifest("\n".join(lines))

    def test_no_plaintext_payload_in_verification_summary(self):
        f=synthetic_bundle()
        p=verify_source(f)
        self.assertNotIn("api assets", repr(p))
        self.assertNotIn("BROKER_RECONCILED", repr(p))


if __name__ == "__main__":
    unittest.main()
