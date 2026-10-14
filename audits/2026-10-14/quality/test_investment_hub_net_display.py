"""Real JS renderer from historical Investment Hub generator; no browser/network.

The test runs built JS in a mocked Node context to prove prior +198% P1
metadata cannot be surfaced without all explicit broker evidence flags.
The actual Vercel linked repo/deployed JS is NOT verified by this test.
"""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]
BUILDER=ROOT/"kalman-toss-gateway"/"scripts"/"build_investment_hub_v7424_execution_telemetry.py"


@unittest.skipUnless(shutil.which("node"), "Node JS runner not installed")
class LegacyInvestmentHubNetGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location("hub_builder_audit",BUILDER)
        builder=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            # Patch the actual historical generator against a minimal source,
            # not real deployed JS or an authorized production deployment.
            (root/"app.js").write_text(
                "function renderExecutionLedger(ctl){}\nasync function loadCommandCenter(){}",
                encoding="utf-8")
            builder.patch_app(root)
            source=(root/"app.js").read_text(encoding="utf-8")
        cls.renderer=source[:source.index("\nasync function loadCommandCenter()")]

    def render(self, row):
        script="""
const rows=[ROW_LITERAL];
const box={innerHTML:""}, state={className:"",textContent:""};
function $(s){return s==='#executionLedger'?box:s==='#executionLedgerState'?state:null;}
function n(x){if(x===null||x===undefined||x==='')return null;let v=Number(x);return Number.isFinite(v)?v:null;}
function fmt(x,d){return Number(x).toFixed(d);}
function pct(x,m){return (x*m).toFixed(2)+'%';}
function money(x){return String(x||'—');}
function time(x){return String(x||'—');}
function esc(x){return String(x);}
function executionStateLabel(x){return x||'—';}
function exitReasonLabel(x){return x||'—';}
RENDERER_LITERAL
renderExecutionLedger({execution_ledger:rows});
process.stdout.write(JSON.stringify({html:box.innerHTML,state:state.textContent}));
""".replace("ROW_LITERAL",json.dumps(row,ensure_ascii=False)).replace("RENDERER_LITERAL",self.renderer)
        proc=subprocess.run(["node","-e",script],capture_output=True,text=True,timeout=12,check=False)
        self.assertEqual(proc.returncode,0,proc.stderr[-1600:])
        return json.loads(proc.stdout)["html"]

    def base(self):
        return dict(symbol="INTC",state="CLOSED",entry_average_price="34",
                    exit_average_price="33.93",net_return=1.98697,
                    realized_return_pct=-0.00212,round_trip_cost_bps=5,
                    entry_signal_as_of="2026-10-14T00:00:00Z",
                    exit_reason="MAX_HOLD_4_BUCKETS")

    def test_legacy_198_percent_fake_gain_masked(self):
        text=self.render(self.base())
        self.assertNotIn("198.70%",text)
        self.assertNotIn("198.69%",text)
        self.assertIn('<td class="">검증 전</td>',text)
        self.assertIn("-0.21%",text)

    def test_legacy_local_quality_covered_does_not_authorize(self):
        row=self.base()
        row["net_return_evidence_status"]="LOCAL_PROVENANCE_ATTESTED"
        row["independent_order_manifest_verified"]=True
        row["fee_currency_verified"]=True
        row["position_fill_coverage_verified"]=True
        self.assertNotIn("198.70%",self.render(row))
        self.assertIn('<td class="">검증 전</td>',self.render(row))

    def test_fake_broker_reconciled_without_all_fields_masked(self):
        for field in ("independent_order_manifest_verified","fee_currency_verified",
                      "position_fill_coverage_verified"):
            with self.subTest(field=field):
                row=self.base()
                row.update(net_return_evidence_status="BROKER_RECONCILED",
                           independent_order_manifest_verified=True,
                           fee_currency_verified=True,
                           position_fill_coverage_verified=True)
                row[field]=False
                html=self.render(row)
                self.assertIn('<td class="">검증 전</td>',html)
                self.assertNotIn("198.70%",html)

    def test_all_flags_attested_allows_pure_display_helper(self):
        row=self.base()
        row.update(net_return_evidence_status="BROKER_RECONCILED",
                   independent_order_manifest_verified=True,
                   fee_currency_verified=True,
                   position_fill_coverage_verified=True)
        html=self.render(row)
        self.assertIn("198.70%",html)
        self.assertIn('<td class="good">198.70%</td>',html)
        # This checks renderer behavior only, NOT that an external source
        # truly verified the flags.

    def test_missing_null_or_nonfinite_net_never_shows_value(self):
        row=self.base()
        row.update(net_return_evidence_status="BROKER_RECONCILED",
                   independent_order_manifest_verified=True,
                   fee_currency_verified=True,
                   position_fill_coverage_verified=True)
        for val in (None, "", "NaN", "Infinity"):
            with self.subTest(value=val):
                row["net_return"]=val
                self.assertIn('<td class="">검증 전</td>',self.render(row))


if __name__=="__main__":
    unittest.main()
