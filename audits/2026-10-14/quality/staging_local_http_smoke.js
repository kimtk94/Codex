'use strict';
// Off-network integration for ACTUAL compiled candidate API handlers.
// This test uses loopback 127.0.0.1 only and code via vm sandbox with mocked
// dependencies: NO Vercel, Neon, broker, runtime .env or application tokens.
// All module imports are mocked. No app-provided fetch/network/SQL possible.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '../../..');
const manifest = path.join(root, 'kalman-hub-recovery/v7.4.36/source_manifest.ndjson');
if (!fs.existsSync(manifest)) throw Error('OFFLINE_BUNDLE_MISSING');
const files = new Map(fs.readFileSync(manifest, 'utf8').trim().split('\n').map(line => {
  const x = JSON.parse(line);
  if (!/^((api|lib)\/[a-z0-9/_-]+\.js|[a-z0-9/_-]+\.js)$/.test(x.file)) {
    // Non-JS entries are allowed in the 30-file bundle but not executable.
    return [x.file, null];
  }
  return [x.file, Buffer.from(x.data_b64, 'base64').toString('utf8')];
}));
let forbiddenOutboundCalls = 0;
let attemptedWrites = 0;
let loadedLedger = 0;
const sampleLedger = [{symbol: 'SYNTHETIC', position_id: 'MOCK-ONLY', net_return: null}];
const runtimeCacheMock = {
  status: async () => ({available:false}),
  getCache: async () => null,
  MANUAL_KEY:'SYNTHETIC_MANUAL', SELECTOR_KEY:'SYNTHETIC_SELECTOR',
  KR_SELECTOR_KEY:'SYNTHETIC_KR',MANUAL_TTL_SECONDS:60,
  SELECTOR_TTL_SECONDS:60,KR_SELECTOR_TTL_SECONDS:60,
};
const moduleStubs = Object.freeze({
  '../lib/runtime-cache':runtimeCacheMock,
  '../../lib/runtime-cache':runtimeCacheMock,
  '../lib/auth': {automationOk: () => false,tokenOk: () => false},
  '../../lib/auth': {automationOk: () => false,tokenOk: () => false},
  '../lib/assets-payload': {buildAssetsPayload: async () => ({synthetic:true,trade_enabled:false})},
  '../lib/position-ledger': {
    load: async () => { loadedLedger++; return {ok:true,ledger:{records:sampleLedger}}; },
    summarize: records => ({synthetic_count:records.length})
  },
  '../lib/position-ledger-actions': {
    captureAndResolve: async () => { attemptedWrites++; throw Error('WRITE_DISABLED'); }
  },
  '../../lib/core': {
    normalizeIngestSnapshot: () => { attemptedWrites++; throw Error('WRITE_DISABLED'); },
    getEtfSnapshot: async () => ({source:'SYNTHETIC'}),
    saveEtf: async () => { attemptedWrites++; throw Error('WRITE_DISABLED'); },
  }
});
const handlers = {};
for (const key of ['api/health.js','api/assets.js','api/ingest/etf.js',
    'api/ingest/manual-snapshot.js','api/position-ledger.js',
    'api/position-ledger-tick.js']) {
  const source = files.get(key);
  if (typeof source !== 'string') throw Error('SOURCE_NOT_PRESENT: '+key);
  const sandbox = {
    module:{exports:{}},
    exports:{},
    process:{env:Object.freeze({})},
    require: name => {
      if (!(name in moduleStubs)) throw Error('UNEXPECTED_MODULE_IMPORT:'+name);
      return moduleStubs[name];
    },
    fetch:async () => { forbiddenOutboundCalls++; throw Error('OUTBOUND_NETWORK_DISABLED'); },
    URL, URLSearchParams, AbortController,
    setTimeout:() => { throw Error('TIMER_NETWORK_NOT_ALLOWED'); },
    clearTimeout:() => {},
  };
  vm.runInNewContext(source, sandbox, {filename:key,timeout:1000});
  if (typeof sandbox.module.exports !== 'function') throw Error('NO_HANDLER:'+key);
  handlers['/'+key.slice(0,-3)] = sandbox.module.exports;
}
const requests = [
  {site:'MAIN',method:'GET',url:'/api/health',code:200,check:r=>r.body.trade_enabled===false&&r.body.account_trade_execution===false},
  {site:'MAIN',method:'POST',url:'/api/health',code:405},
  {site:'MAIN',method:'GET',url:'/api/assets?view=control',code:503,check:r=>r.body.error==='DB_NOT_CONFIGURED'},
  {site:'MAIN',method:'GET',url:'/api/assets?view=account',code:503,check:r=>r.body.error==='ACCOUNT_GATEWAY_NOT_CONFIGURED'},
  {site:'MAIN',method:'POST',url:'/api/assets?view=control',code:405},
  {site:'MAIN',method:'GET',url:'/api/ingest/etf',code:405},
  {site:'MAIN',method:'POST',url:'/api/ingest/etf',code:401},
  {site:'MAIN',method:'POST',url:'/api/ingest/manual-snapshot',code:401},
  {site:'MAIN',method:'GET',url:'/api/ingest/manual-snapshot',code:200,check:r=>r.body.ok===true},
  {site:'MAIN',method:'POST',url:'/api/position-ledger-tick',code:401},
  {site:'MAIN',method:'GET',url:'/api/position-ledger-tick',code:401},
  {site:'MAIN',method:'POST',url:'/api/position-ledger',code:401},
  {site:'MAIN',method:'GET',url:'/api/position-ledger',code:200,check:r=>r.body.records?.[0]?.symbol==='SYNTHETIC'},
  {site:'US',method:'GET',url:'/api/health',code:200},
  {site:'KR',method:'GET',url:'/api/health',code:200},
  {site:'US',method:'GET',url:'/api/assets?view=control',code:503},
  {site:'KR',method:'GET',url:'/api/assets?view=control',code:503},
];

