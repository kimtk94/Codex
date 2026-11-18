/** Read-only Feishu reference Quote -> editable proposed Oppo/Quote.
 * Project identity: process composition + verified data size in Gb.
 * Existing process quantities are NEVER project identity or new sample count.
 * Historical converted USD is NEVER a verified KRW/sample price.
 */
import {inferAmpliconReference,ampliconRegionUnits} from "./sfdc-amplicon-regions.mjs";
import {closeDateOneMonthFromKst} from "./css-close-date.mjs";
import {quoteFeeBreakdown} from "./sfdc-quote-fees.mjs";
const s=v=>String(v??"").trim();
const numeric=v=>/^\d+(?:\.\d+)?$/.test(s(v))?Number(v):null;
const integer=v=>/^\d+$/.test(s(v))?Number(v):null;
const money=n=>Number(n).toLocaleString("ko-KR");
export const isGbUnit=value=>/^(?:g(?:b)?\s*(?:raw\s*data|data|produced|production)?|gigabytes?)$/i.test(s(value));
const gbValue=v=>{
  const n=numeric(v);
  return n!==null&&Number.isFinite(n)&&n>0&&n<=1000000?n:null;
};
export function kstDate(now=new Date()){
  return new Intl.DateTimeFormat("en-CA",{
    timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit"
  }).format(now);
}
function signature(processes,gb,regions=[]){
  return JSON.stringify({
    processes:[...new Set(processes.map(x=>x.processId||x.name))].sort(),
    productionGb:gb===null?"UNVERIFIED":gb,
    regions:[...regions].sort()
  });
}
export function fromFeishuQuote(detail,now=new Date()){
  if(!detail||detail.status!=="PASS"||
     !/^QID-[0-9-]{8,50}$/.test(s(detail.qid))||
     !Array.isArray(detail.process_lines)||!detail.process_lines.length||
     detail.process_lines.length>120||detail.currency!=="USD_CONVERTED_ONLY"||
     detail.krw_rate_verified!==false)
    return {ok:false,code:"REPORT_SOURCE_NOT_VERIFIED"};
  const groups=new Map();
  for(const row of detail.process_lines){
    const key=s(row?.quotation_product_id),name=s(row?.process_name);
    if(!key||!name||key.length>120||name.length>200)
      return {ok:false,code:"REPORT_PROCESS_LINE_INVALID"};
    if(!groups.has(key))groups.set(key,{id:key,processes:[],totals:new Set(),gbs:new Set()});
    const group=groups.get(key),unit=s(row.data_unit);
    group.processes.push({name,processId:s(row.process_id),dataUnit:unit,
      sourceUnitUsd:s(row.unit_price_usd)});
    const total=s(row.product_total_usd_converted);
    if(total!==""&&numeric(total)===null)
      return {ok:false,code:"REPORT_PRODUCT_TOTAL_INVALID"};
    group.totals.add(total);
    if(isGbUnit(unit)){
      // Salesforce report Data Size (Gb) is the reference distinction.
      // Process Sample Quantity can represent Gb, reads, packs or sample count.
      const gb=gbValue(row.data_size);
      if(gb!==null)group.gbs.add(gb);
    }
  }
  if(groups.size>30)return {ok:false,code:"REPORT_PRODUCT_LIMIT"};
  const products=[...groups.values()].map(group=>{
    const gbs=[...group.gbs].sort((a,b)=>a-b);
    const referenceGb=gbs.length===1?gbs[0]:null;
    return {
      id:group.id,processes:group.processes,
      referenceTotalUsd:group.totals.size===1?[...group.totals][0]:"",
      gbCandidates:gbs,referenceProductionGb:referenceGb,
      projectKey:signature(group.processes,referenceGb),
      // New quote inputs always come from operator, not previous process qty.
      productionGb:referenceGb===null?"":String(referenceGb),
      samples:"",sampleUnitKrw:"",cloudUnitKrw:"",priceEvidenceStatus:"NOT_VERIFIED"
    };
  });
  const ref=detail.reference||null;
  const keyed=new Map((ref?.products||[]).map(x=>[x.quoteProductId,x]));
  const identified=products.map(p=>{
    const entry=keyed.get(p.id);
    if(!entry)return {...p,preclassified:false};
    // Shared Feishu class has already been computed at mail ingestion time.
    return {...p,preclassified:true,
      projectKey:s(entry.classKey)||p.projectKey,
      referenceProductionGb:entry.gbStatus==="PASS"?
        Number(entry.productionGb):p.referenceProductionGb,
      productionGb:entry.gbStatus==="PASS"?s(entry.productionGb):p.productionGb,
      gbCandidates:entry.gbStatus==="PASS"?[Number(entry.productionGb)]:p.gbCandidates,
      referenceTotalUsd:s(entry.referenceTotalUsd)||p.referenceTotalUsd};
  });
  const sourceProject=s(ref?.opportunityName);
  // Classify the same physical specimen over multiple Amplicon Regions.
  // "18-16Sv4v5-18-Archaeal16Sv4v5" + "36 K tags" is 18 specimens,
  // 2 region services each, NOT 36 independent specimens.
  const regionReference=inferAmpliconReference(sourceProject,detail.process_lines);
  const serviceNames=[
    ["mRNA-Seq",/\bmRNA\b|mRNA[\s-]*Seq|bulk[\s-]*RNA[\s-]*Seq/i],
    ["WGS",/\bWGS\b|whole.genome/i],
    ["WES",/\bWES\b|whole.exome/i],
    ["small RNA-Seq",/small[\s-]*RNA|miRNA[\s-]*Seq/i],
    ["16S",/\b16S\b/i],
    ["DIA",/\bDIA\b|proteomic/i],
    ["Olink",/\bOlink\b/i],
    ["PMP",/\bPMP\b/i],
    ["PML",/\bPML\b/i],
    ["Iso-Seq",/Iso[\s-]*Seq/i],
    ["ATAC-Seq",/ATAC[\s-]*Seq/i],
    ["Visium",/Visium/i],
    ["Xenium",/Xenium/i]
  ];
  const service=(serviceNames.find(([,re])=>re.test(sourceProject))||[])[0]||"";
  // Service label is a reference-based editable suggestion, not a CRM fact.
  const labeled=identified.map(p=>{
    const useReference=identified.length===1&&regionReference.enabled;
    const amplicon={
      enabled:useReference,
      regions:useReference?regionReference.regions.map(x=>({...x})):[],
      referenceStatus:useReference?regionReference.status:"NOT_SELECTED",
      referenceServiceUnits:useReference?regionReference.referenceServiceUnits:null
    };
    return {...p,
      serviceLabel:useReference?"Amplicon-Seq":service||
        p.processes.find(x=>!/(?:QC|Library|Sequenc|Cloud)/i.test(x.name))?.name||
        p.processes[0]?.name||"",
      amplicon,samples:useReference?regionReference.samples:p.samples,
      projectKey:signature(p.processes,p.referenceProductionGb,
        useReference?amplicon.regions.map(r=>r.code):[])
    };
  });
  const account={id:s(ref?.accountId),name:s(ref?.accountName)};
  const contact={id:s(ref?.contactId),externalId:s(ref?.contactExternalId),
    name:s(ref?.contactName),email:s(ref?.contactEmail)};
  return {ok:true,draft:{
    qid:detail.qid,sourceQuoteId:s(detail.sfdc_record_id),
    // A selected existing Oppo/Quote is a near-clone by default.
    // Users edit only differences, while the new object has NO source ID reuse.
    name:sourceProject,date:kstDate(now),closeDate:closeDateOneMonthFromKst(now),products:labeled,
    descriptionStatus:"Quote Draft",
    feeMode:"EXCLUDE",sourceFeeLines:[],feeEvidenceStatus:"NOT_READ",
    source:"FEISHU_REPORT_USD_CONVERTED_ONLY",
    sourceReceivedKst:s(detail.source_mail_received_kst),
    quoteRecordUnmapped:!s(detail.sfdc_record_id),
    sourceExportUnverified:true,
    referenceIndexStatus:ref?.status||"NOT_PRECLASSIFIED",
    originalOpportunityName:s(ref?.opportunityName),
    originalOpportunityExternalId:s(ref?.opportunityExternalId),
    referenceAccount:account,referenceContact:contact,
    accountMode:"KEEP",account,contact,identitySelectedFromReference:Boolean(ref),
    referenceDefaults:{
      name:sourceProject,account:{...account},contact:{...contact},feeMode:"EXCLUDE",
      products:labeled.map(p=>({
        id:p.id,serviceLabel:p.serviceLabel,productionGb:p.productionGb,
        samples:p.samples,sampleUnitKrw:p.sampleUnitKrw,cloudUnitKrw:p.cloudUnitKrw,
        ampliconEnabled:p.amplicon.enabled,
        regions:p.amplicon.regions.map(r=>({code:r.code,label:r.label,unitKrw:r.unitKrw||""}))
      }))
    }
  }};
}
export function calculateDraft(draft){
  const items=(draft?.products||[]).map(p=>{
    const qty=integer(p.samples),rate=integer(p.sampleUnitKrw);
    const qtyOk=Number.isSafeInteger(qty)&&qty>=1&&qty<=10000;
    const priceOk=Number.isSafeInteger(rate)&&rate>=0&&rate<=1000000000;
    const amp=p.amplicon?.enabled===true;
    const selected=amp?(p.amplicon.regions||[]):[];
    const serviceQty=amp?ampliconRegionUnits(p.samples,selected):qtyOk?qty:null;
    const regionLines=amp?selected.map((r,i)=>{
      const raw=s(r.unitKrw)===""?p.sampleUnitKrw:r.unitKrw;
      const rPrice=integer(raw);
      const good=Number.isSafeInteger(rPrice)&&rPrice>=0&&rPrice<=1000000000;
      const amount=good&&qtyOk&&Number.isSafeInteger(qty*rPrice)?qty*rPrice:null;
      return {code:s(r.code),label:s(r.label),index:i,
        quantity:qtyOk?qty:null,unitKrw:good?rPrice:null,netKrw:amount,
        originalQuoteProductId:p.id,referenceOnly:true};
    }):[];
    const gb=s(p.productionGb)===""?null:gbValue(p.productionGb);
    const gbOk=s(p.productionGb)===""||gb!==null;
    // Business rule: AliCloud is one billed unit per started 100 Gb of
    // total output (biological samples × Gb/sample), regardless of whether
    // the source unit price has finished loading. Never represent a missing
    // Cloud KRW rate as a free (zero-unit) Cloud service.
    const cloudRequested=s(p.cloudUnitKrw)!=="";
    const cloudRate=cloudRequested?integer(p.cloudUnitKrw):null;
    const calculatedCloudUnits=qtyOk&&gb!==null?Math.ceil(qty*gb/100):0;
    // A verified historical Data release 1x fixed Process is NOT an
    // AliCloud service. If the exact source process matrix contains that
    // separate charge but no AliCloud Process, never double-bill it.
    // Unverified quotes without either source indication still HOLD until
    // their Cloud unit rate is checked against live Salesforce.
    const hasCloudProcess=(p.processes||[]).some(x=>
      /ali\\s*cloud|cloud storage|cloud service/i.test(x.name||""));
    const releaseOnlyCloudExcluded=!cloudRequested&&!hasCloudProcess&&
      Array.isArray(p.fixedProcessLines)&&p.fixedProcessLines.some(x=>
        /^data release$/i.test(String(x.processName||"").trim()));
    const cloudQty=releaseOnlyCloudExcluded?0:calculatedCloudUnits;
    const cloudAmount=cloudQty===0?0:
      cloudRate!==null&&Number.isSafeInteger(cloudRate*cloudQty)?
      cloudRate*cloudQty:null;
    const baseNet=amp?(
      serviceQty!==null&&regionLines.every(x=>x.netKrw!==null)?
        regionLines.reduce((n,x)=>n+x.netKrw,0):null
    ):(qtyOk&&priceOk&&Number.isSafeInteger(qty*rate)?qty*rate:null);
    // These are Quote Product processes (e.g. Data release 1 × 30,000),
    // not recurring biological samples and not separate Quotation Fees.
    const fixedInput=Array.isArray(p.fixedProcessLines)?p.fixedProcessLines:[];
    const fixedProcessOk=fixedInput.length<=8&&fixedInput.every(x=>
      x&&typeof x.processId==="string"&&/^Process-[A-Za-z0-9-]{8,70}$/.test(x.processId)&&
      typeof x.processName==="string"&&x.processName.length>0&&x.processName.length<=100&&
      Number.isSafeInteger(x.quantity)&&x.quantity>=1&&x.quantity<=10000&&
      Number.isSafeInteger(x.unitPriceKrw)&&x.unitPriceKrw>=0&&x.unitPriceKrw<=1000000000&&
      Number.isSafeInteger(x.netKrw)&&x.netKrw===x.quantity*x.unitPriceKrw);
    const fixedProcessNetKrw=fixedProcessOk?
      fixedInput.reduce((sum,x)=>sum+x.netKrw,0):null;
    const fixedProcessBasisChanged=fixedInput.length>0&&
      (!Number.isSafeInteger(p.fixedProcessSourceSamples)||
       qty!==p.fixedProcessSourceSamples);
    const net=baseNet!==null&&fixedProcessNetKrw!==null&&
      (cloudQty===0||cloudAmount!==null)?
      baseNet+(cloudAmount||0)+fixedProcessNetKrw:null;
    const safeNet=net!==null&&Number.isSafeInteger(net)?net:null;
    return {...p,quantity:qtyOk?qty:null,unitKrw:priceOk?rate:null,
      productionGbValue:gb,serviceQuantity:serviceQty,
      regionCount:amp?selected.length:0,regionLines,
      cloudUnits:cloudQty,calculatedCloudUnits,cloudSourceExcluded:releaseOnlyCloudExcluded,
      cloudUnitKrw:cloudRate,cloudNetKrw:cloudAmount,
      fixedProcessLines:fixedInput,fixedProcessNetKrw,fixedProcessBasisChanged,
      netKrw:safeNet,ready:safeNet!==null&&gbOk,gbValid:gbOk,
      projectKey:signature(p.processes,gb,selected.map(x=>x.code))};
  });
  const fees=quoteFeeBreakdown(draft);
  const allPriced=items.length>0&&items.every(x=>x.ready)&&fees.ok;
  const processNet=items.length>0&&items.every(x=>x.ready)?
    items.reduce((n,x)=>n+x.netKrw,0):null;
  const total=allPriced?processNet+fees.feeNetKrw:null;
  if(total!==null&&!Number.isSafeInteger(total))
    return {ok:false,code:"DRAFT_TOTAL_OVERFLOW",items};
  const vat=total===null?null:Math.round(total*.1);
  const quoteLineItems=items.flatMap(item=>{
    const base=item.amplicon?.enabled?item.regionLines.map(x=>({
      kind:"AMPLICON_REGION",originalQuoteProductId:item.id,
      regionCode:x.code,regionName:x.label,sampleQuantity:x.quantity,
      unitPriceKrw:x.unitKrw,netKrw:x.netKrw,
      originalProcessIds:item.processes.map(y=>y.processId)
    })):[{
      kind:"PRODUCT",originalQuoteProductId:item.id,
      sampleQuantity:item.quantity,unitPriceKrw:item.unitKrw,
      netKrw:item.quantity!==null&&item.unitKrw!==null?
        item.quantity*item.unitKrw:null,
      originalProcessIds:item.processes.map(y=>y.processId)
    }];
    if(item.cloudUnits>0&&item.cloudUnitKrw!==null)
      base.push({kind:"ALICLOUD",originalQuoteProductId:item.id,
        unitsPer100Gb:1,quantity:item.cloudUnits,unitPriceKrw:item.cloudUnitKrw,
        netKrw:item.cloudNetKrw});
    for(const fixed of item.fixedProcessLines||[])
      base.push({kind:"FIXED_PRODUCT_PROCESS",originalQuoteProductId:item.id,
        processId:fixed.processId,processName:fixed.processName,
        quantity:fixed.quantity,unitPriceKrw:fixed.unitPriceKrw,
        netKrw:fixed.netKrw,
        sourceReferenceOnly:true});
    return base;
  });
  return {ok:allPriced,quoteLineItems:[...quoteLineItems,...fees.quoteFeeItems],
    code:allPriced?"DRAFT_ESTIMATE_ONLY":fees.ok?"INPUT_SAMPLE_PRICE_OR_GB":fees.code,
    items,processNetKrw:processNet,feeNetKrw:fees.feeNetKrw,
    feeIncluded:fees.included,feeSourceStatus:fees.code,
    netKrw:total,vatKrw:vat,grossKrw:total===null?null:total+vat,
    sourceRateVerified:false,crmSavePermitted:false,feishuWrite:false};
}
/** Product-scoped sample unit prices for Opportunity review, without
 * treating multiple products or Amplicon Regions as additional specimens. */
