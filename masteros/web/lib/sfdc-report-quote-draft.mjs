/** Feishu Quote Report → operator-editable Oppo/Quote proposal. NO CRM writes.
 * Process Unit Price USD is NOT a KRW/sample price: most report units are Gb,
 * reads, cells, lanes, etc., and process Sample Quantity often differs.
 */
const integer = value => /^\d+$/.test(String(value??"").trim()) ? Number(value) : null;
const money = value => Number(value).toLocaleString("ko-KR");
const s = value => String(value??"").trim();

export function kstDate(now=new Date()){
  return new Intl.DateTimeFormat("en-CA",{
    timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit"
  }).format(now);
}
export function fromFeishuQuote(detail,now=new Date()){
  if(!detail||detail.status!=="PASS"||!/^QID-[0-9-]{8,50}$/.test(s(detail.qid))||
     !Array.isArray(detail.process_lines)||!detail.process_lines.length||
     detail.process_lines.length>120||detail.currency!=="USD_CONVERTED_ONLY"||
     detail.krw_rate_verified!==false)
    return {ok:false,code:"REPORT_SOURCE_NOT_VERIFIED"};
  const groups=new Map();
  for(const row of detail.process_lines){
    const key=s(row?.quotation_product_id),name=s(row?.process_name);
    if(!key||!name||key.length>120)
      return {ok:false,code:"REPORT_PROCESS_LINE_INVALID"};
    if(!groups.has(key))groups.set(key,{id:key,processes:[],totals:new Set(),quantities:new Set()});
    const group=groups.get(key);
    group.processes.push({name,dataUnit:s(row.data_unit),
      sourceUnitUsd:s(row.unit_price_usd),processId:s(row.process_id),
      sourceSampleQuantity:s(row.sample_quantity),sourceDataSize:s(row.data_size)});
    const total=s(row.product_total_usd_converted);
    if(total!==""&&!/^\d+(?:\.\d+)?$/.test(total))
      return {ok:false,code:"REPORT_PRODUCT_TOTAL_INVALID"};
    group.totals.add(total);
    const qty=s(row.sample_quantity);
    if(qty!==""&&(!/^\d+(?:\.\d+)?$/.test(qty)||Number(qty)>1e8))
      return {ok:false,code:"REPORT_SAMPLE_QUANTITY_INVALID"};
    group.quantities.add(qty);
  }
  const products=[...groups.values()].map(group=>{
    const uniformTotal=group.totals.size===1?[...group.totals][0]:"";
    const onlyQty=group.quantities.size===1?[...group.quantities][0]:"";
    const n=integer(onlyQty);
    return {
      id:group.id,processes:group.processes,
      reportProductTotalUsd:uniformTotal,sourceQtyConflicted:group.quantities.size!==1,
      sourceSampleQtyEvidence:group.quantities.size===1?onlyQty:"MIXED_PROCESS_QUANTITIES",
      // Never auto-fill a sample count from source process quantities:
      // they can refer to runs/data, not biological samples.
      samples:"",sampleUnitKrw:"",dataSizeGb:""
    };
  });
  if(products.length>30)return {ok:false,code:"REPORT_PRODUCT_LIMIT"};
  return {ok:true,draft:{
    qid:detail.qid,sourceQuoteId:s(detail.sfdc_record_id),
    name:"",date:kstDate(now),products,
    source:"FEISHU_REPORT_USD_CONVERTED_ONLY",
    sourceReceivedKst:s(detail.source_mail_received_kst),
    sourceExportUnverified:true,quoteRecordUnmapped:!s(detail.sfdc_record_id)
  }};
}
export function calculateDraft(draft){
  const items=(draft?.products||[]).map(p=>{
    const qty=integer(p.samples),rate=integer(p.sampleUnitKrw);
    const qtyOk=Number.isSafeInteger(qty)&&qty>=1&&qty<=500;
    const priceOk=Number.isSafeInteger(rate)&&rate>=0&&rate<=1_000_000_000;
    const net=qtyOk&&priceOk&&Number.isSafeInteger(qty*rate)?qty*rate:null;
    const size=s(p.dataSizeGb);
    const sizeN=size===""?null:Number(size);
    const dataSizeOk=size===""||(Number.isFinite(sizeN)&&sizeN>0&&sizeN<=100000);
    return {...p,quantity:qtyOk?qty:null,unitKrw:priceOk?rate:null,
      netKrw:net,ready:net!==null&&dataSizeOk,
      dataGb:sizeN!==null&&dataSizeOk?qty*sizeN:null};
  });
  const allPriced=items.length>0&&items.every(x=>x.ready);
  const total=allPriced?items.reduce((n,x)=>n+x.netKrw,0):null;
  if(total!==null&&!Number.isSafeInteger(total))return {ok:false,code:"DRAFT_TOTAL_OVERFLOW",items};
  const vat=total===null?null:Math.round(total*0.1);
  const gb=items.every(x=>x.dataGb!==null)?items.reduce((sum,x)=>sum+x.dataGb,0):null;
  return {ok:allPriced,code:allPriced?"DRAFT_ESTIMATE_ONLY":"PRODUCT_QUANTITY_OR_KRW_UNIT_MISSING",
    items,netKrw:total,vatKrw:vat,grossKrw:total===null?null:total+vat,
    possibleCloudQty:gb===null?null:Math.ceil(gb/100),cloudIncluded:false,
    sourceRateVerified:false,crmSavePermitted:false};
}
export function draftDescription(draft,calc=calculateDraft(draft)){
  if(!draft||!/^\d{4}-\d{2}-\d{2}$/.test(s(draft.date)))return "";
  const lines=calc.items.map((p,i)=>{
    const processNames=[...new Set(p.processes.map(r=>r.name))].slice(0,2);
    const title=processNames.join("+")||"Product "+(i+1);
    const quantity=p.quantity===null?"수량 확인":`${p.quantity} samples`;
    const unit=p.unitKrw===null?"단가 확인":`${money(p.unitKrw)} KRW/sample`;
    const amount=p.netKrw===null?"금액 미확정":`${money(p.netKrw)} KRW`;
    return `${i+1}. ${title} | ${quantity} × ${unit} | ${amount} (VAT 별도)`;
  });
  // Reference is a QID, never a source Progress Description copied verbatim.
  return [draft.date,`Reference Quote: ${draft.qid}`,...lines,
    "기존 Report USD 단가는 참고값. KRW·할인·Cloud·고객 및 Contact 확정 전."].join("\n");
}
export function draftPreflight(draft){
  const summary=calculateDraft(draft);
  const name=s(draft?.name);
  const date=s(draft?.date);
  const desc=draft?.description;
  const errors=[];
  if(name.length<5||name.length>230||name!==draft?.name)errors.push("OPPO_QUOTE_NAME_REQUIRED");
  if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||!Number.isFinite(Date.parse(date+"T00:00:00Z")))
    errors.push("QUOTE_DATE_INVALID");
  if(!summary.ok)errors.push(summary.code);
  if(typeof desc!=="string"||desc.length<10||desc.length>3000)errors.push("DESCRIPTION_REQUIRED");
  if(!s(draft.sourceQuoteId))errors.push("SALESFORCE_QUOTE_RECORD_UNMAPPED");
  return {status:errors.length?"HOLD":"PREVIEW_READY",errors,pricing:summary,
    description:typeof desc==="string"?desc:"",
    opportunityName:name,quotationName:name,
    sourceQuoteId:s(draft?.sourceQuoteId),sourceQid:s(draft?.qid),
    source:draft?.source,referenceOnly:true,
    accountContactVerified:false,
    sourceUnitKrwVerified:false,crmSavePermitted:false,
    salesforceWrite:false,feishuWrite:false};
}
