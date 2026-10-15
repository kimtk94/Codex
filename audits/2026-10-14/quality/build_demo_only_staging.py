"""Create OFFLINE, non-deployable public-safe synthetic-only staging bundle.

No API credentials, Neon, Toss, Vercel, client network, or live inputs.
This transforms a previously validated 30-file candidate into 30 source files
with all 12 backends disabled (except fake health), source-side external fetch
guard, visible demo warning, and synthetic data. Never deploy in this script.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

from hub_offline_release_gate import decode_manifest, EXPECTED_NAMES

ROOT=Path(__file__).resolve().parents[3]
SOURCE=ROOT/"kalman-hub-recovery/v7.4.36/source_manifest.ndjson"
API=[p for p in EXPECTED_NAMES if p.startswith("api/") and p.endswith(".js")]
LIB=[p for p in EXPECTED_NAMES if p.startswith("lib/") and p.endswith(".js")]
DATA=[p for p in EXPECTED_NAMES if p.startswith("data/") and p.endswith(".json")]
MARKER="SYNTHETIC_DEMO_ONLY_NO_REAL_TRADES"

DEMO_HEALTH="""'use strict';
module.exports=async(req,res)=>{
  res.setHeader('Cache-Control','no-store');
  if(req.method!=='GET')return res.status(405).json({error:'METHOD_NOT_ALLOWED'});
  return res.status(200).json({
    app:'kalman-staging-demo-only',
    demo_mode:'SYNTHETIC_DEMO_ONLY_NO_REAL_TRADES',
    trade_enabled:false,account_trade_execution:false,
    data_source:'NONE',backend_connections:false,
    net_return:null,broker_connected:false
  });
};
"""
DEMO_DISABLED="""'use strict';
module.exports=async(req,res)=>{
  res.setHeader('Cache-Control','no-store');
  if(req.method!=='GET')return res.status(405).json({error:'METHOD_NOT_ALLOWED'});
  return res.status(503).json({
    error:'STAGING_DEMO_ONLY_NO_BACKEND',
    demo_mode:'SYNTHETIC_DEMO_ONLY_NO_REAL_TRADES',
    trade_enabled:false,net_return:null
  });
};
"""
BROWSER_GUARD="""// Demo-only: all network access is restricted to same-origin /api/ endpoints.
(()=>{
  const nativeFetch=globalThis.fetch;
  if(typeof nativeFetch==='function'){
    globalThis.fetch=(input,init)=>{
      const target=new URL(typeof input==='string'?input:input.url,location.origin);
      if(target.origin!==location.origin||!target.pathname.startsWith('/api/')){
        return Promise.reject(new Error('DEMO_EXTERNAL_NETWORK_DISABLED'));
      }
      return nativeFetch(input,init);
    };
  }
})();
"""
NOTICE="""<div id="kalman-demo-isolation-banner" role="status"
 style="position:sticky;top:0;z-index:9999;background:#fee2e2;color:#7f1d1d;padding:12px;text-align:center;font-weight:700;">
 SYNTHETIC DEMO ONLY — LIVE DATA DISABLED — DO NOT TRADE
