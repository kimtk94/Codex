/** No Salesforce credentials, private files or CRM writes.
 * Synthetic browser regression for user-triggered local approval review and
 * unsaved native Opportunity preparation UI.
 */
import test from "node:test";
import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import {setTimeout as delay} from "node:timers/promises";
import {chromium} from "playwright";

const port=31391,base="http://127.0.0.1:"+port;
let server,browser;
async function waitForServer(){
 for(let i=0;i<100;i++){
  if(server.exitCode!==null)throw Error("Next exited during approval test");
  try{
   const response=await fetch(base+"/sales/commands/pair/approvals",{
    signal:AbortSignal.timeout(1100)});
   if(response.status===200)return;
  }catch{}
  await delay(500);
 }
 throw Error("Approval browser server unavailable");
}
const qid="OPPOQUOTE-"+"b".repeat(24);
test("local approval console never writes SFDC and can rehearse and prepare unsaved Opportunity",
 {timeout:125000},async()=>{
 server=spawn(process.execPath,["node_modules/next/dist/bin/next","start",
  "--port",String(port)],{cwd:process.cwd(),
  env:{...process.env,NEXT_TELEMETRY_DISABLED:"1"},stdio:"ignore"});
 let page;
 try{
  await waitForServer();
  browser=await chromium.launch({headless:true});
  page=await browser.newPage();
  const writes=[],modes=[];
  page.on("request",request=>{
   const pathname=new URL(request.url()).pathname;
   if(!["GET","HEAD","OPTIONS"].includes(request.method())&&
      pathname!=="/api/sfdc/pair-approval-review-local")
    writes.push(request.method()+" "+pathname);
  });
  await page.route("**/api/sfdc/pair-approval-review-local",async route=>{
   const payload=route.request().postDataJSON();
   modes.push(payload.mode);
   let data;
   if(payload.mode==="LIST"){
    data={status:"PASS",items:[{
     requestId:qid,name:"Korea-Synthetic-RNA-48samples",
     accountName:"합성대학교",contactName:"김가상",productCount:1,
     pendingChecks:10,queueStatus:"PENDING_APPROVAL",
     createdAtUtc:"2026-11-18T01:00:00Z"
    }],total:1,salesforceWrite:false,savePermitted:false};
   }else if(payload.mode==="DETAIL"){
    assert.equal(payload.requestId,qid);
    data={status:"QUEUE_REVIEW_READY_SFDC_NATIVE_RECHECK_REQUIRED",
     requestId:qid,name:"Korea-Synthetic-RNA-48samples",
     queueStatus:"PENDING_APPROVAL",
     closeDateKst:"2026-12-18",description:"Synthetic sample intake expected",
     sourceQid:"QID-2026-11-01-654321",
     account:{name:"합성대학교",sourceIdPresent:true,nativeIdVerified:false},
     contact:{name:"김가상",sourceIdPresent:true,nativeIdVerified:false},
     productCount:1,
     products:[{
      reference_product_id:"QD-01",service:"Synthetic RNA",
      samples:"48",productionGb:"6",historical_sample_unit_krw:"200000",
      historical_cloud_unit_krw:"30000",
      historical_sample_subtotal_krw:"9600000",process_count:2,
      original_process_names:["Synthetic library","Synthetic sequencing"],
      original_process_ids:["Process-2020-01-01-00001","Process-2020-01-01-00002"]
     }],
     requiredChecks:Array.from({length:10},(_,i)=>({
      id:"review"+i,label:"Synthetic check "+i,passed:false,evidence:"Recheck required"})),
     crmWrites:0,salesforceWrite:false,savePermitted:false
    };
   }else if(payload.mode==="FORM_REHEARSAL"){
    data={status:"PASS_FORM_INSPECTION",salesforce_write:false,save_clicked:false,
     forms:[{kind:"Opportunity",status:"PASS",record_type:"CURRENT_NATIVE_UI",
      reason:"NATIVE_FIELDS_PRESENT",required:{"Opportunity Name":true}},
      {kind:"Quotation",status:"PASS",record_type:"Research-AMEA",
       reason:"RESEARCH_AMEA_FIELDS_PRESENT",required:{"Quotation Name":true}}],
     crmWrites:0,savePermitted:false};
   }else if(payload.mode==="OPPO_UNSAVED_PREPARE"){
    assert.equal(payload.requestId,qid);
    data={status:"UNSAVED_OPPORTUNITY_FORM_READY",
     salesforce_write:false,save_clicked:false,crm_writes:0,
     fields:{"Opportunity Name":"FILLED_UNSAVED","Close Date":"FILLED_UNSAVED",
       "Progress Description":"FILLED_UNSAVED"},
     page_open:true,savePermitted:false};
   }else throw Error("UNEXPECTED_MODE_"+payload.mode);
   await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(data)});
  });
  const response=await page.goto(base+"/sales/commands/pair/approvals",{waitUntil:"networkidle"});
  assert.equal(response.status(),200);
  assert.match(await page.locator("h1").innerText(),/Opportunity–Quotation 실제 저장 사전검토/);
  await page.getByTestId("queued-approval-requests").getByRole("button").first().click();
  const review=page.getByTestId("single-quote-save-review");
  await review.waitFor();
  assert.match(await review.innerText(),/9,600,000 KRW/);
  assert.match(await review.innerText(),/Product/);
  assert.equal(await page.getByTestId("save-to-sfdc-disabled").isDisabled(),true);
  await page.getByTestId("prepare-opportunity-unsaved").click();
  await page.getByTestId("prepared-unsaved-opportunity").waitFor();
  assert.match(await page.getByTestId("prepared-unsaved-opportunity").innerText(),
    /FILLED_UNSAVED/);
  await page.getByTestId("sfdc-native-form-rehearsal").click();
  await page.getByTestId("sfdc-rehearsal-result").waitFor();
  assert.match(await page.getByTestId("sfdc-rehearsal-result").innerText(),
    /Research-AMEA/);
  assert.deepEqual(modes,["LIST","DETAIL","OPPO_UNSAVED_PREPARE","FORM_REHEARSAL"]);
  assert.deepEqual(writes,[]);
  assert.equal(await page.getByTestId("save-to-sfdc-disabled").isDisabled(),true);
 }finally{
  await page?.close().catch(()=>{});
  await browser?.close().catch(()=>{});
  server?.kill();
 }
});
