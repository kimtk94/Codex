/** Group QQ personal outbound evidence for SFDC Leads without inventing proof of non-sending.
 * A Lead is SENT only if the source sheet class AND numeric counts agree.
 * Missing/contradictory evidence belongs to REVIEW, never "not sent".
 */
function count(value) {
  if(typeof value==="number")return Number.isSafeInteger(value)&&value>=0?value:null;
  const raw=String(value??"").trim();
  if(!/^\d+$/.test(raw))return null;
  const n=Number(raw);
  return Number.isSafeInteger(n)?n:null;
}
export function leadOutboundGroup(lead){
  if(!lead||typeof lead!=="object")return "REVIEW";
  const after=count(lead.afterCount),ever=count(lead.everCount);
  if(after===null||ever===null||ever<after)return "REVIEW";
  switch(lead.evidence){
    case "SENT_AFTER_LEAD_CONFIRMED":
      return after>0?"SENT":"REVIEW";
    case "SENT_BEFORE_LEAD_ONLY":
      return after===0&&ever>0?"SENT":"REVIEW";
    case "NO_PERSONAL_OUTBOUND_EVIDENCE":
      return after===0&&ever===0?"NO_EVIDENCE":"REVIEW";
    default:
      return "REVIEW";
  }
}
export function leadOutboundSummary(leads){
  const result={all:0,sent:0,sentAfter:0,sentBeforeOnly:0,noEvidence:0,review:0};
  for(const lead of Array.isArray(leads)?leads:[]){
    result.all++;
    const group=leadOutboundGroup(lead);
    if(group==="SENT"){
      result.sent++;
      if(lead.evidence==="SENT_AFTER_LEAD_CONFIRMED")result.sentAfter++;
      else result.sentBeforeOnly++;
    }else if(group==="NO_EVIDENCE")result.noEvidence++;
    else result.review++;
  }
  return result;
}
export function leadGroupMatches(lead,group,detail="ALL"){
  const actual=leadOutboundGroup(lead);
  if(group!=="ALL"&&actual!==group)return false;
  return detail==="ALL"||lead.evidence===detail;
}
