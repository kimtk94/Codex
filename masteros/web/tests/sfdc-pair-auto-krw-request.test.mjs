import test from "node:test";
import assert from "node:assert/strict";
import {verifiedSourcePrice,prefillVerifiedKrw} from "../lib/sfdc-pair-auto-krw.mjs";
import {calculateDraft,draftDescription,draftPreflight,opportunityUnitPriceSummary}
  from "../lib/sfdc-report-quote-draft.mjs";
import {validatePairRequest} from "../lib/sfdc-pair-request-queue.mjs";
import {historicalKrwReference,prefillHistoricalKrw} from "../lib/sfdc-pair-index-krw.mjs";
import {mkdtemp,readFile,readdir,rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {POST as submitPairRequest} from "../app/api/sfdc/pair-request-local/route.js";

const quoteId="a0P000000000001AAA",oppoId="006000000000001AAA";
const ident={status:"PASS",sourceVerified:true,nativeQuoteId:quoteId};
const source={status:"PASS",source:"LIVE_SALESFORCE",read_only:true,
 cache:{state:"LIVE_SOURCE"},id:quoteId,opportunityId:oppoId,productCount:1,
 pricingStatus:"VERIFIED_PROCESS_LINES",sourceVatRateVerified10Pct:true,
 cloudLinePresent:true,sourcePackVerified:true,productName:"mRNA sequencing",
 samples:9,dataSize:6,sampleUnitNetKrw:100000,cloudUnitNetKrw:30000,
 sourceCloudUnits:1,totalPriceKrw:930000,processPriceLines:[
 {sourceQty:9,unitPriceKrw:100000,isCloud:false,packNo:"Pack1"},
 {sourceQty:1,unitPriceKrw:30000,isCloud:true,packNo:"Pack1"}]};
function draft(){
 return {qid:"QID-2026-11-01-111111",sourceQuoteId:quoteId,
  sourceOpportunityId:oppoId,sourceKrwRateStatus:"UNVERIFIED",
  accountMode:"KEEP",account:{id:"001000000000AAA",name:"University"},
  contact:{id:"003000000000AAA",name:"Researcher"},
  name:"Korea-Research-mRNA-Quote",
  date:"2026-11-17",closeDate:"2026-12-17",
  descriptionStatus:"Quote Draft",description:"",
  products:[{id:"qproduct001",productionGb:"6",samples:"",sampleUnitKrw:"",
    cloudUnitKrw:"",serviceLabel:"mRNA-Seq",
    priceEvidenceStatus:"NOT_VERIFIED",
    processes:[{name:"Sequencing",processId:"Process-2026-001"}],
    amplicon:{enabled:false,regions:[]}}]};
}
test("native KRW rates from authenticated source Quote prefill sample+Cloud",()=>{
 const result=verifiedSourcePrice(source,ident);
 assert.equal(result.ok,true);
 const populated=prefillVerifiedKrw(draft(),result);
 assert.equal(populated.products[0].samples,"9");
 assert.equal(populated.products[0].sampleUnitKrw,"100000");
 assert.equal(populated.products[0].cloudUnitKrw,"30000");
 const totals=calculateDraft(populated);
 assert.equal(totals.netKrw,930000);
 assert.equal(totals.items[0].cloudUnits,1);
 assert.equal(totals.items[0].cloudNetKrw,30000);
 assert.equal(opportunityUnitPriceSummary(totals).products[0].unitPriceNetKrw,100000);
 assert.deepEqual(totals.quoteLineItems.map(x=>x.kind),["PRODUCT","ALICLOUD"]);
});
test("100Gb AliCloud blocks step up without manual retyping",()=>{
 const p=prefillVerifiedKrw(draft(),verifiedSourcePrice(source,ident));
 p.products[0].samples="20";
 const total=calculateDraft(p);
 assert.equal(total.netKrw,2060000);
 assert.equal(total.items[0].cloudUnits,2);
 assert.equal(total.items[0].cloudNetKrw,60000);
 assert.equal(opportunityUnitPriceSummary(total).products[0].unitPriceNetKrw,100000);
});
test("invalid or unverified source price never silently applies",()=>{
 const bad=[{...source,pricingStatus:"PROCESS_BREAKDOWN_UNVERIFIED"},
  {...source,totalPriceKrw:1000000},
  {...source,sourceCloudUnits:2},
  {...source,sourcePackVerified:false},
  {...source,processPriceLines:[source.processPriceLines[0]]}];
 for(const q of bad)assert.equal(verifiedSourcePrice(q,ident).ok,false);
 const edited=draft();edited.products[0].sampleUnitKrw="110000";
 const out=prefillVerifiedKrw(edited,verifiedSourcePrice(source,ident));
 assert.equal(out.products[0].sampleUnitKrw,"110000");
 assert.ok(out.priceCandidate);
});
test("paired creation request is locally queued pending approval, not Salesforce save",()=>{
 const ready=prefillVerifiedKrw(draft(),verifiedSourcePrice(source,ident));
 ready.description=draftDescription(ready,calculateDraft(ready));
 const r=validatePairRequest({mode:"SUBMIT_FOR_APPROVAL",draft:ready});
 assert.equal(r.ok,true);
 assert.equal(r.status,"PENDING_APPROVAL");
 assert.equal(r.savePermitted,false);
 assert.equal(r.salesforceWrite,false);
 assert.equal(r.approvalRequired,true);
 assert.equal(r.canonical.review.verifiedNativeRateForUnchangedAmount,true);
 assert.equal(validatePairRequest({mode:"SUBMIT_FOR_APPROVAL",draft:ready}).requestId,r.requestId);
 const hold=draft();hold.description="";
 const hr=validatePairRequest({mode:"SUBMIT_FOR_APPROVAL",draft:hold});
 assert.equal(hr.ok,true);
 assert.equal(hr.status,"NEEDS_REVIEW");
 assert.equal(hr.savePermitted,false);
});

test("exact-QID 2026 KRW index prefills comparisons without granting Save",()=>{
 const base=draft(),p=base.products[0];
 const row={source_kind:"VERIFIED_SFDC_KRW_PROCESS_PRICE",
   source_verified:true,created_date:"2026-11-01",quote_id:base.qid,
   active:true,approval_status:"APPROVED",currency:"KRW",
   was_usd_converted:false,vat_basis:"VAT_EXCLUDED",
   account_id:"001000000000AAA",contact_id:"003000000000AAA",
   process_id:"Process-2026-001",product_signature:"f".repeat(64),
   unit_price_krw:"115000",data_unit:"G raw data",data_size:"6",
   sample_quantity:9,process_name:"Sequencing by data amount"};
 const index={version:"sfdc-2026-krw-process-prices-v1",
   source:"SFDC_AUTHENTICATED_READ_ONLY_KRW_PROCESS_LINES",
   generated_at:new Date().toISOString(),salesforce_write_performed:false,
   records:[row]};
 const candidate=historicalKrwReference(index,base.qid,p);
 assert.equal(candidate.ok,true);
 assert.equal(candidate.candidateSampleUnitKrw,115000);
 assert.equal(candidate.pricesApprovedForNewQuote,false);
 const emptyGb={...p,productionGb:""};
 const withoutGb=historicalKrwReference(index,base.qid,emptyGb);
 assert.equal(withoutGb.ok,true);
 assert.equal(withoutGb.sourceGbStatus,"UNVERIFIED");
 const populated=prefillHistoricalKrw(base,index);
 assert.equal(populated.products[0].sampleUnitKrw,"115000");
 assert.equal(populated.products[0].priceEvidenceStatus,"INDEX_2026_KRW_COMPARISON_ONLY");
 populated.description=draftDescription(populated,calculateDraft(populated));
 assert.equal(validatePairRequest({mode:"SUBMIT_FOR_APPROVAL",draft:populated}).status,"NEEDS_REVIEW");
 const upgraded=prefillVerifiedKrw(populated,verifiedSourcePrice(source,ident));
 assert.equal(upgraded.products[0].sampleUnitKrw,"100000");
 assert.equal(upgraded.products[0].cloudUnitKrw,"30000");
 assert.equal(upgraded.products[0].priceEvidenceStatus,"LIVE_SFDC_KRW_VERIFIED");
 const missingGb={...base,products:[{...base.products[0],productionGb:""}]};
 const autoSource=prefillVerifiedKrw(missingGb,verifiedSourcePrice(source,ident));
 assert.equal(autoSource.products[0].productionGb,"6");
 assert.equal(autoSource.products[0].sampleUnitKrw,"100000");
 assert.equal(historicalKrwReference(index,"QID-2026-11-01-999999",p).ok,false);
});

test("local-only web generation request is durable and idempotent",async()=>{
 const previous={home:process.env.LOCALAPPDATA,enabled:process.env.SFDC_LOCAL_COMMAND_ENABLED};
 const home=await mkdtemp(join(tmpdir(),"sfdc-oppo-quote-test-"));
 process.env.LOCALAPPDATA=home;
 process.env.SFDC_LOCAL_COMMAND_ENABLED="1";
 try{
   const prepared=prefillVerifiedKrw(draft(),verifiedSourcePrice(source,ident));
   prepared.description=draftDescription(prepared,calculateDraft(prepared));
   const body=JSON.stringify({mode:"SUBMIT_FOR_APPROVAL",draft:prepared});
   function request(){
     return new Request("http://127.0.0.1:3199/api/sfdc/pair-request-local",{
       method:"POST",
       headers:{"Host":"127.0.0.1:3199","Origin":"http://127.0.0.1:3199",
         "Content-Type":"application/json","X-SFDC-Command":"1","Sec-Fetch-Site":"same-origin"},
       body
     });
   }
   const first=await submitPairRequest(request());
   const a=await first.json();
   assert.equal(first.status,200);
   assert.equal(a.status,"PENDING_APPROVAL");
   assert.equal(a.created,true);
   assert.equal(a.salesforceWrite,false);
   assert.equal(a.savePermitted,false);
   const dir=join(home,"SFDC_Oppo_Quote_Approval_Requests");
   const files=await readdir(dir);
   assert.equal(files.length,1);
   const stored=JSON.parse(await readFile(join(dir,files[0]),"utf8"));
   assert.equal(stored.state,"AWAITING_OPERATOR_APPROVAL");
   assert.equal(stored.approved,false);
   assert.equal(stored.requestedWrite,false);
   const again=await submitPairRequest(request());
   const b=await again.json();
   assert.equal(b.alreadyQueued,true);
   assert.equal(b.created,false);
   assert.equal(b.requestId,a.requestId);
   assert.equal((await readdir(dir)).length,1);
 }finally{
   if(previous.home===undefined)delete process.env.LOCALAPPDATA;
   else process.env.LOCALAPPDATA=previous.home;
   if(previous.enabled===undefined)delete process.env.SFDC_LOCAL_COMMAND_ENABLED;
   else process.env.SFDC_LOCAL_COMMAND_ENABLED=previous.enabled;
   await rm(home,{force:true,recursive:true});
 }
});

test("Ehwa PMP 4 x 5Gb: recurring QC+Seq 57,500, once-only release 30,000, net 260,000",()=>{
 const qid="QID-2026-10-20-407461";
 const signature="9".repeat(64);
 const row=(processId,processName,qty,rate,unit,size)=>({
   source_kind:"VERIFIED_SFDC_KRW_PROCESS_PRICE",source_verified:true,
   created_date:"2026-10-20",quote_id:qid,active:true,
   approval_status:"APPROVED",currency:"KRW",was_usd_converted:false,
   vat_basis:"VAT_EXCLUDED",account_id:"001000000000AAA",
   contact_id:"003000000000AAA",product_signature:signature,
   process_id:processId,process_name:processName,sample_quantity:qty,
   unit_price_krw:String(rate),data_unit:unit,data_size:String(size)
 });
 const evidence={
   version:"sfdc-2026-krw-process-prices-v1",
   source:"SFDC_AUTHENTICATED_READ_ONLY_KRW_PROCESS_LINES",
   generated_at:new Date().toISOString(),salesforce_write_performed:false,
   records:[
     row("Process-2020-04-30-00044","Library QC",4,20000,"NA",""),
     row("Process-2020-04-29-00031","Sequencing by data amount",4,37500,"G raw data",5),
     row("Process-2020-04-29-00032","Analysis by sample",4,0,"G raw data",5),
     row("Process-2020-04-29-00034","Data release",1,30000,"NA",1)
   ]
 };
 const base=draft();
 base.qid=qid;base.name="Korea-Ehwa Univ.-4-PMP-5Gb-Prof. RohTaeYoung";
 base.products[0].productionGb="5";
 base.products[0].serviceLabel="PMP";
 base.products[0].processes=evidence.records.map(x=>({
   processId:x.process_id,name:x.process_name
 }));
 const candidate=historicalKrwReference(evidence,qid,base.products[0]);
 assert.equal(candidate.ok,true,candidate.code);
 assert.equal(candidate.sourceSamples,4);
 assert.equal(candidate.candidateSampleUnitKrw,57500);
 assert.equal(candidate.recurringProcessNetKrw,230000);
 assert.equal(candidate.fixedProcessNetKrw,30000);
 assert.equal(candidate.fixedProcessLines.length,1);
 assert.equal(candidate.fixedProcessLines[0].quantity,1);
 assert.equal(candidate.effectiveHistoricalUnitKrw,65000);
 assert.equal(candidate.sourceProductNetKrw,260000);
 const proposed=prefillHistoricalKrw(base,evidence);
 assert.equal(proposed.products[0].samples,"4");
 assert.equal(proposed.products[0].sampleUnitKrw,"57500");
 assert.equal(proposed.products[0].fixedProcessNetKrw,30000);
 const calculated=calculateDraft(proposed);
 assert.equal(calculated.ok,true);
 assert.equal(calculated.netKrw,260000);
 assert.equal(calculated.vatKrw,26000);
 assert.equal(calculated.grossKrw,286000);
 assert.equal(calculated.items[0].fixedProcessNetKrw,30000);
 assert.deepEqual(calculated.quoteLineItems.map(x=>x.kind),
   ["PRODUCT","FIXED_PRODUCT_PROCESS"]);
 assert.equal(opportunityUnitPriceSummary(calculated).overallPerSampleNetKrw,57500);
 assert.equal(opportunityUnitPriceSummary(calculated).products[0].effectiveUnitNetKrw,65000);
 proposed.description=draftDescription(proposed,calculated);
 assert.match(proposed.description,/Data release 1 × 30,000KRW/);
 assert.ok(!draftPreflight(proposed).errors.includes(
   "HISTORICAL_FIXED_PROCESS_REVALIDATION_REQUIRED"));
 const changed={...proposed,products:[{...proposed.products[0],samples:"6"}]};
 const changedCalc=calculateDraft(changed);
 assert.equal(changedCalc.netKrw,375000);
 assert.equal(changedCalc.items[0].fixedProcessBasisChanged,true);
 assert.ok(draftPreflight(changed).errors.includes(
   "HISTORICAL_FIXED_PROCESS_REVALIDATION_REQUIRED"));
 changed.description=draftDescription(changed,changedCalc);
 assert.equal(validatePairRequest({mode:"SUBMIT_FOR_APPROVAL",draft:changed}).status,
   "NEEDS_REVIEW");
 const invalid={...evidence,records:evidence.records.map(x=>({...x}))};
 invalid.records[3].sample_quantity=2;
 assert.equal(historicalKrwReference(invalid,qid,base.products[0]).ok,false);
});
