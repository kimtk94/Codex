/** One quoted service: per-sample processes + optional stepwise AliCloud. */
const id=(v,prefix)=>typeof v==="string"&&
 new RegExp("^"+prefix+"[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$").test(v);
const int=(x)=>Number.isSafeInteger(x)&&x>=0;
export function cloudUnits(samples, gbPerSample){
  if(!Number.isInteger(samples)||samples<=0||samples>500||
     !Number.isFinite(gbPerSample)||gbPerSample<=0||gbPerSample>100000)
    throw Error("CLOUD_INPUT_INVALID");
  const totalGb=samples*gbPerSample;
  if(!Number.isFinite(totalGb)||totalGb>1e7)throw Error("CLOUD_TOTAL_INVALID");
  return Math.ceil(totalGb/100);
}
export function derivePairPrice(sourceQuote,samples,dataSizeGb=sourceQuote?.dataSize){
  const q=sourceQuote;
  if(!q||q.productCount!==1||q.pricingStatus!=="VERIFIED_PROCESS_LINES"||
     q.sourceVatRateVerified10Pct!==true||q.cloudLinePresent!==true||!int(q.sampleUnitNetKrw)||
     !int(q.cloudUnitNetKrw)||q.sampleUnitNetKrw+q.cloudUnitNetKrw===0||
     !Number.isInteger(q.samples)||q.samples<=0||
     !int(q.totalPriceKrw)||!Array.isArray(q.processPriceLines)||
     !Number.isInteger(samples)||samples<1||samples>500)
    return {ok:false,code:"SOURCE_PROCESS_PRICE_UNVERIFIED"};
  if(!Number.isFinite(dataSizeGb)||!Number.isFinite(q.dataSize)||
     dataSizeGb!==q.dataSize)
    return {ok:false,code:"DATA_SIZE_CHANGED_REPRICE_REQUIRED"};
  const sourceCloudUnits=cloudUnits(q.samples,q.dataSize);
  const projectedCloudUnits=cloudUnits(samples,dataSizeGb);
  if(q.sourceCloudUnits!==sourceCloudUnits||
     q.totalPriceKrw!==q.sampleUnitNetKrw*q.samples+
                            q.cloudUnitNetKrw*sourceCloudUnits)
    return {ok:false,code:"SOURCE_PROCESS_SUM_MISMATCH"};
  const net=q.sampleUnitNetKrw*samples+q.cloudUnitNetKrw*projectedCloudUnits;
  if(!Number.isSafeInteger(net)||net>1e12||net%10!==0)
    return {ok:false,code:"PRICE_OUT_OF_RANGE"};
  return {ok:true,
    netKrw:net,vatKrw:net/10,grossKrw:net*11/10,
    unitPriceNetKrw:q.sampleUnitNetKrw,
    cloudUnitNetKrw:q.cloudUnitNetKrw,
    cloudUnits:projectedCloudUnits,sourceCloudUnits,
    cloudPriceIncluded:q.cloudUnitNetKrw>0,
    totalDataGb:samples*dataSizeGb,
    sourceSamples:q.samples,sourceNetKrw:q.totalPriceKrw,
    priceBasis:"SOURCE_QUOTE_PROCESS_UNIT_PRICES",
    status:"PROJECTED_REPRICE_MUST_VALIDATE"};
}
export function buildPairDraft(bundle,defaults){
  if(!bundle||bundle.status!=="PASS"||bundle.selectionStatus!=="EXACT_ONE"||
     !bundle.opportunity||bundle.linkedQuotes?.length!==1)
    return {ok:false,code:"EXACTLY_ONE_LINKED_QUOTE_REQUIRED"};
  const opp=bundle.opportunity;
  const quote=bundle.linkedQuotes[0];
  if(quote.opportunityId!==opp.id||!id(opp.id,"006")||
     !id(quote.id,"a0P")||!id(opp.accountId,"001")||
     !id(opp.contactId,"003")||quote.productCount!==1||
     !quote.productName||!quote.productCategory||!quote.processNames||
     !Number.isFinite(quote.dataSize)||quote.dataSize<=0)
    return {ok:false,code:"SOURCE_SINGLE_SERVICE_INCOMPLETE"};
  const price=derivePairPrice(quote,quote.samples,quote.dataSize);
  if(!price.ok)return price;
  const form={...defaults,
    referenceOpportunityId:opp.id,sourceQuoteId:quote.id,
    accountId:opp.accountId,contactId:opp.contactId,
    accountName:opp.accountName,contactName:opp.contactName,
    opportunityName:opp.name,service:opp.service||quote.productName,
    samples:quote.samples,dataSize:quote.dataSize,unit:"Gb",
    amountKrw:price.netKrw,unitPriceNetKrw:price.unitPriceNetKrw,
    cloudUnitNetKrw:price.cloudUnitNetKrw,
    sourceQuoteNetKrw:price.sourceNetKrw,sourceQuoteSamples:price.sourceSamples,
    sourceDataSizeGb:quote.dataSize,
    sourceCloudUnits:price.sourceCloudUnits,cloudUnits:price.cloudUnits,
    productName:quote.productName,productCategory:quote.productCategory,
    processNames:quote.processNames,progressDescription:"",
    referenceAmea:quote.quotationNumber||"",priceConfirmed:false};
  return {ok:true,form,quote,opportunity:opp,pricing:price};
}
export function validatePairPayload(x){
  if(!x||x.action!=="oppo_quote_pair"||!["check","save"].includes(x.mode))
    return {ok:false,code:"ACTION_INVALID"};
  if(x.mode==="save"&&
     (x.confirmSave!==true||x.noDuplicateConfirmed!==true||x.priceConfirmed!==true))
    return {ok:false,code:"EXPLICIT_APPROVAL_REQUIRED"};
  if(!id(x.referenceOpportunityId,"006")||!id(x.sourceQuoteId,"a0P")||
     !id(x.accountId,"001")||!id(x.contactId,"003")||
     typeof x.opportunityName!=="string"||x.opportunityName.trim().length<4||x.opportunityName.length>230||
     typeof x.accountName!=="string"||!x.accountName.trim()||
     typeof x.contactName!=="string"||!x.contactName.trim()||
     typeof x.progressDescription!=="string"||x.progressDescription.trim().length<15||
     typeof x.service!=="string"||!x.service.trim()||
     typeof x.productName!=="string"||!x.productName.trim()||
     typeof x.productCategory!=="string"||!x.productCategory.trim()||
     typeof x.processNames!=="string"||!x.processNames.trim()||
     !Number.isInteger(x.samples)||x.samples<=0||x.samples>500||
     !Number.isFinite(x.dataSize)||x.dataSize<=0||x.dataSize>100000||
     !Number.isInteger(x.unitPriceNetKrw)||x.unitPriceNetKrw<0||
     !Number.isInteger(x.cloudUnitNetKrw)||x.cloudUnitNetKrw<0||
     !Number.isInteger(x.amountKrw)||
     x.amountKrw!==x.unitPriceNetKrw*x.samples+x.cloudUnitNetKrw*x.cloudUnits||
     !Number.isInteger(x.sourceQuoteNetKrw)||!Number.isInteger(x.sourceQuoteSamples)||
     !Number.isFinite(x.sourceDataSizeGb)||x.sourceDataSizeGb!==x.dataSize||
     !Number.isInteger(x.sourceCloudUnits)||!Number.isInteger(x.cloudUnits)||
     x.cloudUnits!==cloudUnits(x.samples,x.dataSize)||
     x.sourceCloudUnits!==cloudUnits(x.sourceQuoteSamples,x.sourceDataSizeGb)||
     !/^\d{4}-\d{2}-\d{2}$/.test(x.closeDate))
    return {ok:false,code:"PAIR_FIELDS_INVALID"};
  return {ok:true};
}
