'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const project=path.join(__dirname,'..');
test('Vercel unchanged-app build policy is scoped to CSS project root',()=>{
 const cfg=JSON.parse(fs.readFileSync(path.join(project,'vercel.json'),'utf8'));
 assert.equal(cfg.ignoreCommand,'git diff --quiet HEAD^ HEAD ./');
 assert.equal(cfg.$schema,'https://openapi.vercel.sh/vercel.json');
 assert.deepEqual(Object.keys(cfg).sort(),['$schema','ignoreCommand']);
});
test('CSS deployment policy does not alter auth or source-sheet credentials',()=>{
 const src=fs.readFileSync(path.join(project,'vercel.json'),'utf8');
 assert.doesNotMatch(src,/CSS_WEB_ACCESS_TOKEN|GOOGLE_SERVICE_ACCOUNT_JSON|VERCEL_APP_CLIENT_SECRET/);
 assert.doesNotMatch(src,/deploy --prod|vercel promote|protection/);
});