export function opportunityUnitPriceSummary(calculation){
  if(!calculation?.ok||!Array.isArray(calculation.items)||!calculation.items.length)
    return {ok:false,code:"OPPO_PRICE_NOT_VERIFIED",products:[]};
  const products=calculation.items.map((item,i)=>{
    if(!Number.isSafeInteger(item.netKrw)||!Number.isInteger(item.quantity)||
       item.quantity<=0)return null;
    // Stepwise AliCloud cannot always be divided into a per-sample price.
    // Report the biological sample rate separately from billed Cloud blocks.
    const biologicalNet=item.netKrw-(item.cloudNetKrw||0)-
      (item.fixedProcessNetKrw||0);
    if(!Number.isSafeInteger(biologicalNet)||biologicalNet%item.quantity!==0)
      return null;
    return {
      id:item.id||String(i),samples:item.quantity,
      unitPriceNetKrw:biologicalNet/item.quantity,
      netKrw:item.netKrw,cloudNetKrw:item.cloudNetKrw||0,
      fixedProcessNetKrw:item.fixedProcessNetKrw||0,
      effectiveUnitNetKrw:item.netKrw/item.quantity,
      cloudUnits:item.cloudUnits||0,regionCount:item.regionCount||0,
      perRegion:item.amplicon?.enabled===true,
      serviceQuantity:item.serviceQuantity
    };
  });
  if(products.some(x=>x===null))
    return {ok:false,code:"OPPO_UNIT_RATE_NOT_VERIFIED",products:[]};
  return {ok:true,products,singleProduct:products.length===1,
    overallPerSampleNetKrw:products.length===1?products[0].unitPriceNetKrw:null,
    totalNetKrw:calculation.netKrw};
}

