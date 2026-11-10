/** Read-only source identity reconciliation; never authorizes Salesforce saving. */
const s=value=>String(value??"").trim();
const id=(value,prefix)=>typeof value==="string"&&new RegExp("^"+prefix+"[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$").test(value);
const hold=code=>({status:"HOLD",code,sourceVerified:false,canSave:false});

export function reconcileQuoteSource(feishu,quote,opportunity){
  if(!feishu||feishu.status!=="PASS")return hold("FEISHU_REFERENCE_UNAVAILABLE");
  const ref=feishu.reference||{};
  if(!id(feishu.sfdc_record_id,"a0P"))return hold("FEISHU_NATIVE_QUOTE_ID_UNAVAILABLE");
  if(!quote||quote.status!=="PASS"||!opportunity||opportunity.status!=="PASS")
    return hold("SALESFORCE_UI_READ_UNAVAILABLE");
  for(const item of [quote,opportunity]){
    if(item.source!=="LIVE_SALESFORCE"||item.read_only!==true)
      return hold("SALESFORCE_UI_PROVENANCE_UNVERIFIED");
    if(item.cache?.state!=="LIVE_SOURCE")
      return hold("SALESFORCE_LIVE_REFRESH_REQUIRED");
  }
  if(quote.id!==feishu.sfdc_record_id||!id(quote.id,"a0P"))
    return hold("QUOTE_ID_MISMATCH");
  if(!id(quote.opportunityId,"006")||opportunity.id!==quote.opportunityId)
    return hold("QUOTE_OPPORTUNITY_LINK_MISMATCH");
  if(!id(quote.accountId,"001")||!id(opportunity.accountId,"001")||
     quote.accountId!==opportunity.accountId||quote.accountId!==ref.accountId)
    return hold("SOURCE_ACCOUNT_ID_MISMATCH");
  if(!id(quote.contactId,"003")||!id(opportunity.contactId,"003")||
     quote.contactId!==opportunity.contactId)
    return hold("SOURCE_CONTACT_ID_MISMATCH");
  if(id(ref.contactId,"003")&&ref.contactId!==quote.contactId)
    return hold("FEISHU_CONTACT_ID_MISMATCH");
  if(!s(quote.name)||!s(opportunity.name)||!s(opportunity.accountName)||
     !s(opportunity.contactName))
    return hold("SOURCE_IDENTITY_FIELDS_MISSING");
  const nameReview=s(quote.name)!==s(opportunity.name)||
    (s(ref.opportunityName)!==""&&s(ref.opportunityName)!==s(opportunity.name));
  return {
    status:"PASS",code:nameReview?"SOURCE_IDENTITIES_VERIFIED_NAME_REVIEW":"SOURCE_IDENTITIES_VERIFIED",
    sourceVerified:true,canSave:false,nameReview,
    nativeQuoteId:quote.id,nativeOpportunityId:opportunity.id,
    quoteName:quote.name,opportunityName:opportunity.name,
    account:{id:opportunity.accountId,name:opportunity.accountName},
    contact:{id:opportunity.contactId,externalId:s(ref.contactExternalId),
      name:opportunity.contactName,email:s(ref.contactEmail)},
    customerIdsMatched:true,krwRateVerified:false
  };
}

export function applyVerifiedSource(draft,result){
  if(!draft||result?.status!=="PASS"||result.sourceVerified!==true||
     draft.accountMode!=="KEEP")return draft;
  if(draft.sourceQuoteId!==result.nativeQuoteId||
     draft.referenceAccount?.id!==result.account.id)return draft;
  // Never overwrite user-edited Product/Gb/sample/price/name/Description.
  const account={...result.account},contact={...result.contact};
  return {...draft,account,contact,referenceAccount:account,referenceContact:contact,
    sourceOpportunityId:result.nativeOpportunityId,
    referenceDefaults:{...draft.referenceDefaults,account:{...account},contact:{...contact}}};
}
