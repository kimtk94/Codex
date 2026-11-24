/** Shipping/return fees are Quote Fee items, never per-sample or per-Process rates.
 * Provenance: local authenticated Salesforce readback. No CRM writer.
 */
const isMoney=n=>Number.isSafeInteger(n)&&n>=0&&n<=1_000_000_000_000;
const FEE_TYPES=new Set(["SP Sample Shipping Fee","Sample Return Fee"]);
const QID=/^a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;
const PID=/^[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?$/;

export function isVerifiedSourceFee(evidence,sourceQuoteId){
  if(!evidence||evidence.status!=="PASS"||
     evidence.source!=="LIVE_SALESFORCE_READ_ONLY"||
     evidence.salesforce_write!==false||
     !QID.test(sourceQuoteId||"")||
     evidence.nativeQuoteId!==sourceQuoteId||
     !Array.isArray(evidence.feeLines)||evidence.feeLines.length>100||
     evidence.feeCount!==evidence.feeLines.length||
     !isMoney(evidence.totalFeeKrw))return false;
  let total=0;
  for(const fee of evidence.feeLines){
    if(!fee||!FEE_TYPES.has(fee.feeType)||fee.currency!=="KRW"||
       !PID.test(fee.sourceQuoteProductId||"")||
       typeof fee.productName!=="string"||!fee.productName.trim()||
       fee.productName.length>200||!isMoney(fee.feeKrw)||fee.feeKrw<=0)
      return false;
    total+=fee.feeKrw;
    if(!isMoney(total))return false;
  }
  return total===evidence.totalFeeKrw;
}

export function attachVerifiedSourceFees(draft,evidence){
  if(!draft||!isVerifiedSourceFee(evidence,draft.sourceQuoteId))return draft;
  const sourceFeeLines=evidence.feeLines.map((fee,i)=>({
    key:"quote-fee-"+i,
    feeType:fee.feeType,feeKrw:fee.feeKrw,
    productName:fee.productName,
    sourceQuoteProductId:fee.sourceQuoteProductId,
    currency:"KRW"
  }));
  return {...draft,sourceFeeLines,feeEvidenceStatus:"LIVE_SFDC_QUOTATION_FEE_VERIFIED",
    // Loading a reference never silently switches an old fee into a new Quote.
    feeMode:draft.feeMode==="KEEP"?"KEEP":"EXCLUDE"};
}

export function quoteFeeBreakdown(draft){
  const mode=draft?.feeMode||"EXCLUDE";
  if(!["EXCLUDE","KEEP"].includes(mode))
    return {ok:false,code:"QUOTE_FEE_MODE_INVALID",feeNetKrw:null,quoteFeeItems:[]};
  if(mode==="EXCLUDE")return {ok:true,code:"QUOTE_FEE_EXCLUDED",
    feeNetKrw:0,quoteFeeItems:[],included:false};
  const raw=draft?.sourceFeeLines;
  if(draft?.feeEvidenceStatus!=="LIVE_SFDC_QUOTATION_FEE_VERIFIED"||
     !Array.isArray(raw)||!raw.length||raw.length>100)
    return {ok:false,code:"QUOTE_FEE_SOURCE_NOT_VERIFIED",
      feeNetKrw:null,quoteFeeItems:[],included:false};
  let sum=0;
  const quoteFeeItems=[];
  for(const row of raw){
    if(!row||!FEE_TYPES.has(row.feeType)||row.currency!=="KRW"||
       !PID.test(row.sourceQuoteProductId||"")||
       !isMoney(row.feeKrw)||row.feeKrw<=0||
       typeof row.productName!=="string"||row.productName.length>200||
       !row.productName.trim())
      return {ok:false,code:"QUOTE_FEE_LINE_INVALID",
        feeNetKrw:null,quoteFeeItems:[],included:false};
    sum+=row.feeKrw;
    if(!isMoney(sum))
      return {ok:false,code:"QUOTE_FEE_AMOUNT_OVERFLOW",
        feeNetKrw:null,quoteFeeItems:[],included:false};
    quoteFeeItems.push({kind:"QUOTE_FEE",feeType:row.feeType,
      sourceQuoteProductId:row.sourceQuoteProductId,
      sourceProductName:row.productName,quantity:1,
      unitPriceKrw:row.feeKrw,netKrw:row.feeKrw,
      referenceOnly:true,needsNativeRecheck:true});
  }
  return {ok:true,code:"QUOTE_FEE_REFERENCE_RECHECK_REQUIRED",
    feeNetKrw:sum,quoteFeeItems,included:true};
}