// Versioned concise description template: source Progress Description is never copied.
// Content is generated from current draft only; no unstated PO, receipt or status.
export const DESCRIPTION_TEMPLATE_VERSION="OPPO_QUOTE_SHORT_V2";
export function descriptionBasis(draft){
  if(!draft)return "";
  return JSON.stringify({
    template:DESCRIPTION_TEMPLATE_VERSION,
    date:s(draft.date),status:s(draft.descriptionStatus)||"Quote Draft",
    feeMode:draft.feeMode||"EXCLUDE",
    feeLines:draft.feeMode==="KEEP"?(draft.sourceFeeLines||[]).map(f=>({
      feeType:f.feeType,feeKrw:f.feeKrw,productName:f.productName,
      sourceQuoteProductId:f.sourceQuoteProductId})):[],
    products:(draft.products||[]).map(p=>({
      service:s(p.serviceLabel),
      gb:s(p.productionGb),samples:s(p.samples),unitKrw:s(p.sampleUnitKrw),
      cloudUnitKrw:s(p.cloudUnitKrw),
      fixedProcessLines:(p.fixedProcessLines||[]).map(x=>({
        processId:x.processId,quantity:x.quantity,
        unitPriceKrw:x.unitPriceKrw,netKrw:x.netKrw})),
      fixedProcessSourceSamples:p.fixedProcessSourceSamples??null,
      regionMode:Boolean(p.amplicon?.enabled),
      regions:(p.amplicon?.regions||[]).map(r=>({
        code:s(r.code),label:s(r.label),unitKrw:s(r.unitKrw)
      }))
    }))
  });
}
// The actual Salesforce Progress Description convention is concise, e.g.
// "0407 Quote Issued mRNA-Seq 12 samples * 250,000KRW".
// "Quote Issued" must only appear after actual issuance evidence; new
// reference-based drafts ALWAYS start at Quote Draft.
export function draftDescription(draft,calc=calculateDraft(draft)){
  if(!draft||!/^\d{4}-\d{2}-\d{2}$/.test(s(draft.date)))return "";
  const mmdd=s(draft.date).slice(5,7)+s(draft.date).slice(8,10);
  const status=s(draft.descriptionStatus)||"Quote Draft";
  if(!["Quote Draft","Prospective","Quote Issued"].includes(status))return "";
  const lines=calc.items.map((p,i)=>{
    const source=draft.products[i];
    const service=s(source.serviceLabel)||"Service 확인";
    const gb=p.productionGbValue===null?"":p.productionGbValue+"Gb";
    const count=p.quantity===null?"수량 확인":p.quantity+" samples";
    if(p.amplicon?.enabled){
      const regions=p.regionLines.map(x=>x.label).join(" + ")||"Region 확인";
      const rates=p.regionLines.map(x=>x.unitKrw);
      const sameRate=rates.length>0&&rates.every(x=>x!==null&&x===rates[0]);
      const rate=sameRate?money(rates[0])+"KRW/region":
        p.regionLines.map(x=>x.label+" "+(x.unitKrw===null?"단가 확인":money(x.unitKrw)+"KRW")).join(" + ");
      return [service,"("+regions+")",gb,count,"* "+p.regionCount+" regions","* "+rate]
        .filter(Boolean).join(" ");
    }
    const rate=p.unitKrw===null?"단가 확인":money(p.unitKrw)+"KRW";
    return [service,gb,count,"* "+rate].filter(Boolean).join(" ");
  });
  const fees=quoteFeeBreakdown(draft);
  const feeSummary=fees.included&&fees.ok?
    fees.quoteFeeItems.map(f=>f.feeType+" "+money(f.netKrw)+"KRW").join(" + "):"";
  const fixedSummary=calc.items.flatMap(p=>
    (p.fixedProcessLines||[]).map(x=>x.processName+
      " "+x.quantity+" × "+money(x.unitPriceKrw)+"KRW")).join(" + ");
  // Preserve the established one-line Salesforce Description convention.
  const base=[mmdd,status,lines.join(" / ")].filter(Boolean).join(" ");
  return [base,fixedSummary,feeSummary].filter(Boolean).join(" / ");
}
export function descriptionReview(draft,text,manualBasis=null){
  const basis=descriptionBasis(draft);
  const stale=manualBasis!==null&&manualBasis!==basis;
  const calc=calculateDraft(draft);
  const date=s(draft?.date);
  if(!/^\d{4}-\d{2}-\d{2}$/.test(date))
    return {stale,complete:false,missing:["DATE"]};
  const required=[date.slice(5,7)+date.slice(8,10),
    s(draft.descriptionStatus)||"Quote Draft"];
  for(const [i,p] of calc.items.entries()){
    const label=s(draft.products[i].serviceLabel);
    if(label)required.push(label);
    if(p.productionGbValue!==null)required.push(String(p.productionGbValue)+"Gb");
    if(p.quantity!==null)required.push(String(p.quantity)+" samples");
    if(p.amplicon?.enabled){
      required.push(p.regionCount+" regions");
      for(const r of p.regionLines){
        required.push(r.label);
        if(r.unitKrw!==null)required.push(money(r.unitKrw)+"KRW");
      }
    }else if(p.unitKrw!==null)required.push(money(p.unitKrw)+"KRW");
    for(const fixed of p.fixedProcessLines||[]){
      required.push(fixed.processName);
      required.push(fixed.quantity+" × "+money(fixed.unitPriceKrw)+"KRW");
    }
  }
  if(draft?.feeMode==="KEEP"){
    const fees=quoteFeeBreakdown(draft);
    if(fees.ok)for(const fee of fees.quoteFeeItems){
      required.push(fee.feeType);
      required.push(money(fee.netKrw)+"KRW");
    }
  }
  const missing=required.filter(fragment=>!s(text).includes(fragment));
  return {stale,complete:missing.length===0,missing};
}
export function draftPreflight(draft){
  const calc=calculateDraft(draft);
  const name=s(draft?.name),date=s(draft?.date),description=draft?.description;
  const errors=[];
  if(name.length<5||name.length>230||name!==draft?.name)
    errors.push("OPPO_QUOTE_NAME_REQUIRED");
  if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||!Number.isFinite(Date.parse(date+"T00:00:00Z")))
    errors.push("QUOTE_DATE_INVALID");
  if(!calc.ok)errors.push(calc.code);
  if(calc.items?.some(item=>item.fixedProcessBasisChanged))
    errors.push("HISTORICAL_FIXED_PROCESS_REVALIDATION_REQUIRED");
  if(draft?.feeMode==="KEEP")
    errors.push("QUOTE_FEE_SOURCE_REVALIDATION_REQUIRED");
  else if(draft?.feeMode&&draft.feeMode!=="EXCLUDE")
    errors.push("QUOTE_FEE_MODE_INVALID");
  if(typeof description!=="string"||description.length<10||description.length>3000)
    errors.push("DESCRIPTION_REQUIRED");
  if(s(draft?.descriptionStatus)==="Quote Issued"&&!draft?.quoteIssuedEvidenceVerified)
    errors.push("QUOTE_ISSUED_EVIDENCE_REQUIRED");
  if(typeof description==="string"){
    const review=descriptionReview(draft,description,draft?.descriptionManualBasis??null);
    if(review.stale)errors.push("DESCRIPTION_LOCKED_STALE");
    if(!review.complete)errors.push("DESCRIPTION_CURRENT_FACTS_MISSING");
  }
  if(!s(draft?.sourceQuoteId))errors.push("REFERENCE_RECORD_ID_UNMAPPED");
  const mode=draft?.accountMode;
  if(!["KEEP","CHANGE"].includes(mode))errors.push("ACCOUNT_CONTACT_MODE_REQUIRED");
  if(mode==="KEEP"&&(
    !/^001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/.test(s(draft?.account?.id))||
    !/^003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/.test(s(draft?.contact?.id))||
    !s(draft?.account?.name)||!s(draft?.contact?.name)
  ))errors.push("REFERENCE_ACCOUNT_CONTACT_UNVERIFIED");
  if(mode==="CHANGE"){
    if(!s(draft?.account?.name)||!s(draft?.contact?.name))
      errors.push("NEW_ACCOUNT_CONTACT_REQUIRED");
    // Changing Account/Contact needs an independent Salesforce identity
    // confirmation before any create operation; local report != current CRM.
    errors.push("ACCOUNT_CONTACT_REVALIDATION_REQUIRED");
  }
  return {status:errors.length?"HOLD":"PREVIEW_READY",errors,pricing:calc,
    description:typeof description==="string"?description:"",
    quoteLineItems:calc.quoteLineItems,
    reusedSourceReference:true,
    modifiedFields:draftChanges(draft),
    opportunityName:name,quotationName:name,
    sourceQuoteId:s(draft?.sourceQuoteId),sourceQid:s(draft?.qid),
    source:draft?.source,referenceOnly:true,
    accountContactMode:mode,
    accountContactReferenceMatched:mode==="KEEP"&&
      !errors.includes("REFERENCE_ACCOUNT_CONTACT_UNVERIFIED"),
    accountContactVerified:false,sourceUnitKrwVerified:false,
    crmSavePermitted:false,salesforceWrite:false,feishuWrite:false};
}


