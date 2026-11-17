/** Exact-QID 2026 KRW source-process comparison, never CRM price approval.
 * Cannot infer final Cloud fees or contract discounts from the report.
 */
import {parseKrwEvidence} from "./sfdc-2026-krw-price-preview.mjs";
export function historicalKrwReference(evidence,sourceQid,product) {
  let parsed;
  try{parsed=parseKrwEvidence(JSON.stringify(evidence))}
  catch{return {ok:false,code:"HISTORICAL_KRW_INDEX_UNAVAILABLE"}}
  return historicalReferenceFromValidatedRows(parsed.records,sourceQid,product);
}
function historicalReferenceFromValidatedRows(records,sourceQid,product) {
  const required=(product?.processes||[]).map(x=>x.processId).filter(Boolean);
  if(typeof sourceQid!=="string"||!/^QID-[0-9-]{8,50}$/.test(sourceQid)||
      !required.length||new Set(required).size!==required.length)
    return {ok:false,code:"HISTORICAL_PRODUCT_NOT_IDENTIFIED"};
  const gb=product.productionGb===""||product.productionGb==null?
    null:Number(product.productionGb);
  if(gb!==null&&(!Number.isFinite(gb)||gb<=0))
    return {ok:false,code:"HISTORICAL_GB_INVALID"};
  const groups=new Map();
  for(const row of records) {
    if(row.quote_id!==sourceQid||!required.includes(row.process_id))continue;
    const key=row.product_signature;
    if(!groups.has(key))groups.set(key,[]);
    groups.get(key).push(row);
  }
  const matches=[...groups.values()].filter(rows=>
    rows.length===required.length &&
    required.every(id=>rows.filter(r=>r.process_id===id).length===1) &&
    (gb===null||rows.some(r=>r.data_unit==="Gb"&&Number(r.data_size)===gb)));
  if(matches.length!==1)return {ok:false,code:"HISTORICAL_EXACT_PROCESS_MATCH_UNAVAILABLE"};
  const rows=matches[0];
  const isCloud=r=>/ali\s*cloud|cloud storage|cloud service/i.test(r.process_name);
  const isRelease=r=>/^data release$/i.test(r.process_name.trim());
  const cloudRows=rows.filter(isCloud);
  const sampleRows=rows.filter(r=>!isCloud(r)&&!isRelease(r));
  // Salesforce Process.Sample_Quantity is the number of *process operations*,
  // not necessarily biological sample count. Paid Data release may have two
  // operations per biological sample. Summing process Unit Prices is wrong.
  if(!sampleRows.length||cloudRows.length>1||
     !sampleRows.every(r=>Number.isInteger(r.sample_quantity)&&r.sample_quantity>0))
    return {ok:false,code:"HISTORICAL_SAMPLE_BASIS_UNVERIFIED"};
  const quantities=new Set(sampleRows.map(r=>r.sample_quantity));
  if(quantities.size!==1)
    return {ok:false,code:"HISTORICAL_MIXED_PROCESS_QUANTITIES"};
  const sourceSamples=sampleRows[0].sample_quantity;
  const gbRows=sampleRows.filter(r=>r.data_unit==="Gb");
  if(gb!==null&&(!gbRows.length||gbRows.some(r=>Number(r.data_size)!==gb)))
    return {ok:false,code:"HISTORICAL_EXACT_SOURCE_GB_NOT_FOUND"};
  const productNetKrw=rows.filter(r=>!isCloud(r)).reduce((sum,r)=>
    sum+Number(r.unit_price_krw)*r.sample_quantity,0);
  // This is historical VAT-excluded Product net / observed biological samples,
  // not a new Quote approval and not a per-process price rewrite.
  const sampleUnitKrw=productNetKrw/sourceSamples;
  const cloudUnitKrw=cloudRows.length?Number(cloudRows[0].unit_price_krw):null;
  // A divided historical per-sample price can be fractional even if every
  // original Salesforce Process Unit Price is a whole KRW amount.
  // This editor accepts integer KRW; do not round or silently shift the net.
  if(Number.isFinite(sampleUnitKrw)&&!Number.isInteger(sampleUnitKrw))
    return {ok:false,code:"HISTORICAL_FRACTIONAL_SAMPLE_RATE_HOLD"};
  if(!Number.isSafeInteger(productNetKrw)||productNetKrw<0||
     !Number.isSafeInteger(sampleUnitKrw)||sampleUnitKrw<0||
     (cloudUnitKrw!==null&&(!Number.isSafeInteger(cloudUnitKrw)||cloudUnitKrw<0))||
     !rows.every(x=>Number.isSafeInteger(Number(x.unit_price_krw))))
    return {ok:false,code:"HISTORICAL_PRICE_AGGREGATION_UNVERIFIED"};
  return {ok:true,code:"HISTORICAL_2026_KRW_COMPARISON_ONLY",
    sourceQid,sourceProcessCount:rows.length,sourceSamples,
    sourceProductNetKrw:productNetKrw,
    sourceGbStatus:gb===null?"UNVERIFIED":"EXACT_SOURCE_GB_MATCH",
    candidateSampleUnitKrw:sampleUnitKrw,candidateCloudUnitKrw:cloudUnitKrw,
    currency:"KRW",vatBasis:"VAT_EXCLUDED",year:2026,
    pricesApprovedForNewQuote:false,sourceRecheckRequired:true};
}

