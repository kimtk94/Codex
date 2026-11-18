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
  const writes=[],modes=[],saveModes=[];
  const digest="SFDC-REVIEW-"+"e".repeat(24),nonce="a".repeat(48);
  page.on("dialog",dialog=>dialog.accept());
  page.on("request",request=>{
   const pathname=new URL(request.url()).pathname;
   if(!["GET","HEAD","OPTIONS"].includes(request.method())&&
      !["/api/sfdc/pair-approval-review-local",
        "/api/sfdc/pair-native-save-local"].includes(pathname))
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
     sourceAudit:{status:"HOLD_NATIVE_QUOTE_SOURCE",processRows:4,
       reasonCodes:["ALICLOUD_EXCLUDED_BUT_SOURCE_HAS_ALICLOUD_TYPED_PROCESS"],
       savePermitted:false},
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
    data={status:"HOLD_FORM_PARTIAL",
     stage:"EXISTING_CONTACT_OPENED_READ_ONLY",
     reason:"CONTACT_FIRST_NEW_OPPORTUNITY_ACTION_NOT_YET_VERIFIED",
     salesforce_write:false,save_clicked:false,crm_writes:0,
     fields:{"Contact":"VERIFIED_NATIVE_003","Account":"VERIFIED_NATIVE_001",
       "Opportunity":"NOT_CREATED"},
     page_open:true,savePermitted:false};
   }else throw Error("UNEXPECTED_MODE_"+payload.mode);
   await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(data)});
  });
  await page.route("**/api/sfdc/pair-native-save-local",async route=>{
    const payload=route.request().postDataJSON();
    saveModes.push(payload.mode+":"+payload.stage);
    assert.equal(payload.requestId,qid);
    let data;
    if(payload.mode==="PRECHECK"&&payload.stage==="OPPORTUNITY"){
      data={status:"READY_FOR_EXACT_RECORD_SAVE_CLICK",stage:payload.stage,
       requestId:qid,approvalDigest:digest,nonce,name:"Korea-Synthetic-RNA-48samples",
       quoteName:"Korea-Synthetic-RNA-48samples",
       netKrw:"9600000",vatKrw:"960000",grossKrw:"10560000",
       productCount:1,processCount:2,
       salesforce_write:false,save_clicked:false,crm_writes:0};
    }else if(payload.mode==="COMMIT"&&payload.stage==="OPPORTUNITY"){
      assert.equal(payload.approvalDigest,digest);
      assert.equal(payload.nonce,nonce);
      assert.equal(payload.confirmation,"SAVE "+digest.slice(-8));
      data={status:"NATIVE_SAVE_CREATED_AND_READBACK",stage:payload.stage,
       requestId:qid,nativeId:"006000000000001",journalState:"OPPORTUNITY_SAVED",
       nativeRecordUrl:"https://novogene.lightning.force.com/lightning/r/Opportunity/006000000000001/view",
       salesforce_write:true,save_clicked:true,crm_writes:1};
    }else if(payload.mode==="PRECHECK"&&payload.stage==="QUOTATION"){
      data={status:"HOLD_NATIVE_SAVE",code:"QUOTATION_PRODUCT_PROCESS_ROWS_NOT_VERIFIED_IN_FORM",
       stage:payload.stage,allowed:false,salesforce_write:false,save_clicked:false,
       crm_writes:0};
    }else throw Error("UNEXPECTED_NATIVE_SAVE_"+payload.mode+"_"+payload.stage);
    await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(data)});
  });
    const response=await page.goto(base+"/sales/commands/pair/approvals",{waitUntil:"networkidle"});
  assert.equal(response.status(),200);
  assert.match(await page.locator("h1").innerText(),/Opportunity–Quotation 실제 저장 사전검토/);
  await page.getByTestId("queued-approval-requests").getByRole("button").first().click();
  const review=page.getByTestId("single-quote-save-review");
  await review.waitFor();
  assert.match(await review.innerText(),/9,600,000 KRW/);
  assert.match(await page.getByTestId("sfdc-native-source-process-audit").innerText(),
    /원본 Process 4개 확인/);
  assert.match(await page.getByTestId("sfdc-native-source-process-audit").innerText(),
    /Data release 30,000원/);
  assert.match(await review.innerText(),/Product/);
  assert.equal(await page.getByTestId("save-to-sfdc-disabled").isDisabled(),true);
  const nativeSave=page.getByTestId("commit-sfdc-native-save");
  assert.equal(await nativeSave.isDisabled(),true,"Save must start disabled");
  await page.getByTestId("check-native-save").click();
  await page.getByTestId("native-save-precheck-result").waitFor();
  assert.match(await page.getByTestId("native-save-precheck-result").innerText(),
    /READY_FOR_EXACT_RECORD_SAVE_CLICK/);
  assert.equal(await nativeSave.isDisabled(),true,"Typed explicit confirmation is required");
  await page.locator("#native-save-confirm").fill("SAVE WRONG");
  assert.equal(await nativeSave.isDisabled(),true);
  await page.locator("#native-save-confirm").fill("SAVE "+digest.slice(-8));
  assert.equal(await nativeSave.isDisabled(),false);
  await nativeSave.click();
  await page.getByTestId("native-save-commit-result").waitFor();
  assert.match(await page.getByTestId("native-save-commit-result").innerText(),
    /NATIVE_SAVE_CREATED_AND_READBACK/);
  assert.equal(await nativeSave.isDisabled(),true,"Save cannot be clicked twice");
  assert.equal(await page.locator("#native-save-stage").inputValue(),"QUOTATION");
  await page.getByTestId("check-native-save").click();
  assert.match(await page.getByTestId("native-save-precheck-result").innerText(),
    /QUOTATION_PRODUCT_PROCESS_ROWS_NOT_VERIFIED_IN_FORM/);
  assert.equal(await nativeSave.isDisabled(),true);
  await page.getByTestId("prepare-opportunity-unsaved").click();
  await page.getByTestId("prepared-unsaved-opportunity").waitFor();
  assert.match(await page.getByTestId("prepared-unsaved-opportunity").innerText(),
    /VERIFIED_NATIVE_003/);
  assert.doesNotMatch(await page.getByTestId("prepared-unsaved-opportunity").innerText(),
    /FILLED_UNSAVED/);
  await page.getByTestId("sfdc-native-form-rehearsal").click();
  await page.getByTestId("sfdc-rehearsal-result").waitFor();
  assert.match(await page.getByTestId("sfdc-rehearsal-result").innerText(),
    /Research-AMEA/);
  assert.deepEqual(modes,["LIST","DETAIL","OPPO_UNSAVED_PREPARE","FORM_REHEARSAL"]);
  assert.deepEqual(saveModes,[
   "PRECHECK:OPPORTUNITY","COMMIT:OPPORTUNITY","PRECHECK:QUOTATION"]);
  assert.deepEqual(writes,[]);
  assert.equal(await page.getByTestId("save-to-sfdc-disabled").isDisabled(),true);
 }finally{
  await page?.close().catch(()=>{});
  await browser?.close().catch(()=>{});
  server?.kill();
 }
});