/** Compact source-vs-new draft delta. Source IDs are references, not new IDs.
 * Editable defaults are copied once; on-screen changes only report edited fields.
 */
export function draftChanges(draft){
  const ref=draft?.referenceDefaults;
  if(!ref)return [];
  const changes=[];
  const changed=(field,oldValue,newValue)=>{
    if(JSON.stringify(oldValue)!==JSON.stringify(newValue))
      changes.push({field,before:oldValue,after:newValue});
  };
  changed("opportunityQuoteName",ref.name,draft.name);
  changed("account",ref.account,draft.account);
  changed("contact",ref.contact,draft.contact);
  changed("quoteFeeMode",ref.feeMode||"EXCLUDE",draft.feeMode||"EXCLUDE");
  (draft.products||[]).forEach((p,i)=>{
    const prev=ref.products?.[i];
    if(!prev){changes.push({field:"product["+i+"]",before:null,after:p.id});return;}
    const lead="product["+i+"].";
    for(const key of ["serviceLabel","productionGb","samples","sampleUnitKrw","cloudUnitKrw","fixedProcessLines"])
      changed(lead+key,prev[key],p[key]);
    changed(lead+"regionMode",prev.ampliconEnabled,Boolean(p.amplicon?.enabled));
    changed(lead+"regions",prev.regions,
      (p.amplicon?.regions||[]).map(r=>({
        code:r.code,label:r.label,unitKrw:r.unitKrw||""
      })));
  });
  return changes;
}
