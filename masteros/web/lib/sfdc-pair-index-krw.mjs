/** Exact-QID 2026 KRW source-process comparison, never CRM price approval.
 * Cannot infer final Cloud fees or contract discounts from the report.
 */
import {parseKrwEvidence} from "./sfdc-2026-krw-price-preview.mjs";
export function historicalKrwReference(evidence,sourceQid,product) {
  let parsed;
  try{parsed=parseKrwEvidence(JSON.stringify(evidence))}
  catch{return {ok:false,code:"HISTORICAL_KRW_INDEX_UNAVAILABLE"}}
  const required=(product?.processes||[]).map(x=>x.processId).filter(Boolean);
  if(typeof sourceQid!=="string"||!/^QID-[0-9-]{8,50}$/.test(sourceQid)||
      !required.length||new Set(required).size!==required.length)
    return {ok:false,code:"HISTORICAL_PRODUCT_NOT_IDENTIFIED"};
  const gb=product.productionGb===""||product.productionGb==null?
    null:Number(product.productionGb);
  if(gb!==null&&(!Number.isFinite(gb)||gb<=0))
    return {ok:false,code:"HISTORICAL_GB_INVALID"};
  const groups=new Map();
  for(const row of parsed.records) {
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
