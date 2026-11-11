import {derivePairPrice} from "./sfdc-paired-clone.mjs";

/** Audit the actual KRW process-price matrix of one Salesforce source Quote.
 * The 'Pack No.' source column is an identifier, NOT a quantity and must
 * never be counted as additional biological samples.
 */
export function verifiedQuoteProcessBreakdown(quote,samples,dataSizeGb,requestedSampleRate=null){
  const projection=derivePairPrice(quote,samples,dataSizeGb);
  if(!projection.ok)return {ok:false,code:projection.code,items:[]};
  const source=quote?.processPriceLines||[];
  if(source.length===0||source.length>25)return {ok:false,code:"QUOTE_PROCESS_LINES_MISSING",items:[]};
  const items=[];
  for(const line of source){
    if(!line||typeof line.processName!=="string"||!line.processName.trim()||
      !Number.isSafeInteger(line.unitPriceKrw)||line.unitPriceKrw<0||
      !Number.isInteger(line.sourceQty)||line.sourceQty<1||
      !Number.isSafeInteger(line.sourceNetKrw)||
      line.sourceQty*line.unitPriceKrw!==line.sourceNetKrw||
      typeof line.isCloud!=="boolean")
      return {ok:false,code:"QUOTE_PROCESS_LINE_INVALID",items:[]};
    const qty=line.isCloud?projection.cloudUnits:samples;
    items.push({name:line.processName,processType:line.processType||"",
      packNo:String(line.packNo||"").slice(0,80),
      quantity:qty,unitPriceKrw:line.unitPriceKrw,
      projectedNetKrw:qty*line.unitPriceKrw,isCloud:line.isCloud,
      sourceQuantity:line.sourceQty});
  }
  const sampleRate=items.filter(x=>!x.isCloud).reduce((n,x)=>n+x.unitPriceKrw,0);
  const cloudRate=items.filter(x=>x.isCloud).reduce((n,x)=>n+x.unitPriceKrw,0);
  if(sampleRate!==projection.unitPriceNetKrw||cloudRate!==projection.cloudUnitNetKrw||
    items.reduce((n,x)=>n+x.projectedNetKrw,0)!==projection.netKrw)
    return {ok:false,code:"QUOTE_PROCESS_PRICE_SUM_MISMATCH",items:[]};
  const changed=requestedSampleRate!==null&&requestedSampleRate!==sampleRate;
  const packs=[...new Set(items.filter(x=>!x.isCloud).map(x=>x.packNo).filter(Boolean))];
  return {ok:true,items,
    originalSampleRateKrw:sampleRate,sourceTotalNetKrw:projection.netKrw,
    manualOverride:changed,
    // Same physical specimens per Pack; never multiply by Region or process.
    pack:{biologicalSamples:samples,quantity:samples,
      sourcePackNo:packs.length===1?packs[0]:"",
      sourcePackAmbiguous:packs.length>1,
      needsReview:true,policy:"SAME_PHYSICAL_SAMPLE_COUNT"},
    priceAllocation:changed?"PROCESS_ALLOCATIONS_MUST_BE_REVISED":
      "SOURCE_KRW_PROCESS_RATES_VERIFIED",
    vatExcluded:true
  };
}

export function reportProcessComposition(product){
  const rows=(product?.processes||[]).map(p=>({
    name:String(p.name||"").trim(),dataUnit:String(p.dataUnit||"").trim(),
    sourceUnitUsd:String(p.sourceUnitUsd||"").trim(),
    krwUnitVerified:false,
    quantityBasis:/cloud/i.test(p.name||"")?"100_GB":
      /(?:Gb|Gbase)/i.test(p.dataUnit||"")?"DATA_SIZE":
      "BIOLOGICAL_SAMPLE_OR_PACK_REVIEW"
  })).filter(x=>x.name);
  return {rows,pack:{
    quantity:Number.isInteger(Number(product?.samples))&&Number(product.samples)>0?
      Number(product.samples):null,
    sourcePackNo:"",needsReview:true,policy:"SAME_PHYSICAL_SAMPLE_COUNT"},
    priceBasis:"USD_CONVERTED_REFERENCE_ONLY",krwUnitVerified:false};
}
