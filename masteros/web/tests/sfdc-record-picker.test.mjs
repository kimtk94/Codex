import test from "node:test";
import assert from "node:assert/strict";
import {validRecordPickerRequest,recordToDraft,recordSelectionSummary} from "../lib/sfdc-record-picker.mjs";

const id={lead:"00Q000000000000AAA",opportunity:"006000000000000AAA",
 quote:"a0P000000000000AAA"};
test("picker accepts only bounded list search or correct record IDs",()=>{
 for(const resource of Object.keys(id)){
  assert.equal(validRecordPickerRequest({mode:"list",resource,query:"김지훈"}).ok,true);
  assert.equal(validRecordPickerRequest({mode:"detail",resource,recordId:id[resource]}).ok,true);
 }
 assert.equal(validRecordPickerRequest({mode:"detail",resource:"lead",recordId:id.opportunity}).ok,false);
 assert.equal(validRecordPickerRequest({mode:"detail",resource:"quote",recordId:"https://evil/"}).ok,false);
 assert.equal(validRecordPickerRequest({mode:"list",resource:"lead",query:"x".repeat(101)}).ok,false);
});
test("Lead load pre-populates existing fields, keeps source id",()=>{
 const item={status:"PASS",resource:"lead",id:id.lead,name:"김태훈",
  koreanName:"김태훈",accountName:"학교",englishName:"KimTaeHoon"};
 const input=recordToDraft("lead",item,{leadId:"",accountName:"",koreanName:"",englishName:""});
 assert.equal(input.leadId,id.lead);
 assert.equal(input.accountName,"학교");
 assert.equal(input.englishName,"KimTaeHoon");
});
test("Oppo clone preserves amounts and identity but never carries over progress",()=>{
 const src={status:"PASS",resource:"opportunity",id:id.opportunity,
  accountId:"001000000000000AAA",contactId:"003000000000000AAA",
  name:"Korea-Jeju Univ.-42-mRNASeq",accountName:"제주대학교",contactName:"이태백",
  samples:42,amountKrw:8400000,dataSize:12,service:"Eukaryotic mRNA Sequencing",
  closeDate:"2026-11-30",progressDescriptionSource:"0914 Quote Issued"};
 const input=recordToDraft("opportunity",src,{samples:1,dataSize:1,amountKrw:0,closeDate:"",unit:"Gb"});
 assert.equal(input.samples,42);
 assert.equal(input.amountKrw,8400000);
 assert.equal(input.progressDescription,"");
 assert.equal(input.referenceOpportunityId,id.opportunity);
 assert.ok(recordSelectionSummary(src).warnings.some(s=>s.includes("Progress")));
});
test("Quote source maps actual product and parent opportunity; user can alter quantity",()=>{
 const src={status:"PASS",resource:"quote",id:id.quote,opportunityId:id.opportunity,
   opportunityName:"Korea-Jeju Univ.-42-mRNASeq",productName:"Plant and Animal Eukaryotic mRNA (WOBI)",
   accountName:"제주대학교",contactName:"이태백",samples:null,dataSize:null};
 const input=recordToDraft("quote",src,{samples:1,dataSize:1,processNames:""});
 assert.equal(input.sourceQuoteId,id.quote);
 assert.equal(input.productName,"Plant and Animal Eukaryotic mRNA (WOBI)");
 assert.equal(input.opportunityId,id.opportunity);
 assert.equal(input.processNames,"");
 assert.equal(input.quoteName,src.opportunityName);
});