/** Source Quotation Product Process breakdown: display ONLY.
 * Never derive a new Quote price for a HOLD Product. Original unit prices,
 * native per-Process quantities and exact Process subtotal stay distinct.
 * The source index contains no Quote Fee; do not invent a shipping charge.
 * All amounts use exact 1/10,000 KRW BigInt arithmetic without rounding.
 */
const HISTORICAL_SOURCE="SFDC_AUTHENTICATED_READ_ONLY_KRW_PROCESS_LINES";
const rawScaledKrw=(amount,qty)=>{
 const value=String(amount);
 if(!/^\d{1,9}(?:\.\d{1,4})?$/.test(value)||
    !Number.isInteger(qty)||qty<=0||qty>1000000)return null;
 const [int,dec=""]=value.split(".");
 return (BigInt(int)*10000n+BigInt(dec.padEnd(4,"0")||"0"))*BigInt(qty);
};
const formatScaledKrw=value=>{
 const whole=value/10000n;
 const frac=(value%10000n).toString().padStart(4,"0").replace(/0+$/,"");
 return whole.toString()+(frac?"."+frac:"");
};
export function listKrwOriginalProcessGroups(evidence){
 const hold=(code)=>({status:code,groups:[],total:0,heldCount:0,
   comparableCount:0,price_auto_apply:false,crm_writes:0});
 if(evidence?.source!==HISTORICAL_SOURCE||
    evidence?.status!=="LOCAL_FILE_SCHEMA_OK_AUTH_RECHECK_REQUIRED"||
    evidence?.prices_approved_for_new_quote!==false||
    !Array.isArray(evidence.records)||!evidence.records.length||
    evidence.records.length>5000)
   return hold("HOLD_VALIDATED_SOURCE_REQUIRED");
 const products=new Map(),quoteRows=new Map();
 for(const r of evidence.records){
   if(!r||typeof r.quote_id!=="string"||
      typeof r.product_signature!=="string"||
      typeof r.process_id!=="string")return hold("HOLD_PROCESS_SCHEMA");
   const key=r.quote_id+"|"+r.product_signature;
   if(!products.has(key))products.set(key,[]);
   products.get(key).push(r);
   if(!quoteRows.has(r.quote_id))quoteRows.set(r.quote_id,[]);
   quoteRows.get(r.quote_id).push(r);
 }
 const groups=[];
 for(const [key,rows] of products){
   const first=rows[0];
   const consistent=rows.every(r=>r.quote_id===first.quote_id&&
     r.product_signature===first.product_signature&&
     r.account_id===first.account_id&&r.contact_id===first.contact_id&&
     r.product_name===first.product_name);
   let sum=0n,valid=true;
   const lines=rows.map(r=>{
     const x=rawScaledKrw(r.unit_price_krw,r.sample_quantity);
     if(x===null){valid=false;return null}
     sum+=x;
     return {process_id:r.process_id,process_name:r.process_name,
       process_quantity:r.sample_quantity,unit_price_krw:r.unit_price_krw,
       process_net_krw:formatScaledKrw(x),
       data_size:r.data_size,data_unit:r.data_unit,
       cloud:/ali\s*cloud|cloud storage|cloud service/i.test(r.process_name),
       data_release:/^data release$/i.test(r.process_name.trim())};
   });
   if(!valid)return hold("HOLD_PROCESS_ARITHMETIC");
   const sampleRows=rows.filter(r=>!/^data release$/i.test(r.process_name.trim())&&
     !/ali\s*cloud|cloud storage|cloud service/i.test(r.process_name));
   const gbSizes=[...new Set(sampleRows.filter(r=>r.data_unit==="Gb").map(r=>r.data_size))];
   const productionGb=gbSizes.length===1?gbSizes[0]:"";
   const candidate=consistent?
     historicalReferenceFromValidatedRows(quoteRows.get(first.quote_id),
       first.quote_id,{productionGb,
         processes:rows.map(r=>({processId:r.process_id}))}):
     {ok:false,code:"HOLD_PRODUCT_IDENTITY_MISMATCH"};
   groups.push({key,quote_id:first.quote_id,created_date:first.created_date,
     product_signature:first.product_signature,product_name:first.product_name||"Product",
     account_id:first.account_id,contact_id:first.contact_id,
     line_count:rows.length,lines,process_net_krw:formatScaledKrw(sum),
     review_status:candidate.ok?"COMPARISON_ONLY":"HOLD",
     hold_reason:candidate.ok?null:candidate.code,
     historical_sample_rate_krw:candidate.ok?
       String(candidate.candidateSampleUnitKrw):null,
     sample_rate_auto_applicable:false,source_recheck_required:true,
     fee_included:false,crm_writes:0});
 }
 groups.sort((a,b)=>b.created_date.localeCompare(a.created_date)||
    a.quote_id.localeCompare(b.quote_id)||
    a.product_signature.localeCompare(b.product_signature));
 const heldCount=groups.filter(g=>g.review_status==="HOLD").length;
 return {status:"LOCAL_ORIGINAL_PROCESS_DISPLAY_ONLY",groups,total:groups.length,
   heldCount,comparableCount:groups.length-heldCount,
   price_auto_apply:false,crm_writes:0};
}

/** Prefill the exact selected historical Quote as a comparison, never approved.
 * A live verified source overrides this later; manual operator edits never do.
 */
export function prefillHistoricalKrw(draft,evidence) {
  if(!draft||!Array.isArray(draft.products)||!evidence)return draft;
  let any=false;
  const products=draft.products.map(product=>{
    if(product.sampleUnitKrw!==""&&product.sampleUnitKrw!==undefined)return product;
    const proposal=historicalKrwReference(evidence,draft.qid,product);
    if(!proposal.ok)return product;
    any=true;
    return {...product,sampleUnitKrw:String(proposal.candidateSampleUnitKrw),
      cloudUnitKrw:proposal.candidateCloudUnitKrw===null?"":String(proposal.candidateCloudUnitKrw),
      priceEvidenceStatus:"INDEX_2026_KRW_COMPARISON_ONLY",
      priceSourceQid:proposal.sourceQid};
  });
  return any?{...draft,products,sourceKrwRateStatus:"HISTORICAL_COMPARISON_RECHECK_REQUIRED"}:draft;
}
