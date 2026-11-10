/** Read-only source identity reconciliation; never authorizes Salesforce saving. */
const s=value=>String(value??"").trim();
const id=(value,prefix)=>typeof value==="string"&&new RegExp("^"+prefix+"[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$").test(value);
const hold=code=>({status:"HOLD",code,sourceVerified:false,canSave:false});

// Salesforce 15-char IDs are case sensitive; 18-char IDs contain the same
// 15 characters plus a 3-character capitalization checksum.
// QQ/Feishu may retain the 15-char form while Salesforce UI returns 18.
const CHECKSUM_ALPHABET="ABCDEFGHIJKLMNOPQRSTUVWXYZ012345";
export function canonicalSalesforceId(value,prefix){
  if(!id(value,prefix))return null;
  const first15=value.slice(0,15);
  if(value.length===18){
    let expected="";
    for(let block=0;block<3;block++){
      let mask=0;
      for(let pos=0;pos<5;pos++){
        const ch=first15[block*5+pos];
        if(ch>="A"&&ch<="Z")mask|=1<<pos;
      }
      expected+=CHECKSUM_ALPHABET[mask];
    }
    if(value.slice(15)!==expected)return null;
  }
  return first15;
}
export function sameSalesforceId(a,b,prefix){
  const left=canonicalSalesforceId(a,prefix);
  return left!==null&&left===canonicalSalesforceId(b,prefix);
}

export function reconcileQuoteSource(feishu,quote,opportunity){
  if(!feishu||feishu.status!=="PASS")return hold("FEISHU_REFERENCE_UNAVAILABLE");
  const ref=feishu.reference||{};
  if(!canonicalSalesforceId(feishu.sfdc_record_id,"a0P"))return hold("FEISHU_NATIVE_QUOTE_ID_UNAVAILABLE");
  if(!quote||quote.status!=="PASS"||!opportunity||opportunity.status!=="PASS")
    return hold("SALESFORCE_UI_READ_UNAVAILABLE");
  for(const item of [quote,opportunity]){
    if(item.source!=="LIVE_SALESFORCE"||item.read_only!==true)
      return hold("SALESFORCE_UI_PROVENANCE_UNVERIFIED");
    if(item.cache?.state!=="LIVE_SOURCE")
      return hold("SALESFORCE_LIVE_REFRESH_REQUIRED");
  }
  if(!sameSalesforceId(quote.id,feishu.sfdc_record_id,"a0P"))
    return hold("QUOTE_ID_MISMATCH");
  if(!sameSalesforceId(opportunity.id,quote.opportunityId,"006"))
    return hold("QUOTE_OPPORTUNITY_LINK_MISMATCH");
  if(!sameSalesforceId(quote.accountId,opportunity.accountId,"001")||
     !sameSalesforceId(quote.accountId,ref.accountId,"001"))
    return hold("SOURCE_ACCOUNT_ID_MISMATCH");
  if(!sameSalesforceId(quote.contactId,opportunity.contactId,"003"))
    return hold("SOURCE_CONTACT_ID_MISMATCH");
  if(ref.contactId&&
     !sameSalesforceId(ref.contactId,quote.contactId,"003"))
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
  if(!sameSalesforceId(draft.sourceQuoteId,result.nativeQuoteId,"a0P")||
     !sameSalesforceId(draft.referenceAccount?.id,result.account.id,"001"))return draft;
  // Never overwrite user-edited Product/Gb/sample/price/name/Description.
  const account={...result.account},contact={...result.contact};
  return {...draft,account,contact,referenceAccount:account,referenceContact:contact,
    sourceOpportunityId:result.nativeOpportunityId,
    referenceDefaults:{...draft.referenceDefaults,account:{...account},contact:{...contact}}};
}
