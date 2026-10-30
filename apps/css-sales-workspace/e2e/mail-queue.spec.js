'use strict';
const {test,expect}=require('@playwright/test');

function records(){
 const result=Array.from({length:60},(_,i)=>({
   uid:'inbox:'+(40000+i),days:i+1,priority:i>40?'URGENT':'FOLLOWUP',
   sender:'client'+i+'@mock.example.edu',
   subject:'Subject '+i,
   project:'Korea-Mock-'+i,
   received:'2026-10-30 09:00:00',
   body:'Original body for sample '+i
 }));
 result[0].subject='Sample <img src=x onerror=alert(1)> XSS probe';
 return result;
}
function sheet({enabled=false}={}){
 return {inbox:records(),reviews:[
   {uid:'inbox:40001',decision:'EXCLUDE_MAIL',sync:'SYNCED:EXCLUDE_MAIL',
    sender:'client1@mock.example.edu',subject:'Subject 1'}
 ],capabilities:{manualMailReview:enabled},refreshed:'2026-10-30 09:30:00 KST'};
}
async function mockData(page,snapshot){
 await page.route('**/api/lifecycle',route=>
   route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(snapshot)}));
}

test('real browser: filter, 25-row pages, sort and HTML-safe subject rendering',async({page})=>{
 await mockData(page,sheet());
 await page.addInitScript(()=>{
   window.open=(url)=>{window.__lastOpened=url;return null;};
 });
 await page.goto('/mail-queue.html');
 await expect(page.locator('#rows tr')).toHaveCount(25);
 await expect(page.locator('#unansweredCount')).toHaveText('60');
 await expect(page.locator('#range')).toHaveText('1–25 / 60');
 await page.locator('#next').click();
 await expect(page.locator('#range')).toHaveText('26–50 / 60');
 await page.locator('#prev').click();
 await page.locator('#sort').selectOption('new');
 await expect(page.locator('#rows tr')).toHaveCount(25);
 await page.locator('#search').fill('client59@');
 await expect(page.locator('#rows tr')).toHaveCount(1);
 await expect(page.locator('#rows tr').first()).toContainText('client59@mock.example.edu');
 await page.locator('#rows tr').first().locator('button').nth(1).click();
 await expect.poll(()=>page.evaluate(()=>window.__lastOpened)).toBe(
   'https://docs.google.com/spreadsheets/d/1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI/edit');
 await page.locator('#search').fill('client0@');
 await expect(page.locator('#rows tr')).toHaveCount(1);
 await expect(page.locator('#rows tr').first()).toContainText('<img src=x onerror=alert(1)>');
 await expect(page.locator('img')).toHaveCount(0);
});

test('real browser: read-only mode never POSTs decisions',async({page})=>{
 const writes=[];
 await mockData(page,sheet());
 page.on('request',req=>{if(req.method()!=='GET')writes.push(req.url());});
 await page.goto('/mail-queue.html');
 await expect(page.locator('#mode')).toContainText('읽기 전용');
 await expect(page.locator('#excludedRows tr')).toHaveCount(1);
 await page.locator('#rows tr').first().locator('button').first().click();
 await expect(page.locator('#bodyDialog')).toBeVisible();
 await expect(page.locator('#bodyText')).toContainText('Original body for sample');
 await page.locator('#closeBody').click();
 await expect(page.locator('#bodyDialog')).toBeHidden();
 assertNoPost(writes);
});

test('real browser: explicit owner confirmation sends only expected UID action',async({page})=>{
 const posts=[];
 await mockData(page,sheet({enabled:true}));
 await page.route('**/api/lifecycle/review',async route=>{
   const req=route.request();
   posts.push({method:req.method(),headers:req.headers(),body:req.postDataJSON()});
   await route.fulfill({status:200,contentType:'application/json',
     body:JSON.stringify({status:'QUEUED_FOR_EXISTING_GITHUB_SYNC',
       uid:'inbox:40059',decision:'EXCLUDE_MAIL',synced:false})});
 });
 page.on('dialog',d=>d.accept());
 await page.goto('/mail-queue.html');
 await expect(page.locator('#mode')).toContainText('수동 Decision 접수 가능');
 await page.locator('#search').fill('client59@');
 await page.locator('#rows tr').first().locator('button').nth(1).click();
 await expect(page.locator('#reviewDialog')).toBeVisible();
 await expect(page.locator('#reviewDescription')).toContainText('inbox:40059');
 await page.locator('#choice').selectOption('EXCLUDE_MAIL');
 await page.locator('#confirmReview').click();
 await expect.poll(()=>posts.length).toBe(1);
 expect(posts[0].method).toBe('POST');
 expect(posts[0].headers['x-css-review-confirm']).toBe('EXPLICIT_USER_APPROVAL');
 expect(posts[0].body).toEqual({
   uid:'inbox:40059',action:'EXCLUDE_MAIL',expectedDecision:'NONE'
 });
 await expect(page.locator('#reviewDialog')).toBeHidden();
});

test('real browser: unauthorized source responds with clear login requirement',async({page})=>{
 await page.route('**/api/lifecycle',route=>route.fulfill({
   status:401,contentType:'application/json',body:JSON.stringify({error:'AUTH_REQUIRED'})
 }));
 await page.goto('/mail-queue.html');
 await expect(page.locator('#syncState')).toContainText('인증 필요');
 await expect(page.locator('#rows tr')).toHaveCount(0);
});

function assertNoPost(writes){
 expect(writes).toEqual([]);
}
