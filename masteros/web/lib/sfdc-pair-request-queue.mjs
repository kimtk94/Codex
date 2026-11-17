/** Local-only Quote preparation queue. It NEVER writes to Salesforce.
 * A queued request is not permission to save; customer-specific approval is
 * required later and the independent new-Quote writer remains unavailable.
 */
import {createHash} from "node:crypto";
import {draftPreflight} from "./sfdc-report-quote-draft.mjs";

const ID=/^a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;
const EMAIL=/^QID-[0-9-]{8,50}$/;
export function validatePairRequest(input){
  if(!input||typeof input!=="object"||Array.isArray(input)||
     input.mode!=="SUBMIT_FOR_APPROVAL"||
     !input.draft||typeof input.draft!=="object"||Array.isArray(input.draft))
    return {ok:false,code:"REQUEST_INVALID"};
  const d=input.draft;
  if(typeof d.name!=="string"||d.name.length<5||d.name.length>230||
     !Array.isArray(d.products)||d.products.length<1||d.products.length>12||
     typeof d.qid!=="string"||!EMAIL.test(d.qid)||
     (typeof d.sourceQuoteId!=="string"||d.sourceQuoteId.length>18||
      (d.sourceQuoteId!==""&&!ID.test(d.sourceQuoteId)))||
     typeof d.description!=="string"||d.description.length>3000||
     !["KEEP","CHANGE"].includes(d.accountMode)||
     !["Quote Draft","Prospective"].includes(d.descriptionStatus))
    return {ok:false,code:"REQUEST_FIELDS_INVALID"};
  for(const p of d.products){
    if(!p||typeof p!=="object"||
       typeof p.id!=="string"||p.id.length>130||
       typeof p.serviceLabel!=="string"||p.serviceLabel.length>200||
       typeof p.productionGb!=="string"||p.productionGb.length>25||
       typeof p.samples!=="string"||p.samples.length>20||
       typeof p.sampleUnitKrw!=="string"||p.sampleUnitKrw.length>20||
       typeof p.cloudUnitKrw!=="string"||p.cloudUnitKrw.length>20||
       !Array.isArray(p.processes)||p.processes.length>100)
      return {ok:false,code:"REQUEST_PRODUCT_INVALID"};
  }
  const review=draftPreflight(d);
  const pending=review.status==="PREVIEW_READY"?"PENDING_APPROVAL":"NEEDS_REVIEW";
  const customerPriceMatches=d.products.every(p=>p.priceEvidenceStatus==="LIVE_SFDC_KRW_VERIFIED"&&
      p.priceSourceQuoteId===d.sourceQuoteId&&
      Number(p.priceSourceUnitKrw)===Number(p.sampleUnitKrw)&&
      Number(p.priceSourceCloudUnitKrw)===Number(p.cloudUnitKrw));
  const canonical={
    reference:{sourceQuoteId:d.sourceQuoteId,qid:d.qid,
      opportunityId:d.sourceOpportunityId||""},
    proposed:{name:d.name,date:d.date,closeDate:d.closeDate,
      description:d.description,accountMode:d.accountMode,
      account:d.account,contact:d.contact,
      products:d.products.map(p=>({
        id:p.id,serviceLabel:p.serviceLabel,productionGb:p.productionGb,
        samples:p.samples,sampleUnitKrw:p.sampleUnitKrw,
        cloudUnitKrw:p.cloudUnitKrw,priceEvidenceStatus:p.priceEvidenceStatus||"",
        sourceQuoteProductId:p.id,
        processNames:p.processes.map(x=>x.name),
        processIds:p.processes.map(x=>x.processId),
        amplicon:p.amplicon||null
      }))},
    review:{preflightStatus:review.status,missing:review.errors,
      verifiedNativeRateForUnchangedAmount:customerPriceMatches,
      sourceKrwRateStatus:d.sourceKrwRateStatus||"UNVERIFIED",
      priceChangeRequiresApproval:!customerPriceMatches}
  };
  const requestId="OPPOQUOTE-"+createHash("sha256")
    .update(JSON.stringify(canonical)).digest("hex").slice(0,24);
  return {ok:true,requestId,status:pending,canonical,
    approvalRequired:true,salesforceWrite:false,
    quoteWriterVerified:false,savePermitted:false,
    preflight:review.status,missing:review.errors};
}