</div>"""
CONFIG={
  "cleanUrls":True,
  "headers":[{"source":"/(.*)","headers":[
    {"key":"Cache-Control","value":"no-store"},
    {"key":"X-Robots-Tag","value":"noindex, nofollow, noarchive"},
    {"key":"Content-Security-Policy","value":"default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; base-uri 'self'; frame-ancestors 'none'"}
  ]}],
  "rewrites":[
    {"source":"/api/account","destination":"/api/assets"},
    {"source":"/api/dashboard","destination":"/api/assets"},
    {"source":"/api/ingest-status","destination":"/api/cache-status"}
  ]
}


def create():
    files=decode_manifest(SOURCE.read_text(encoding="utf-8"))
    if set(files)!=EXPECTED_NAMES:raise RuntimeError("SOURCE_MANIFEST_INVALID")
    for name in API:
        files[name]=(DEMO_HEALTH if name=="api/health.js" else DEMO_DISABLED).encode()
    for name in LIB:
        files[name]=b"'use strict';module.exports=Object.freeze({});\n"
    for name in DATA:
        files[name]=json.dumps({"demo_mode":MARKER,"data_source":"NONE",
                                "live_values":None},sort_keys=True).encode()
    html=files["index.html"].decode("utf-8")
    if html.count("<body>")!=1:raise RuntimeError("UNEXPECTED_BODY_COUNT")
    files["index.html"]=html.replace("<body>","<body>\n"+NOTICE,1).encode("utf-8")
    files["app.js"]=(BROWSER_GUARD+files["app.js"].decode("utf-8")).encode("utf-8")
    files["vercel.json"]=(json.dumps(CONFIG,sort_keys=True,indent=2)+"\n").encode()
    files["package.json"]=json.dumps({"name":"kalman-staging-demo-only",
                         "version":"0.0.0-demo","private":True,
                         "engines":{"node":"24.x"}},sort_keys=True).encode()
    verify(files)
    return files


def verify(files):
    if set(files)!=EXPECTED_NAMES:raise RuntimeError("PREVIEW_FILE_SET_CHANGED")
    if len(API)!=12:raise RuntimeError("API_COUNT_INVALID")
    for name in API:
        txt=files[name].decode()
        if "process.env" in txt or "require(" in txt or "import(" in txt or "fetch(" in txt:
            raise RuntimeError("DEMO_API_DEPENDENCY_PRESENT:"+name)
        if name=="api/health.js":
            if MARKER not in txt or "trade_enabled:false" not in txt:
                raise RuntimeError("HEALTH_NOT_DEMO")
        elif "STAGING_DEMO_ONLY_NO_BACKEND" not in txt:
            raise RuntimeError("BACKEND_NOT_DISABLED:"+name)
    if MARKER not in files["index.html"].decode() and "SYNTHETIC DEMO ONLY" not in files["index.html"].decode():
        raise RuntimeError("VISIBLE_DEMO_BANNER_MISSING")
    app=files["app.js"].decode()
    if "DEMO_EXTERNAL_NETWORK_DISABLED" not in app or "target.origin!==location.origin" not in app:
        raise RuntimeError("EXTERNAL_BROWSER_FETCH_NOT_BLOCKED")
    c=json.loads(files["vercel.json"])
    if "connect-src 'self'" not in c["headers"][0]["headers"][2]["value"]:
        raise RuntimeError("CSP_EXTERNAL_CONNECT_ALLOWED")
    if any("https://" in r["destination"] or "http://" in r["destination"] for r in c["rewrites"]):
        raise RuntimeError("CROSS_ORIGIN_REWRITE")
    if any(name not in files for name in API+LIB+DATA):
        raise RuntimeError("INCOMPLETE_ISOLATION")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--report",required=True)
    args=parser.parse_args()
    files=create()
    with tempfile.TemporaryDirectory(prefix="kalman-synthetic-demo-") as temp:
        root=Path(temp)
        for name in sorted(files):
            dest=root/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(files[name])
        for name in API+["app.js"]:
            subprocess.run(["node","--check",str(root/name)],check=True,
                           capture_output=True,timeout=12)
    report={
      "verdict":"DEMO_ONLY_SOURCE_VERIFIED_NOT_DEPLOYED",
      "source_files":len(files),
      "backend_api_handlers_stubbed":len(API)-1,
      "synthetic_health_handler":True,
      "all_libraries_stubbed":len(LIB),
      "synthetic_data_files":len(DATA),
      "browser_external_fetch_restricted":True,
      "backend_credentials_used":False,
      "network_calls_made":False,
      "public_staging_deployment_authorized":False,
      "reproducible_content_digest":hashlib.sha256(
          b"".join(name.encode()+b"\0"+files[name]+b"\0" for name in sorted(files))
      ).hexdigest(),
    }
    Path(args.report).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,sort_keys=True))


if __name__=="__main__":main()
