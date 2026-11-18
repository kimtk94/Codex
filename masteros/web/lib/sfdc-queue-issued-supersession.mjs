/** Pure, no-Save migration of immutable historical Quote Draft approval queues.
 *
 * Never edits the old queue or infers approval. Only updates the one authorized
 * Progress Description status and creates a new SHA256 requestId. All other
 * canonical data (Account/Contact, prices, Product/Process, fees, Name) remains
 * byte-equivalent after JSON serialization.
 */
import {createHash} from "node:crypto";

const ID=/^OPPOQUOTE-[a-f0-9]{24}$/;
const idOf=c=>"OPPOQUOTE-"+createHash("sha256")
  .update(JSON.stringify(c)).digest("hex").slice(0,24);

export function supersedeQueueQuoteDraft(old,originalId){
 if(!old||typeof old!=="object"||Array.isArray(old)||
   !ID.test(originalId)||old.requestId!==originalId||
   !old.canonical||typeof old.canonical!=="object"||
   idOf(old.canonical)!==originalId)
   return {ok:false,code:"SOURCE_QUEUE_IDENTITY_INVALID"};
 if(old.state!=="AWAITING_OPERATOR_APPROVAL"||
    old.approved!==false||old.requestedWrite!==false||
    old.salesforceWrite!==false||old.savePermitted!==false)
   return {ok:false,code:"SOURCE_QUEUE_ALREADY_APPROVED_OR_WRITTEN"};
 const description=old.canonical?.proposed?.description;
 if(typeof description!=="string"||
   (description.match(/\bQuote Draft\b/g)||[]).length!==1||
   description.includes("Quote Issued"))
   return {ok:false,code:"SOURCE_QUOTE_DRAFT_NOT_UNIQUE"};
 const canonical=JSON.parse(JSON.stringify(old.canonical));
 canonical.proposed.description=description.replace(/\bQuote Draft\b/,"Quote Issued");
 const nextId=idOf(canonical);
 if(nextId===originalId)return {ok:false,code:"NO_CANONICAL_CHANGE"};
 const entry={
   ...old,requestId:nextId,canonical,
   status:"NEEDS_REVIEW",state:"AWAITING_OPERATOR_APPROVAL",
   approved:false,requestedWrite:false,salesforceWrite:false,
   savePermitted:false,quoteWriterVerified:false,
   approvalRequired:true,
   supersedesRequestId:originalId,
   revisionKind:"QUOTE_ISSUED_WORDING_ONLY__NO_CRM_WRITE",
   receivedAtUtc:new Date().toISOString()
 };
 return {ok:true,requestId:nextId,sourceRequestId:originalId,
   unchangedOriginal:true,crmWrites:0,newQueue:entry};
}
