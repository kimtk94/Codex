"""Synthetic-only V2 heuristic coverage tests. No production CSS imported."""
import unittest
from unittest.mock import patch

from css_g12_v2_coverage_audit import audit

def fixture(*, suspicious=False, dynamic=False):
    calls=["ws.update('D2', [[1]])"]*26
    calls += ["set_with_dataframe(ws, [[2]])",
              "other.batch_update({})" if suspicious else "sheet.batch_update({})"]
    lines=["def main(ws, sheet, other):"] + ["    "+c for c in calls]
    if dynamic:
        lines.append("    getattr(ws, 'clear')()")
    source=("\n".join(lines)+"\n").encode()
    sites=[]
    for index,call in enumerate(calls,2):
        method="set_with_dataframe" if call.startswith("set_") else (
            "batch_update" if "batch_update" in call else "update")
        sites.append({"line":index,"method":method})
    return source,{"candidate_count":28,"sites_truncated":False,"sites":sites}

class CoverageTests(unittest.TestCase):
    def run_synthetic(self, *, suspicious=False,dynamic=False):
        src, inv=fixture(suspicious=suspicious,dynamic=dynamic)
        with patch("css_g12_v2_coverage_audit.extract",return_value=inv):
            return audit(src)

    def test_28_writer_calls_accounted(self):
        result=self.run_synthetic()
        self.assertEqual(result["candidate_count"],28)
        self.assertEqual(result["v2_heuristically_wrapped"],28)
        self.assertFalse(result["release_authorized"])

    def test_unknown_worksheet_receiver_does_not_become_safe(self):
        result=self.run_synthetic(suspicious=True)
        self.assertEqual(result["v2_unclassified"],1)
        self.assertFalse(result["all_28_intercepted"])
        self.assertEqual(result["unclassified_sites"][0]["method"],"batch_update")

    def test_dynamic_getattr_counted_independently(self):
        result=self.run_synthetic(dynamic=True)
        self.assertGreaterEqual(result["dynamic_builtin_calls"],1)
        self.assertFalse(result["full_sink_isolation_proven"])

    def test_exact_28_required(self):
        src,inv=fixture()
        inv["sites"].pop()
        with patch("css_g12_v2_coverage_audit.extract",return_value=inv):
            with self.assertRaisesRegex(ValueError,"CALLSITE_INVENTORY_CHANGED"):
                audit(src)

    def test_duplicate_line_method_rejected(self):
        src,inv=fixture()
        inv["sites"][1]={"line":inv["sites"][0]["line"],"method":"update"}
        with patch("css_g12_v2_coverage_audit.extract",return_value=inv):
            with self.assertRaisesRegex(ValueError,"CALLSITE_INVENTORY_CHANGED"):
                audit(src)

    def test_no_live_source_executed(self):
        src,inv=fixture()
        src=b"raise RuntimeError('must never run')\n"+src
        inv["sites"]=[{"line":i["line"]+1,"method":i["method"]} for i in inv["sites"]]
        with patch("css_g12_v2_coverage_audit.extract",return_value=inv):
            result=audit(src)
        self.assertFalse(result["production_source_executed"])

    def test_callsite_private_literal_not_emitted(self):
        src,inv=fixture()
        src=src.replace(b"'D2'",b"'private@example.test'")
        with patch("css_g12_v2_coverage_audit.extract",return_value=inv):
            result=audit(src)
        self.assertNotIn("private@example.test",str(result))

    def test_unknown_site_only_line_and_method(self):
        result=self.run_synthetic(suspicious=True)
        for item in result["unclassified_sites"]:
            self.assertEqual(set(item),{"line","method","classification"})

if __name__=="__main__":
    unittest.main()
