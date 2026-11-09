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
  const account={id:s(ref?.accountId),name:s(ref?.accountName)};
  const contact={id:s(ref?.contactId),name:s(ref?.contactName),
    email:s(ref?.contactEmail)};
  return {ok:true,draft:{
    qid:detail.qid,sourceQuoteId:s(detail.sfdc_record_id),
    name:"",date:kstDate(now),products:identified,
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
export function draftDescription(draft,calc=calculateDraft(draft)){
  if(!draft||!/^\d{4}-\d{2}-\d{2}$/.test(s(draft.date)))return "";
  const lines=calc.items.map((p,i)=>{
    const names=[...new Set(p.processes.map(r=>r.name))].slice(0,2);
    const title=names.join(" + ")||"Product "+(i+1);
    const gb=p.productionGbValue===null?"Gb 확인 필요":p.productionGbValue+" Gb";
    const count=p.quantity===null?"샘플 수 확인":p.quantity+" samples";
    const unit=p.unitKrw===null?"단가 확인":money(p.unitKrw)+" KRW/sample";
    const amount=p.netKrw===null?"금액 미확정":money(p.netKrw)+" KRW (VAT 별도)";
    return (i+1)+". "+title+" | "+gb+" | "+count+" | "+unit+" | "+amount;
  });
  const identityLine=(draft.account?.name&&draft.contact?.name)?
    "Account/Contact: "+s(draft.account.name)+" / "+s(draft.contact.name):"";
  return [s(draft.date),"Reference Quote: "+draft.qid,
    ...(identityLine?[identityLine]:[]),...lines,
    "기존 Quote는 참고값. 신규 고객/Contact·가격·Cloud는 저장 전 별도 확인."].join("\n");
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
