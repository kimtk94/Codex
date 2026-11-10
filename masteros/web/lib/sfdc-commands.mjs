const validId = (v,prefix)=>typeof v==="string" &&
  new RegExp("^"+prefix+"[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$").test(v);
const clean=(x,n=180)=>typeof x==="string"&&x.trim()===x&&x.length>0&&x.length<=n;
export const ACTIONS=["lead_convert","opportunity_create","quote_create"];
/** Separate biological sample unit price from optional AliCloud price (VAT excluded). */
export function opportunityPriceBreakdown({samples,unitPriceNetKrw,cloudUnits=0,cloudUnitNetKrw=0}) {
  if(!Number.isInteger(samples)||samples<1||samples>500||
     !Number.isSafeInteger(unitPriceNetKrw)||unitPriceNetKrw<=0||
     !Number.isInteger(cloudUnits)||cloudUnits<0||cloudUnits>100000||
     !Number.isSafeInteger(cloudUnitNetKrw)||cloudUnitNetKrw<0)
    return {ok:false,code:"OPPO_UNIT_PRICE_REQUIRED"};
  const sampleTotalKrw=samples*unitPriceNetKrw;
  const cloudTotalKrw=cloudUnits*cloudUnitNetKrw;
  const netKrw=sampleTotalKrw+cloudTotalKrw;
  if(!Number.isSafeInteger(netKrw)||netKrw>1_000_000_000_000)
    return {ok:false,code:"OPPO_AMOUNT_OUT_OF_RANGE"};
  return {ok:true,unitPriceNetKrw,samples,sampleTotalKrw,cloudUnits,
    cloudUnitNetKrw,cloudTotalKrw,netKrw,vatKrw:Math.round(netKrw/10),
    grossKrw:netKrw+Math.round(netKrw/10)};
}
export function validateRequest(x) {
  if(!x||typeof x!=="object"||Array.isArray(x)||!ACTIONS.includes(x.action)||
     !["check","save"].includes(x.mode))return {ok:false,code:"ACTION_INVALID"};
  if(x.mode==="save"&&(x.confirmSave!==true||x.noDuplicateConfirmed!==true))
    return {ok:false,code:"SAVE_CONFIRM_REQUIRED"};
  if(x.action==="lead_convert"){
    if(!validId(x.leadId,"00Q")||!clean(x.accountName,150)||
       !clean(x.koreanName,100)||!clean(x.englishName,100)||
       !/^[A-Z][a-zA-Z]+$/.test(x.englishName.replace(/\s/g,"")))
      return {ok:false,code:"LEAD_FIELDS_INVALID"};
    return {ok:true};
  }
  if(x.action==="opportunity_create"){
    if(Object.prototype.hasOwnProperty.call(x,"unitPriceNetKrw")){
      const pricing=opportunityPriceBreakdown(x);
      if(!pricing.ok)return {ok:false,code:pricing.code};
      if(pricing.netKrw!==x.amountKrw)
        return {ok:false,code:"OPPO_UNIT_PRICE_TOTAL_MISMATCH"};
      if(!String(x.progressDescription||"").includes(
        x.unitPriceNetKrw.toLocaleString("en-US")+"KRW/sample"))
        return {ok:false,code:"OPPO_DESCRIPTION_UNIT_PRICE_STALE"};
    }
    if(!validId(x.referenceOpportunityId,"006")||
       !validId(x.accountId,"001")||!validId(x.contactId,"003")||
       !clean(x.opportunityName,230)||!clean(x.accountName,180)||
       !clean(x.contactName,140)||!clean(x.progressDescription,2000)||
       !Number.isInteger(x.samples)||x.samples<1||x.samples>500||
       !Number.isInteger(x.amountKrw)||x.amountKrw<0||x.amountKrw>1_000_000_000_000||
       !/^\d{4}-\d{2}-\d{2}$/.test(x.closeDate) ||
       /^(?:\s*|\s*(?:copy|same as previous)\s*)$/i.test(x.progressDescription))
      return {ok:false,code:"OPPO_FIELDS_INVALID"};
    return {ok:true};
  }
  if(x.action==="quote_create"){
    if(!validId(x.opportunityId,"006")||!validId(x.sourceQuoteId,"a0P")||!clean(x.quoteName,230)||
       !clean(x.accountName,180)||!clean(x.contactName,140)||
       !clean(x.productName,230)||!clean(x.processNames,500)||!Number.isInteger(x.samples)||
       x.samples<1||x.samples>500||!Number.isFinite(x.dataSize)||
       x.dataSize<=0||x.dataSize>100_000)
      return {ok:false,code:"QUOTE_FIELDS_INVALID"};
    return {ok:true};
  }
  return {ok:false,code:"ACTION_INVALID"};
}
export function authorizeCommand({enabled,method,host,origin,fetchSite,header,contentType}){
  if(!enabled)return {ok:false,code:"LOCAL_COMMAND_DISABLED",status:404};
  if(method!=="POST"||!/^127\.0\.0\.1:[0-9]{2,5}$/.test(host||""))
    return {ok:false,code:"LOCAL_ONLY",status:403};
  if(origin!=="http://"+host || (fetchSite && !["same-origin","none"].includes(fetchSite)))
    return {ok:false,code:"ORIGIN_REJECTED",status:403};
  if(header!=="1"||!/^application\/json(?:;|$)/i.test(contentType||""))
    return {ok:false,code:"REQUEST_REJECTED",status:403};
  return {ok:true,status:200};
}
export function freshProgress({accountName,contactName,service,samples,dataSize,unit,referenceAmea,unitPriceNetKrw,cloudUnits=0,cloudUnitNetKrw=0}){
  if(!clean(accountName,180)||!clean(contactName,140)||!clean(service,160)||
     !Number.isInteger(samples)||samples<1||samples>500||
     !Number.isFinite(dataSize)||dataSize<=0)throw Error("PROGRESS_INPUT_INVALID");
  const priced=unitPriceNetKrw===undefined||unitPriceNetKrw===null?
    null:opportunityPriceBreakdown({samples,unitPriceNetKrw,cloudUnits,cloudUnitNetKrw});
  if(priced&&!priced.ok)throw Error("PROGRESS_PRICE_UNVERIFIED");
  return [
    "New request — "+accountName+" / "+contactName,
    "Service: "+service+"; "+samples+" samples; "+dataSize+" "+(unit||"Gb")+" per sample.",
    priced ? "Unit price: "+unitPriceNetKrw.toLocaleString("en-US")+"KRW/sample (VAT excluded); "+
      "sample subtotal: "+priced.sampleTotalKrw.toLocaleString("en-US")+" KRW; "+
      "AliCloud: "+priced.cloudUnits+" × "+cloudUnitNetKrw.toLocaleString("en-US")+" KRW; "+
      "total: "+priced.netKrw.toLocaleString("en-US")+" KRW (VAT excluded)." : "",
    referenceAmea ? "Reference "+referenceAmea+" (product/specifications only)." : "",
    "Opportunity/Quote preparation in progress. PO, sample receipt and payment not confirmed."
  ].filter(Boolean).join("\n");
}
export function alicloudUnits(totalGb){
  if(!Number.isFinite(totalGb)||totalGb<=0||totalGb>1e6)throw Error("TOTAL_GB_INVALID");
  return Math.ceil(totalGb/100);
}
