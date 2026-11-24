/** Verified *live Salesforce source* KRW unit rates, not USD-converted report prices.
 * Apply to the draft only; CRM Save remains separately authorized per record.
 */
import {cloudUnits} from "./sfdc-paired-clone.mjs";

const safeMoney=x=>Number.isSafeInteger(x)&&x>=0&&x<=1e10;
const positive=x=>Number.isInteger(x)&&x>=1&&x<=10000;

export function verifiedSourcePrice(quote,identity){
  if(identity?.status!=="PASS"||identity.sourceVerified!==true||
     quote?.status!=="PASS"||quote.source!=="LIVE_SALESFORCE"||
     quote.read_only!==true||quote.cache?.state!=="LIVE_SOURCE"||
     quote.id!==identity.nativeQuoteId||quote.productCount!==1||
     quote.pricingStatus!=="VERIFIED_PROCESS_LINES"||
     quote.sourceVatRateVerified10Pct!==true||
     quote.cloudLinePresent!==true||quote.sourcePackVerified!==true||
     !positive(quote.samples)||!Number.isFinite(quote.dataSize)||quote.dataSize<=0||
     !safeMoney(quote.sampleUnitNetKrw)||!safeMoney(quote.cloudUnitNetKrw)||
     !safeMoney(quote.totalPriceKrw)||!Array.isArray(quote.processPriceLines)||
     quote.processPriceLines.length<2)
    return {ok:false,code:"SOURCE_KRW_PROCESS_PRICE_NOT_VERIFIED"};
  let expectedCloud;
  try{expectedCloud=cloudUnits(quote.samples,quote.dataSize)}
  catch{return {ok:false,code:"SOURCE_CLOUD_UNIT_UNVERIFIED"}}
  if(quote.sourceCloudUnits!==expectedCloud||
      quote.totalPriceKrw!==quote.samples*quote.sampleUnitNetKrw+
                                expectedCloud*quote.cloudUnitNetKrw)
    return {ok:false,code:"SOURCE_KRW_TOTAL_MISMATCH"};
  let actual=0,cloudRows=0;
  for(const row of quote.processPriceLines){
    if(!row||!safeMoney(row.unitPriceKrw)||!positive(row.sourceQty)||
       typeof row.isCloud!=="boolean")return {ok:false,code:"SOURCE_PROCESS_ROW_UNVERIFIED"};
    actual+=row.unitPriceKrw*row.sourceQty;
    if(row.isCloud){
      cloudRows++;
      if(row.sourceQty!==expectedCloud)
        return {ok:false,code:"SOURCE_CLOUD_UNIT_UNVERIFIED"};
    }else if(row.sourceQty!==quote.samples||!row.packNo)
      return {ok:false,code:"SOURCE_PACK_QTY_UNVERIFIED"};
  }
  if(cloudRows!==1||actual!==quote.totalPriceKrw)
    return {ok:false,code:"SOURCE_PROCESS_SUM_MISMATCH"};
  return {ok:true,code:"LIVE_SFDC_KRW_SOURCE_VERIFIED",
    nativeQuoteId:quote.id,productName:quote.productName,
    productionGb:quote.dataSize,samples:quote.samples,
    sampleUnitKrw:quote.sampleUnitNetKrw,
    cloudUnitKrw:quote.cloudUnitNetKrw,
    sourceTotalNetKrw:quote.totalPriceKrw,
    sourceCloudUnits:quote.sourceCloudUnits,
    source: "LIVE_SFDC_KRW_PROCESS_MATRIX",crmSavePermitted:false};
}

export function prefillVerifiedKrw(draft,evidence){
  if(!draft||!evidence?.ok||!Array.isArray(draft.products)||
     draft.products.length!==1||draft.sourceQuoteId!==evidence.nativeQuoteId)
    return draft;
  const product=draft.products[0];
  if((product.productionGb!==""&&product.productionGb!==undefined&&
       Number(product.productionGb)!==evidence.productionGb)||
     !String(evidence.productName||"").trim())return draft;
  // Do not silently overwrite a price the operator has already edited.
  const wasManual=product.sampleUnitKrw!==""&&
      !["LIVE_SFDC_KRW_VERIFIED","INDEX_2026_KRW_COMPARISON_ONLY"].includes(
        product.priceEvidenceStatus);
  if(wasManual)return {...draft,priceCandidate:evidence};
  const update={...product,
    productionGb:product.productionGb||String(evidence.productionGb),
    samples:product.samples||String(evidence.samples),
    sampleUnitKrw:String(evidence.sampleUnitKrw),
    cloudUnitKrw:String(evidence.cloudUnitKrw),
    // An independently verified native product matrix replaces the tentative
    // historical comparison in full; never stack fixed charges on it twice.
    fixedProcessLines:[],fixedProcessNetKrw:0,fixedProcessSourceSamples:null,
    priceEvidenceStatus:"LIVE_SFDC_KRW_VERIFIED",
    priceSourceQuoteId:evidence.nativeQuoteId,
    priceSourceUnitKrw:evidence.sampleUnitKrw,
    priceSourceCloudUnitKrw:evidence.cloudUnitKrw};
  const products=[update];
  return {...draft,products,sourceKrwRateStatus:"VERIFIED",
    referenceDefaults:{...draft.referenceDefaults,
      products:draft.referenceDefaults?.products?.map((p,i)=>
        i===0?{...p,productionGb:update.productionGb,samples:update.samples,
                    sampleUnitKrw:update.sampleUnitKrw,
                    cloudUnitKrw:update.cloudUnitKrw}:p)}};
}
