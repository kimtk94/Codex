"""Synthetic demo-only staging bundle tests; no deploy, DB, Vercel or WAN."""
import json
import shutil
import subprocess
import unittest
from build_demo_only_staging import (
    create, verify, DEMO_DISABLED, DEMO_HEALTH, BROWSER_GUARD,
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
        self.assertLess(html.index("SYNTHETIC DEMO ONLY"),html.index("Investment Intelligence"))

    def test_mutations_to_demo_protection_fail_closed(self):
        f=dict(self.f)
        f["api/assets.js"]=b"const db=process.env.DATABASE_URL_READER;"
        with self.assertRaisesRegex(RuntimeError,"DEMO_API_DEPENDENCY_PRESENT"):
            verify(f)
        f=dict(self.f)
        f["app.js"]=b"const dashboard=1;"
        with self.assertRaisesRegex(RuntimeError,"EXTERNAL_BROWSER_FETCH_NOT_BLOCKED"):
            verify(f)

    @unittest.skipUnless(shutil.which("node"),"Node.js required")
    def test_synthetic_http_handler_statuses_and_fetch_guard(self):
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
  let hits=0;
  const globalThis={fetch:async ()=>{hits++;return {ok:true}}};
  const sandbox={globalThis,URL,location:{origin:'https://preview.invalid'},Promise};
  vm.runInNewContext(a.browser,sandbox,{timeout:1000});
  await assert.rejects(globalThis.fetch('https://open.er-api.com/test'));
  assert.equal(hits,0);
  await globalThis.fetch('/api/health');
  assert.equal(hits,1);
  process.stdout.write('DEMO_HANDLER_AND_FETCH_GUARD_OK\n');
})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1});
"""
        p=subprocess.run(["node","-e",script,
                          json.dumps({"health":DEMO_HEALTH,
                                      "disabled":DEMO_DISABLED,
                                      "browser":BROWSER_GUARD})],
                         capture_output=True,text=True,timeout=12,check=False)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn("DEMO_HANDLER_AND_FETCH_GUARD_OK",p.stdout)


if __name__=="__main__":
    unittest.main()
