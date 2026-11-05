'use strict';
// Synthetic owner API/Chromium interaction; never accesses production CRM or Sheets.
const {test,expect}=require('@playwright/test');
const {createServer}=require('node:http');
const fs=require('node:fs');
const path=require('node:path');

let server,base;
test.beforeAll(async()=>{
  const html=fs.readFileSync(path.join(__dirname,'..','index.html'));
  server=createServer((req,res)=>{
    if(req.url!=='/'){res.writeHead(404);res.end();return;}
    res.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'});
    res.end(html);
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  base='http://127.0.0.1:'+server.address().port;
});
test.afterAll(async()=>{if(server)await new Promise(resolve=>server.close(resolve))});

function fixture(){
 const items=[
  {month:'2025-10',year:2025,monthNumber:10,officialNetKRW:3000000,officialNetKUSD:2,
   issuedGrossKRW:null,verifiedNetKRW:null,source:'2025_OFFICIAL_USD_NET'},
  {month:'2026-10',year:2026,monthNumber:10,officialNetKRW:null,issuedGrossKRW:11000000,
   issuedGrossKUSD:7.333,verifiedNetKRW:10000000,verifiedNetKUSD:6.667,pendingKRW:0,pendingKUSD:0,
   forecastKRW:0,forecastKUSD:0,coverage:'INVOICES_VERIFIED_FORECAST_ESTIMATED',source:'LIFECYCLE_CURRENT',
   currentMonth:false},
  {month:'2026-11',year:2026,monthNumber:11,officialNetKRW:null,issuedGrossKRW:4000000,
   issuedGrossKUSD:2.667,verifiedNetKRW:3500000,verifiedNetKUSD:2.333,pendingKRW:1250000,pendingKUSD:.833,
   forecastKRW:9000000,forecastKUSD:6,coverage:'INVOICES_VERIFIED_FORECAST_ESTIMATED',source:'LIFECYCLE_CURRENT',
   currentMonth:true}
 ];
 return{
  months:[{month:'2026-10',actual:11000000,netRevenue:10000000,netRevenueKUSD:6.667,
   pending:0,forecast:0,forecastKUSD:0,verifiedBilling:11000000,verifiedBillingKUSD:7.333,
   invoices:5,openStatements:0},
   {month:'2026-11',actual:4000000,netRevenue:3500000,netRevenueKUSD:2.333,
   pending:1250000,forecast:9000000,forecastKUSD:6,verifiedBilling:5250000,verifiedBillingKUSD:3.5,
   invoices:2,openStatements:1}],
  monthlyComparison:{available:true,comparability:'DIFFERENT_BASES_NO_DIRECT_YOY',rows:items,issues:[],
    sources:{official2025:'BI 2025 Official Monthly',annual2026:'BI 2026 Forecast Overview'}},
  projects:[],statements:[],inbox:[],leads:[],status:[],mailBackfill:{state:'NOT_VERIFIED'},
  automation:{progress:{available:false},tracks:{available:false},acceptance:{available:false}},
  contractReview:{available:false,items:[]},refreshed:'2026-11-05 12:00 KST'
 };
}
async function launch(page,payload=fixture(),status=200){
 const errors=[];
 page.on('pageerror',err=>errors.push(err.message));
 await page.route('**/api/lifecycle',route=>route.fulfill({status,contentType:'application/json',
  body:JSON.stringify(status===200?payload:{error:'AUTH_REQUIRED'})}));
 await page.goto(base);
 return errors;
}
test('Monthly Revenue controls render and filter 2026 KRW/kUSD without combining forecast',async({page})=>{
 const errors=await launch(page);
 await expect(page.locator('#state')).toHaveText('연결됨');
 await page.locator('nav button[data-view="monthlyRevenue"]').click();
 await expect(page.locator('#monthlyRevenue')).toBeVisible();
 await expect(page.locator('#monthlyRows tr')).toHaveCount(12);
 await expect(page.locator('#monthlyChart .monthly-bar-group')).toHaveCount(12);
 await page.locator('#monthlyFilter').selectOption('11');
 await expect(page.locator('#monthlyRows tr')).toHaveCount(1);
 await expect(page.locator('#monthlyRows')).toContainText('3,500,000');
 await expect(page.locator('#monthlyRows')).toContainText('4,000,000');
 await expect(page.locator('#monthlyRows')).toContainText('1,250,000');
 await expect(page.locator('#monthlyRows')).toContainText('9,000,000');
 await expect(page.locator('#monthlyRows')).toContainText('진행 중');
 await expect(page.locator('#monthlyKpi')).toContainText('2.333 kUSD');
 expect(errors).toEqual([]);
});
test('2025 official and 2026 invoice are explicitly different accounting bases',async({page})=>{
 const errors=await launch(page);
 await page.locator('nav button[data-view="monthlyRevenue"]').click();
 await page.locator('#monthlyMode').selectOption('compare');
 await page.locator('#monthlyFilter').selectOption('10');
 await expect(page.locator('#monthlyRows tr')).toHaveCount(1);
 await expect(page.locator('#monthlyRows')).toContainText('₩3,000,000');
 await expect(page.locator('#monthlyRows')).toContainText('₩11,000,000');
 await expect(page.locator('#monthlyFootnote')).toContainText('동등한 YoY 성장률을 산출하지 않습니다');
 await expect(page.locator('#monthlyHeaders')).toContainText('2025 공식');
 await expect(page.locator('#monthlyHeaders')).toContainText('2026 Invoice');
 expect(errors).toEqual([]);
});
test('source unavailable never fabricates revenue or shows a green verified status',async({page})=>{
 const value=fixture();value.monthlyComparison={available:false,rows:[],issues:['SOURCE_MISSING']};
 const errors=await launch(page,value);
 await page.locator('nav button[data-view="monthlyRevenue"]').click();
 await expect(page.locator('#monthlySourceStatus')).toContainText('연결되지 않음');
 await expect(page.locator('#monthlyRows')).toContainText('미검증');
 await expect(page.locator('#monthlyChart')).toContainText('원본 확인이 필요');
 expect(errors).toEqual([]);
});
test('401 requires login and does not disclose monthly source data',async({page})=>{
 const errors=await launch(page,fixture(),401);
 await expect(page.locator('#state')).toHaveText('인증 필요');
 await expect(page.locator('#login')).toBeVisible();
 await expect(page.locator('#monthlyRows tr')).toHaveCount(0);
 expect(errors).toEqual([]);
});
test('untrusted source labels never become executable HTML',async({page})=>{
 const payload=fixture();
 payload.monthlyComparison.rows[1].coverage='<img src=x onerror="window.__monthlyXss=1">';
 const errors=await launch(page,payload);
 await page.locator('nav button[data-view="monthlyRevenue"]').click();
 await expect(page.locator('#monthlyRows')).toContainText('<img src=x onerror=');
 await expect(page.locator('#monthlyRows img')).toHaveCount(0);
 expect(await page.evaluate(()=>window.__monthlyXss)).toBeUndefined();
 expect(errors).toEqual([]);
});
