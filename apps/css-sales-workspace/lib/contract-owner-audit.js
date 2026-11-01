'use strict';
// A read-only owner diagnostic must never certify contracts, issued invoices,
// payment, or Actual based on a candidate/legacy Watch X.
const WRONG_WATCH_X='X209SC26065705-Z01';
const CORRECT_FINANCE_CANDIDATE='X209SC26107211';
const REFERENCE_AMEA='AMEA2026090309';
function inspectOwnerContractReview(review){
  if(!review||review.available!==true||review.verified!==false||
     !Array.isArray(review.items)||!review.items.length)return false;
  if(!Number.isSafeInteger(review.candidateCount)||!Number.isSafeInteger(review.missingCount)||
     review.candidateCount<0||review.missingCount<0||
     review.candidateCount+review.missingCount!==review.items.length)return false;
  if(!['REVIEW_ONLY','REVIEW_SOURCE_STALE'].includes(review.status))return false;
  const amea=new Set(),bases=new Set();
  let candidates=0;
  for(const item of review.items){
    if(!/^AMEA20\d{8}$/.test(item?.amea||'')||amea.has(item.amea))return false;
    amea.add(item.amea);
    if(item.attributionVerified!==false||item.issuanceVerified!==false||
       item.paymentVerified!==false||item.revenueActualApproved!==false)return false;
    if(item.candidateX){
      candidates++;
      const base=String(item.candidateX).split('-')[0];
      if(!/^X[A-Z0-9]{10,30}$/.test(base)||bases.has(base))return false;
      bases.add(base);
      if(item.gate!=='CANDIDATE_ONLY_REQUIRES_ORIGINAL_CONTRACT_REVIEW')return false;
    }else if(item.gate!=='QUARANTINE_NO_CONTRACT_ATTRIBUTION')return false;
  }
  if(candidates!==review.candidateCount)return false;
  // This known wrong-Watch mapping is the regression control for owner review.
  // If this AMEA stops being unissued, no manual release acceptance is inferred.
  const known=review.items.find(item=>item.amea===REFERENCE_AMEA);
  if(!known||known.unsafeWatchX!==WRONG_WATCH_X||
     known.candidateX!==CORRECT_FINANCE_CANDIDATE||
     known.onlineH||known.onlineStage||
     known.state!=='FINANCE_AMEA_CANDIDATE')return false;
  return true;
}
module.exports={inspectOwnerContractReview};
