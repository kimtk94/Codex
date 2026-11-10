/** Read-only browser contract for a local Salesforce Oppo+Quote workspace. */
const id=(v,p)=>typeof v==="string" &&
  new RegExp("^"+p+"[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$").test(v);

export function previewCandidate(bundle){
  if(!bundle||bundle.status!=="PASS"||bundle.selectionStatus!=="EXACT_ONE"||
     !id(bundle.opportunity?.id,"006")||bundle.linkedQuotes?.length!==1)
    return {ok:false,code:"SOURCE_PARENT_QUOTE_NOT_UNIQUE"};
  const q=bundle.linkedQuotes[0];
  if(!id(q?.id,"a0P")||q.opportunityId!==bundle.opportunity.id)
    return {ok:false,code:"SOURCE_QUOTE_PARENT_MISMATCH"};
  const verified=q.productCount===1&&q.pricingStatus==="VERIFIED_PROCESS_LINES"&&
    q.sourceVatRateVerified10Pct===true&&q.cloudLinePresent===true;
  return {ok:true,opportunity:bundle.opportunity,quote:q,
    pricingReady:verified,
    priceStatus:verified?"SOURCE_PROCESS_VERIFIED":"SOURCE_PROCESS_PRICE_HOLD",
    productCount:Number.isInteger(q.productCount)?q.productCount:null,
    productEvidence:Array.isArray(q.sourceProductEvidence)?q.sourceProductEvidence:[]};
}

export function pairWebRequest(form,mode){
  if(!["CHECK_PRICE","CHECK_FORMS","CHECK_READBACK"].includes(mode))
    return {ok:false,code:"READ_ONLY_MODE_REQUIRED"};
  if(!id(form?.sourceOpportunityId,"006")||!id(form?.sourceQuoteId,"a0P")||
     !Number.isInteger(form.samples)||form.samples<1||form.samples>500||
     !Number.isFinite(form.dataSizeGb)||form.dataSizeGb<=0||form.dataSizeGb>100000||
     typeof form.newOpportunityName!=="string"||form.newOpportunityName!==form.newOpportunityName.trim()||
     form.newOpportunityName.length<5||form.newOpportunityName.length>230)
    return {ok:false,code:"SOURCE_OR_REQUEST_FIELDS_INVALID"};
  const unitPrice=form.productUnitOverrideKrw;
  const cloudPrice=form.cloudUnitOverrideKrw;
  for(const v of [unitPrice,cloudPrice]){
    if(v!==""&&v!=null&&(!Number.isSafeInteger(v)||v<0||v>1_000_000_000))
      return {ok:false,code:"INVALID_PRICE_OVERRIDE"};
  }
  if(mode==="CHECK_READBACK"&&(!id(form.newOpportunityId,"006")||
     form.newOpportunityId===form.sourceOpportunityId))
    return {ok:false,code:"NEW_OPPORTUNITY_ID_INVALID"};
  return {ok:true,body:{
    mode,runMode:"CHECK",
    sourceOpportunityId:form.sourceOpportunityId,
    sourceQuoteId:form.sourceQuoteId,
    newOpportunityName:form.newOpportunityName,
    samples:form.samples,dataSizeGb:form.dataSizeGb,
    productUnitOverrideKrw:unitPrice??"",
    cloudUnitOverrideKrw:cloudPrice??"",
    ...(mode==="CHECK_READBACK"?{newOpportunityId:form.newOpportunityId}:{})
  }};
}

export function priceLines(pricing){
  if(!pricing||typeof pricing!=="object")return [];
  let rows;
  try{rows=JSON.parse(pricing["Product Price Items JSON"]||"");}
  catch{return [];}
  if(!Array.isArray(rows)||rows.length<1||rows.length>12)return [];
  const clean=rows.every(x=>x&&typeof x.product==="string"&&x.product.length>0&&
    Number.isSafeInteger(x.unit_krw)&&x.unit_krw>=0&&
    Number.isSafeInteger(x.qty)&&x.qty>=1&&
    Number.isSafeInteger(x.net_krw)&&x.net_krw===x.qty*x.unit_krw);
  if(!clean||rows.reduce((sum,x)=>sum+x.net_krw,0)!==pricing["Product Net KRW"])return [];
  return rows;
}

export function cloudQuantity(samples,sizeGb){
  return Number.isInteger(samples)&&samples>0&&Number.isFinite(sizeGb)&&sizeGb>0?
    Math.ceil(samples*sizeGb/100):null;
}
