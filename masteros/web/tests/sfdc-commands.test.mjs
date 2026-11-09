import test from "node:test";
import assert from "node:assert/strict";
import {validateRequest,authorizeCommand,freshProgress,alicloudUnits} from "../lib/sfdc-commands.mjs";
const lead={action:"lead_convert",mode:"check",leadId:"00Q000000000000AAA",
  accountName:"Example University",koreanName:"김민수",englishName:"KimMinSu"};
const opportunity={action:"opportunity_create",mode:"check",
  referenceOpportunityId:"006000000000000AAA",accountId:"001000000000000AAA",
  contactId:"003000000000000AAA",accountName:"Example",contactName:"KimMinSu",
  opportunityName:"Korea-Example-12-mRNA",samples:12,amountKrw:2400000,
  closeDate:"2026-11-30",progressDescription:"New inquiry — 12 samples."};
const quote={action:"quote_create",mode:"check",
  opportunityId:"006000000000000AAA",sourceQuoteId:"a0P000000000000AAA",
  quoteName:"Korea-Example-12-mRNA",accountName:"Example",contactName:"KimMinSu",
  productCategory:"Eukaryotic mRNA",productName:"Plant and Animal Eukaryotic mRNA",
  samples:12,dataSize:12,processNames:"NovaSeq Reagent Kit (500 Cycles), Data quality control"};
test("input validation for Lead, Oppo, Quote",()=>{
  for(const x of [lead,opportunity,quote])assert.equal(validateRequest(x).ok,true);
  assert.equal(validateRequest({...lead,leadId:"00QBAD"}).ok,false);
  assert.equal(validateRequest({...quote,sourceQuoteId:""}).ok,false);
  assert.equal(validateRequest({...opportunity,progressDescription:""}).ok,false);
  assert.equal(validateRequest({...opportunity,samples:0}).ok,false);
  assert.equal(validateRequest({...lead,mode:"save"}).code,"SAVE_CONFIRM_REQUIRED");
  assert.equal(validateRequest({...lead,mode:"save",confirmSave:true,noDuplicateConfirmed:true}).ok,true);
});
test("strict loopback origin and user-action gate",()=>{
  const x={enabled:true,method:"POST",host:"127.0.0.1:3000",
    origin:"http://127.0.0.1:3000",fetchSite:"same-origin",
    header:"1",contentType:"application/json"};
  assert.equal(authorizeCommand(x).ok,true);
  for(const changes of [
    {enabled:false},{method:"GET"},{host:"0.0.0.0:3000"},
    {host:"localhost:3000"},{origin:"http://evil.test"},
    {fetchSite:"cross-site"},{header:""},{contentType:"text/plain"}
  ])assert.equal(authorizeCommand({...x,...changes}).ok,false);
});
test("progress must be new and avoids confirmed PO / sample status",()=>{
  const s=freshProgress({accountName:"Gencurix",contactName:"KimJiJun",
    service:"mRNA-Seq",samples:12,dataSize:12,unit:"Gb",
    referenceAmea:"AMEA2026091421"});
  assert.match(s,/12 samples/);assert.match(s,/specifications only/);
  assert.match(s,/not confirmed/);
  assert.doesNotMatch(s,/0914 Quote Issued/);
  assert.equal(alicloudUnits(150),2);
  assert.equal(alicloudUnits(100),1);
  assert.equal(alicloudUnits(201),3);
});
