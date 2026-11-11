import {derivePairPrice} from "./sfdc-paired-clone.mjs";

/** Evidence-only SFDC Quote process/Pack projection.
 * Each process fee stays individually visible. Rates do not migrate between
 * processes when a user overrides the overall sample price.
 */
export function quoteProcessReview(quote,samples,dataSizeGb){
  if(quote?.pricingStatus!=="VERIFIED_PROCESS_LINES"||
      !Array.isArray(quote.processPriceLines)||!quote.processPriceLines.length||
      !Number.isInteger(samples)||samples<1||samples>500||
      !Number.isFinite(dataSizeGb)||dataSizeGb<=0||
      dataSizeGb!==quote.dataSize)
    return {ok:false,code:"PROCESS_LINES_NOT_VERIFIED",lines:[],packStatus:"NOT_VERIFIED"};
  const projection=derivePairPrice(quote,samples,dataSizeGb);
  if(!projection.ok)
    return {ok:false,code:projection.code,lines:[],packStatus:"NOT_VERIFIED"};
  const lines=[];
  for(const row of quote.processPriceLines){
    if(typeof row.processName!=="string"||!row.processName.trim()||
       !Number.isSafeInteger(row.unitPriceKrw)||row.unitPriceKrw<0||
       !Number.isInteger(row.sourceQty)||row.sourceQty<1||
       (row.sourceNetKrw!==undefined&&
         (!Number.isSafeInteger(row.sourceNetKrw)||
          row.sourceQty*row.unitPriceKrw!==row.sourceNetKrw))||
       typeof row.isCloud!=="boolean")
      return {ok:false,code:"PROCESS_ROW_UNVERIFIED",lines:[],packStatus:"NOT_VERIFIED"};
    const quantity=row.isCloud?Math.ceil(samples*dataSizeGb/100):samples;
    const netKrw=quantity*row.unitPriceKrw;
    if(!Number.isSafeInteger(netKrw))return {ok:false,code:"PROCESS_TOTAL_INVALID",lines:[],packStatus:"NOT_VERIFIED"};
    lines.push({name:row.processName,packNo:String(row.packNo??"").trim(),
      isCloud:row.isCloud===true,unitKrw:row.unitPriceKrw,quantity,netKrw});
  }
  const samplePacks=new Set(lines.filter(x=>!x.isCloud).map(x=>x.packNo).filter(Boolean));
  const allPacked=lines.every(x=>x.packNo);
  const packStatus=!allPacked?"REVIEW_MISSING_PACK":
    samplePacks.size===1?"PASS":"REVIEW_SAME_SAMPLE_MULTIPLE_PACKS";
  const netKrw=lines.reduce((sum,x)=>sum+x.netKrw,0);
  const sampleRate=lines.filter(x=>!x.isCloud).reduce((a,x)=>a+x.unitKrw,0);
  const cloudRate=lines.filter(x=>x.isCloud).reduce((a,x)=>a+x.unitKrw,0);
  if(netKrw!==projection.netKrw||sampleRate!==projection.unitPriceNetKrw||
      cloudRate!==projection.cloudUnitNetKrw)
    return {ok:false,code:"PROCESS_PRICE_PARITY_MISMATCH",lines:[],packStatus:"NOT_VERIFIED"};
  return {ok:true,lines,netKrw,packStatus,
    sampleUnitKrw:lines.filter(x=>!x.isCloud).reduce((a,x)=>a+x.unitKrw,0),
    cloudUnitKrw:lines.filter(x=>x.isCloud).reduce((a,x)=>a+x.unitKrw,0)};
}
