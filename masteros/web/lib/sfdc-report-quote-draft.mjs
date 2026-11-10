/** Read-only Feishu reference Quote -> editable proposed Oppo/Quote.
 * Project identity: process composition + verified data size in Gb.
 * Existing process quantities are NEVER project identity or new sample count.
 * Historical converted USD is NEVER a verified KRW/sample price.
 */
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
function signature(processes,gb){
  return JSON.stringify({
    processes:[...new Set(processes.map(x=>x.processId||x.name))].sort(),
    productionGb:gb===null?"UNVERIFIED":gb
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
      samples:"",sampleUnitKrw:""
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
  const labeled=identified.map(p=>({...p,
    serviceLabel:service||p.processes.find(x=>!/(?:QC|Library|Sequenc|Cloud)/i.test(x.name))?.name||p.processes[0]?.name||""
  }));
  const account={id:s(ref?.accountId),name:s(ref?.accountName)};
  const contact={id:s(ref?.contactId),externalId:s(ref?.contactExternalId),
    name:s(ref?.contactName),email:s(ref?.contactEmail)};
  return {ok:true,draft:{
    qid:detail.qid,sourceQuoteId:s(detail.sfdc_record_id),
    name:"",date:kstDate(now),products:labeled,
    descriptionStatus:"Quote Draft",
    source:"FEISHU_REPORT_USD_CONVERTED_ONLY",
    sourceReceivedKst:s(detail.source_mail_received_kst),
    quoteRecordUnmapped:!s(detail.sfdc_record_id),
    sourceExportUnverified:true,
    referenceIndexStatus:ref?.status||"NOT_PRECLASSIFIED",
    originalOpportunityName:s(ref?.opportunityName),
    originalOpportunityExternalId:s(ref?.opportunityExternalId),
    referenceAccount:account,referenceContact:contact,
    accountMode:"KEEP",account,contact,identitySelectedFromReference:Boolean(ref)
  }};
}
export function calculateDraft(draft){
  const items=(draft?.products||[]).map(p=>{
    const qty=integer(p.samples),rate=integer(p.sampleUnitKrw);
    const qtyOk=Number.isSafeInteger(qty)&&qty>=1&&qty<=10000;
    const priceOk=Number.isSafeInteger(rate)&&rate>=0&&rate<=1000000000;
    const net=qtyOk&&priceOk&&Number.isSafeInteger(qty*rate)?qty*rate:null;
    const gb=s(p.productionGb)===""?null:gbValue(p.productionGb);
    const gbOk=s(p.productionGb)===""||gb!==null;
    return {...p,quantity:qtyOk?qty:null,unitKrw:priceOk?rate:null,
      productionGbValue:gb,netKrw:net,ready:net!==null&&gbOk,
      gbValid:gbOk,projectKey:signature(p.processes,gb)};
  });
  const allPriced=items.length>0&&items.every(x=>x.ready);
  const total=allPriced?items.reduce((n,x)=>n+x.netKrw,0):null;
  if(total!==null&&!Number.isSafeInteger(total))
    return {ok:false,code:"DRAFT_TOTAL_OVERFLOW",items};
  const vat=total===null?null:Math.round(total*.1);
  return {ok:allPriced,
    code:allPriced?"DRAFT_ESTIMATE_ONLY":"INPUT_SAMPLE_PRICE_OR_GB",
    items,netKrw:total,vatKrw:vat,grossKrw:total===null?null:total+vat,
    sourceRateVerified:false,crmSavePermitted:false,feishuWrite:false};
}
// Versioned concise description template: source Progress Description is never copied.
// Content is generated from current draft only; no unstated PO, receipt or status.
export const DESCRIPTION_TEMPLATE_VERSION="OPPO_QUOTE_SHORT_V2";
export function descriptionBasis(draft){
  if(!draft)return "";
  return JSON.stringify({
    template:DESCRIPTION_TEMPLATE_VERSION,
    date:s(draft.date),status:s(draft.descriptionStatus)||"Quote Draft",
    products:(draft.products||[]).map(p=>({
      service:s(p.serviceLabel),
      gb:s(p.productionGb),samples:s(p.samples),unitKrw:s(p.sampleUnitKrw)
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
    const rate=p.unitKrw===null?"단가 확인":money(p.unitKrw)+"KRW";
    return [service,gb,count,"* "+rate].filter(Boolean).join(" ");
  });
  return [mmdd,status,lines.join(" / ")].filter(Boolean).join(" ");
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
    if(p.unitKrw!==null)required.push(money(p.unitKrw)+"KRW");
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
    opportunityName:name,quotationName:name,
    sourceQuoteId:s(draft?.sourceQuoteId),sourceQid:s(draft?.qid),
    source:draft?.source,referenceOnly:true,
    accountContactMode:mode,
    accountContactReferenceMatched:mode==="KEEP"&&
      !errors.includes("REFERENCE_ACCOUNT_CONTACT_UNVERIFIED"),
    accountContactVerified:false,sourceUnitKrwVerified:false,
    crmSavePermitted:false,salesforceWrite:false,feishuWrite:false};
}
