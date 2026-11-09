export function validRecordPickerRequest(x){
  if(!x||typeof x!=="object"||Array.isArray(x)||
     !["lead","opportunity","quote"].includes(x.resource)||
     !["list","detail"].includes(x.mode))return {ok:false,code:"PICKER_INVALID"};
  if(x.mode==="list"){
    if(typeof x.query!=="string"||x.query.length>100)
      return {ok:false,code:"SEARCH_INVALID"};
  }else{
    const prefix={lead:"00Q",opportunity:"006",quote:"a0P"}[x.resource];
    if(typeof x.recordId!=="string"||
      !new RegExp("^"+prefix+"[a-zA-Z0-9]{12}(?:[a-zA-Z0-9]{3})?$").test(x.recordId))
      return {ok:false,code:"RECORD_ID_INVALID"};
  }
  return {ok:true};
}
export function recordToDraft(resource,record,existing) {
  if(!record||record.status!=="PASS"||record.resource!==resource)return null;
  if(resource==="lead")return {...existing,
      leadId:record.id,
      accountName:record.accountName||"",
      koreanName:record.koreanName||"",
      englishName:record.englishName||""};
  if(resource==="opportunity")return {...existing,
      referenceOpportunityId:record.id,accountId:record.accountId||"",
      contactId:record.contactId||"",accountName:record.accountName||"",
      contactName:record.contactName||"",opportunityName:record.name||"",
      samples:Number.isInteger(record.samples)&&record.samples>0?record.samples:existing.samples,
      amountKrw:Number.isInteger(record.amountKrw)?record.amountKrw:existing.amountKrw,
      closeDate:record.closeDate||existing.closeDate,service:record.service||"",
      dataSize:Number.isFinite(record.dataSize)&&record.dataSize>0?record.dataSize:existing.dataSize,
      unit:record.unit||"Gb",
      progressDescription:"",referenceAmea:""};
  return {...existing,
      sourceQuoteId:record.id,
      opportunityId:record.opportunityId||"",
      quoteName:record.opportunityName||"",
      accountName:record.accountName||"",
      contactName:record.contactName||"",
      productName:record.productName||"",
      productCategory:record.productCategory||"",
      processNames:record.processNames||"",
      samples:Number.isInteger(record.samples)&&record.samples>0?record.samples:existing.samples,
      dataSize:Number.isFinite(record.dataSize)&&record.dataSize>0?record.dataSize:existing.dataSize};
}
export function recordSelectionSummary(record){
  if(!record||record.status!=="PASS")return null;
  return {id:record.id,name:record.name||"",source:record.source,
    warnings:record.resource==="opportunity"?
      ["Progress Description must be newly written",
       ...(record.dataSizeSource==="OPPO_NAME_ESTIMATE"?["Data amount inferred from opportunity name"]:[])]:
      record.resource==="quote"?["Validate existing product, processes, quantities and pricing before Save"]:
      ["Confirm the correct Account and English Contact name"]};
}
