'use strict';
// Local Chromium UI E2E with synthetic owner/API responses; NOT authenticated
// Vercel SSO E2E and never a Production release gate acceptance.
const {test,expect}=require('@playwright/test');
const {createServer}=require('node:http');
const fs=require('node:fs');
const path=require('node:path');

let server, base;
test.beforeAll(async()=>{
  const html=fs.readFileSync(path.join(__dirname,'..','index.html'));
  server=createServer((req,res)=>{
    if(req.url!=='/'){res.writeHead(404);res.end();return;}
    res.writeHead(200,{'Content-Type':'text/html; charset=utf-8',
      'Cache-Control':'no-store'});
    res.end(html);
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  base='http://127.0.0.1:'+server.address().port;
});
test.afterAll(async()=>{
  if(server)await new Promise(resolve=>server.close(resolve));
});

const oldWrong='X209SC26065705-Z01';
const correctCandidate='X209SC26107211';
const pending={
  amea:'AMEA2026090309',
  project:'Korea-ChangWon Univ.-1-Plant-WGS-AMEA2026090309',
  quoteKrw:'9640005',unsafeWatchX:oldWrong,candidateX:correctCandidate,
  onlineH:'',onlineStage:'',source:'FINANCE',
  state:'FINANCE_AMEA_CANDIDATE',
  gate:'CANDIDATE_ONLY_REQUIRES_ORIGINAL_CONTRACT_REVIEW',
  financeSourceDate:'2026-10-26',onlineSourceDate:'2026-11-01',
  financeStale:true,attributionVerified:false,issuanceVerified:false,
  paymentVerified:false,revenueActualApproved:false
};
const unknown={
  ...pending,amea:'AMEA2026090335',
  project:'Korea-Konkuk Univ.-9-Human-mRNASeq-AMEA2026090335',
  unsafeWatchX:'X209SC26089427-Z01',candidateX:'',source:'NONE',
  state:'NO_AMEA_SOURCE_CANDIDATE',gate:'QUARANTINE_NO_CONTRACT_ATTRIBUTION'
};
const response=(contractReview)=>({
  months:[{month:'2026-10',actual:158541900,netRevenue:144129000,
    pending:0,forecast:21152370,forecastKUSD:14.102,
    verifiedBilling:0,verifiedBillingKUSD:0,netRevenueKUSD:96.086,
    invoices:48,openStatements:0}],
  projects:[],statements:[],statementSource:'QQ_VERIFIED',
  inbox:[],leads:[],reviews:[],status:[],refreshed:'2026-11-01 00:58 KST',
  mailBackfill:{state:'NOT_VERIFIED'},
  automation:{progress:{available:false},tracks:{available:false},
    acceptance:{available:false,status:'BLOCK',reason:'OWNER_E2E_NOT_RUN'}},
  contractReview
});
async function launch(page,review,code=200) {
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/lifecycle',route=>route.fulfill({
    status:code,contentType:'application/json',
    body:JSON.stringify(code===200?response(review):{error:'AUTH_REQUIRED'})
  }));
  await page.goto(base);
  await page.locator('nav button[data-view="contractReview"]').click();
  return errors;
}
test('AMEA query and candidate/quarantine filters never certify legacy X',async({page})=>{
  const contractReview={available:true,status:'REVIEW_SOURCE_STALE',verified:false,
    financeStale:true,candidateCount:1,missingCount:1,items:[pending,unknown]};
  const errors=await launch(page,contractReview);
  await expect(page.locator('#state')).toHaveText('연결됨');
  await expect(page.locator('#contractReviewRows tr')).toHaveCount(2);
  const first=page.locator('#contractReviewRows tr').first();
  await expect(first).toContainText(oldWrong+' (무효 연결)');
  await expect(first).toContainText(correctCandidate+' · 검토 후보');
  await expect(first).toContainText('귀속 미승인');
  await expect(page.locator('#contractReviewSummary')).toContainText('계약 귀속·수금·발행 승인 0건');
  await expect(page.locator('#contractReviewSummary')).toContainText('결제 원본 오래됨');
  await page.locator('#contractState').selectOption('candidate');
  await expect(page.locator('#contractReviewRows tr')).toHaveCount(1);
  await page.locator('#contractState').selectOption('missing');
  await expect(page.locator('#contractReviewRows tr')).toHaveCount(1);
  await expect(page.locator('#contractReviewRows')).toContainText('근거 없음 · 격리');
  await page.locator('#contractState').selectOption('');
  await page.locator('#contractQuery').fill('AMEA2026090309');
  await expect(page.locator('#contractReviewRows tr')).toHaveCount(1);
  await expect(page.locator('#contractReviewRows')).not.toContainText('Konkuk');
  expect(errors).toEqual([]);
});
test('missing crosswalk renders no candidates, no row-position X fallback',async({page})=>{
  const errors=await launch(page,{available:false,status:'SOURCE_NOT_VERIFIED',
    candidateCount:0,missingCount:0,items:[]});
  await expect(page.locator('#state')).toHaveText('연결됨');
  await expect(page.locator('#contractReviewSummary')).toContainText('원본 검증 실패');
  await expect(page.locator('#contractReviewRows')).not.toContainText(oldWrong);
  await expect(page.locator('#contractReviewRows')).not.toContainText(correctCandidate);
  await expect(page.locator('#contractReviewRows')).toContainText('표시할 데이터가 없습니다');
  expect(errors).toEqual([]);
});
test('unauthenticated HTTP 401 stays blocked without loading private crosswalk',async({page})=>{
  await launch(page,undefined,401);
  await expect(page.locator('#state')).toHaveText('인증 필요');
  await expect(page.locator('#login')).toBeVisible();
  await expect(page.locator('#contractReviewRows tr')).toHaveCount(0);
  await expect(page.locator('#contractReviewRows')).not.toContainText(correctCandidate);
});
test('untrusted project and X text are never interpreted as HTML',async({page})=>{
  const injected={...pending,project:'<img src=x onerror="window.__contractInjection=1"> '+pending.project};
  const errors=await launch(page,{available:true,verified:false,status:'REVIEW_ONLY',
    financeStale:false,candidateCount:1,missingCount:0,items:[injected]});
  await expect(page.locator('#contractReviewRows')).toContainText('<img src=x onerror=');
  await expect(page.locator('#contractReviewRows img')).toHaveCount(0);
  expect(await page.evaluate(()=>window.__contractInjection)).toBeUndefined();
  expect(errors).toEqual([]);
});