async function main() {
  // Bind only to loopback. US/KR are MOCK routing labels, not real Vercel
  // traffic, and all requests hit this same synthetic MAIN origin.
  const server=http.createServer(async (req,res)=>{
    res.status=function(code){res.statusCode=code;return res};
    res.json=function(body){res.setHeader('Content-Type','application/json');res.end(JSON.stringify(body));return res};
    const pathname=new URL(req.url,'http://127.0.0.1').pathname;
    const handler=handlers[pathname];
    if (!handler) return res.status(404).json({error:'LOCAL_ROUTE_NOT_FOUND'});
    try{await handler(req,res)}catch(e){res.status(599).json({error:'SANDBOX_HANDLER_EXCEPTION',category:String(e.message).slice(0,64)})}
  });
  await new Promise((resolve,reject)=>server.listen(0,'127.0.0.1',e=>e?reject(e):resolve()));
  const port=server.address().port;
  const results=[];
  try{
    for (const q of requests){
      const r=await new Promise((resolve,reject)=>{
        const req=http.request({hostname:'127.0.0.1',port,path:q.url,method:q.method,
          timeout:2500}, res=>{
          let raw='';res.on('data',s=>raw+=s);res.on('end',()=>{
            try{resolve({status:res.statusCode,body:JSON.parse(raw)})}catch(e){reject(e)}
          });
        });
        req.on('error',reject);req.on('timeout',()=>req.destroy(Error('LOOPBACK_TIMEOUT')));req.end();
      });
      assert.equal(r.status,q.code,q.site+' '+q.method+' '+q.url+' returned unexpected status');
      if(q.check)assert.equal(q.check(r),true,'UNEXPECTED_HANDLER_CONTRACT:'+q.url);
      results.push({site:q.site,method:q.method,path:new URL(q.url,'http://127.0.0.1').pathname,
        view:new URL(q.url,'http://127.0.0.1').searchParams.get('view')||null,
        status:r.status});
    }
    assert.equal(forbiddenOutboundCalls,0,'OUTBOUND_NETWORK_ATTEMPTED');
    assert.equal(attemptedWrites,0,'APP_WRITE_PATH_INVOKED');
    assert.ok(loadedLedger>=2,'POSITION_LEDGER_SOURCE_NOT_USED');
    process.stdout.write(JSON.stringify({
      status:'MOCK_HTTP_SMOKE_PASS_STAGING_RELEASE_HOLD',
      routes_exercised:6, request_cases:results.length, results,
      actual_vpn_ss0_or_vercel_http_verified:false,
      live_data_used:false, outbound_network_calls:forbiddenOutboundCalls,
      write_attempts:attemptedWrites,
      unauthenticated_ledger_get_returns_synthetic_records:true,
      unauthenticated_manual_get_allows_synthetic_cache:true,
      production_release_authorized:false
    })+'\n');
  }finally{
    await new Promise(resolve=>server.close(resolve));
  }
}
main().catch(e=>{process.stderr.write(String(e.stack||e).slice(0,1800)+'\n');process.exitCode=1});
