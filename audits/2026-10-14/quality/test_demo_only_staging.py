"""Synthetic demo-only staging bundle tests; no deploy, DB, Vercel or WAN."""
import json
import shutil
import subprocess
import unittest
from build_demo_only_staging import (
    create, verify, DEMO_DISABLED, DEMO_HEALTH, DEMO_APP, DEMO_INDEX, DEMO_STYLE,
    MARKER, API, LIB, DATA, EXPECTED_NAMES,
)


class DemoOnlyStagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f=create()

    def test_all_30_source_files_remain(self):
        self.assertEqual(set(self.f),EXPECTED_NAMES)
        self.assertEqual(len(self.f),30)

    def test_twelve_api_sources_isolated(self):
        self.assertEqual(len(API),12)
        for p in API:
            s=self.f[p].decode("utf-8")
            self.assertNotIn("require(",s)
            self.assertNotIn("process.env",s)
            self.assertNotIn("fetch(",s)
            self.assertNotIn("DATABASE_URL",s)
            self.assertNotIn("HUB_GATEWAY_SECRET",s)
        self.assertIn("trade_enabled:false",self.f["api/health.js"].decode())

    def test_all_runtime_libraries_inert(self):
        for p in LIB:
            self.assertEqual(self.f[p],b"'use strict';module.exports=Object.freeze({});\n")

    def test_no_static_market_data(self):
        for p in DATA:
            o=json.loads(self.f[p].decode())
            self.assertEqual(o["demo_mode"],MARKER)
            self.assertIsNone(o["live_values"])

    def test_no_third_party_network_csp(self):
        conf=json.loads(self.f["vercel.json"].decode())
        hdr={x["key"]:x["value"] for x in conf["headers"][0]["headers"]}
        self.assertIn("connect-src 'self'",hdr["Content-Security-Policy"])
        self.assertIn("noindex",hdr["X-Robots-Tag"])
        self.assertTrue(all(r["destination"].startswith("/api/") for r in conf["rewrites"]))

    def test_visible_warning_before_main_ui(self):
        html=self.f["index.html"].decode()
        self.assertIn("SYNTHETIC DEMO ONLY",html)
        self.assertNotIn("Investment Intelligence",html)
        self.assertNotIn("BUY",html)
        self.assertNotIn("SELL",html)

    def test_mutations_to_demo_protection_fail_closed(self):
        f=dict(self.f)
        f["api/assets.js"]=b"const db=process.env.DATABASE_URL_READER;"
        with self.assertRaisesRegex(RuntimeError,"DEMO_API_DEPENDENCY_PRESENT"):
            verify(f)
        f=dict(self.f)
        f["app.js"]=b"const dashboard=1;"
        with self.assertRaisesRegex(RuntimeError,"DEMO_APP_NOT_ISOLATED"):
            verify(f)

    def test_full_demo_ui_has_no_original_app_or_remote_network_calls(self):
        app=self.f["app.js"].decode()
        self.assertEqual(app,DEMO_APP)
        self.assertEqual(self.f["index.html"].decode(),DEMO_INDEX)
        self.assertEqual(self.f["style.css"].decode(),DEMO_STYLE)
        for marker in ("fetch(", "XMLHttpRequest", "WebSocket(", "EventSource(", "sendBeacon",
                       "document.cookie", "localStorage", "sessionStorage",
                       "buyOrder", "sellOrder", "renderExecutionLedger", "open.er-api.com"):
            with self.subTest(marker=marker):
                self.assertNotIn(marker,app)

    @unittest.skipUnless(shutil.which("node"),"Node.js required")
    def test_synthetic_http_handlers_and_zero_network_demo_boot(self):
        script=r"""
const vm=require('node:vm'),assert=require('node:assert/strict');
const a=JSON.parse(process.argv[1]);
async function invoke(source,method){
  let sandbox={module:{exports:{}}};
  vm.runInNewContext(source,sandbox,{timeout:1000});
  const res={
    statusCode:200,head:{},payload:null,
    setHeader(k,v){this.head[k]=v;return this},
    status(c){this.statusCode=c;return this},
    json(body){this.payload=body;return this},
  };
  await sandbox.module.exports({method},res);
  return {status:res.statusCode,body:JSON.parse(JSON.stringify(res.payload))};
}
(async()=>{
  assert.equal((await invoke(a.health,'GET')).status,200);
  assert.equal((await invoke(a.health,'GET')).body.broker_connected,false);
  assert.equal((await invoke(a.health,'POST')).status,405);
  assert.equal((await invoke(a.disabled,'GET')).status,503);
  assert.equal((await invoke(a.disabled,'POST')).status,405);
  const dom={
    'demo-environment':{textContent:''},
    'demo-health':{textContent:''}
  };
  const sandbox={document:{getElementById:id=>dom[id]||null}};
  vm.runInNewContext(a.browser,sandbox,{timeout:1000});
  assert.equal(dom['demo-environment'].textContent,'SYNTHETIC DEMO — NO CONNECTION');
  assert.match(dom['demo-health'].textContent,/synthetic mock only/);
  process.stdout.write('DEMO_HANDLER_AND_ISOLATED_BOOT_OK\n');
})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1});
"""
        p=subprocess.run(["node","-e",script,
                          json.dumps({"health":DEMO_HEALTH,
                                      "disabled":DEMO_DISABLED,
                                      "browser":DEMO_APP})],
                         capture_output=True,text=True,timeout=12,check=False)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn("DEMO_HANDLER_AND_ISOLATED_BOOT_OK",p.stdout)


if __name__=="__main__":
    unittest.main()
