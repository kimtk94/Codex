/** Operator-PC Salesforce Opportunity + Quotation save review.
 * This is a SOURCE-IMMUTABLE, DISPLAY-ONLY view of local approval queue files.
 * A queued draft is NEVER a native SFDC-approved write, even if its old
 * Quote's rate had been verified. No server save/approval endpoint is exposed.
 */
import {createHash} from "node:crypto";

const ID=/^OPPOQUOTE-[a-f0-9]{24}$/;
const CRM_ID=(x,prefix)=>typeof x==="string"&&
  new RegExp("^"+prefix+"[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$").test(x);
const MONEY=/^(0|[1-9]\d{0,11})$/;
const QTY=/^[1-9]\d{0,5}$/;
const KRW=(x)=>typeof x==="string"&&MONEY.test(x)?BigInt(x):null;
const wholeKrw=x=>typeof x==="number"&&Number.isSafeInteger(x)&&x>=0?
  BigInt(x):KRW(x);
const fixedQty=x=>typeof x==="number"&&Number.isSafeInteger(x)&&x>=1&&x<=100000?
  BigInt(x):qty(x);
const qty=x=>typeof x==="string"&&QTY.test(x)&&Number(x)<=100000?BigInt(x):null;
const no=(code)=>({status:"HOLD_QUEUE_RECORD",code,savePermitted:false,
  salesforceWrite:false,crmWrites:0});

export function reviewQueueRecord(entry,expectedId){
 if(!ID.test(expectedId||"")||!entry||typeof entry!=="object"||
    entry.requestId!==expectedId||!entry.canonical||typeof entry.canonical!=="object"||
    entry.salesforceWrite!==false||entry.savePermitted!==false||
    entry.approved!==false||entry.requestedWrite!==false||
    entry.state!=="AWAITING_OPERATOR_APPROVAL"||
    !["PENDING_APPROVAL","NEEDS_REVIEW"].includes(entry.status))
  return no("QUEUE_PROVENANCE_INVALID");
 const expected="OPPOQUOTE-"+createHash("sha256")
   .update(JSON.stringify(entry.canonical)).digest("hex").slice(0,24);
 if(expected!==expectedId)return no("QUEUE_IMMUTABLE_DIGEST_MISMATCH");
 const c=entry.canonical,ref=c.reference,proposed=c.proposed,previous=c.review;
 if(!ref||!proposed||!previous||!Array.isArray(proposed.products)||
    proposed.products.length<1||proposed.products.length>12||
    typeof proposed.name!=="string"||proposed.name.length>230||
    !["KEEP","CHANGE"].includes(proposed.accountMode))
  return no("QUEUE_CANONICAL_INVALID");
 const account=proposed.account||{},contact=proposed.contact||{};
 const checks=[
   {id:"live_account_contact",label:"현재 SFDC Account·Main Contact 관계",passed:false,
    evidence:CRM_ID(account.id,"001")&&CRM_ID(contact.id,"003")?
      "과거 참조 ID 있음 · 실시간 관계 검증 필요":"001·003 원본 ID 미확정"},
   {id:"duplicate",label:"신규 Opportunity·Quotation 동일 이름 중복",passed:false,
    evidence:"현재 Salesforce 양쪽 목록에서 중복 0건 재조회 필요"},
   {id:"native_quote_type",label:"Quotation Record Type = Research-AMEA",passed:false,
    evidence:"실제 연구견적 유형 재선택 필요 · AMEA Agreement와 구분"},
   {id:"product_process",label:"Product·Process 원본 ID 및 공정 수량·Pack",passed:false,
    evidence:"현재 SFDC master / Pack / Data release 원본 대조 필요"},
   {id:"new_client_price",label:"신규 고객에 적용할 KRW 공정별 가격",passed:false,
    evidence:"과거 Quote 단가와 신규 계약 단가 승인은 별개"},
   {id:"cloud_fee",label:"AliCloud 100Gb당 1개 및 배송·반송 Fee",passed:false,
    evidence:"Cloud 필요 여부, 실제 총 Gb 및 별도 Fee 결정 필요"},
   {id:"amount",label:"Oppo Amount = Quote 공급가액(부가세 제외)",passed:false,
    evidence:"Product×Process 원본과 VAT 10% 검증 후 확정"},
   {id:"stage",label:"Stage·Forecast·Service Line·Opportunity Record Type",passed:false,
    evidence:"현재 SFDC 필수 선택값 재확인 필요"},
   {id:"description",label:"신규 진행 상태에 맞는 Progress Description",passed:false,
    evidence:"원본 문구 복제 금지 · 미확인 샘플 접수·PO 주장 금지"},
   {id:"approval",label:"이 정확한 단일 건에 대한 최종 Save 승인",passed:false,
    evidence:"저장 전 사용자 검토·승인 필수"}
 ];
 const previews=[];
 let provisionalNet=0n,subtotalsReliable=true;
 let fixedProcessNet=0n,fixedProcessReliable=true,cloudRatePresent=false;
 for(const p of proposed.products){
   if(!p||typeof p!=="object"||typeof p.id!=="string"||
      !Array.isArray(p.processIds)||!Array.isArray(p.processNames))
    return no("QUEUE_PRODUCT_SCHEMA_INVALID");
   const count=qty(p.samples),unit=KRW(p.sampleUnitKrw);
   const line=count!==null&&unit!==null?count*unit:null;
   if(line!==null)provisionalNet+=line;
   else subtotalsReliable=false;
   if(p.cloudUnitKrw!==""&&p.cloudUnitKrw!==undefined&&p.cloudUnitKrw!==null)
     cloudRatePresent=true;
   const fixed=Array.isArray(p.fixedProcessLines)?p.fixedProcessLines:[];
   if(fixed.length>15)fixedProcessReliable=false;
   const fixedProcessLines=fixed.slice(0,15).map(item=>{
     const units=fixedQty(item?.quantity),rate=wholeKrw(item?.unitPriceKrw),
       reported=wholeKrw(item?.netKrw);
     const referenced=typeof item?.processId==="string"&&
       p.processIds.includes(item.processId);
     const valid=referenced&&units!==null&&rate!==null&&
       reported!==null&&units*rate===reported;
     if(valid)fixedProcessNet+=reported;
     else fixedProcessReliable=false;
     return {process_id:String(item?.processId??""),
       process_name:String(item?.processName??""),
       quantity:item?.quantity??null,unit_price_krw:item?.unitPriceKrw??null,
       net_krw:valid?reported.toString():null,
       reference_verified:valid};
   });
   previews.push({
     reference_product_id:p.id,service:p.serviceLabel||"원본 확인 필요",
     samples:p.samples,productionGb:p.productionGb,
     historical_sample_unit_krw:p.sampleUnitKrw,
     historical_cloud_unit_krw:p.cloudUnitKrw,
     historical_sample_subtotal_krw:line===null?null:line.toString(),
     fixed_process_lines:fixedProcessLines,
     fixed_process_subtotal_krw:fixedProcessLines.every(x=>x.reference_verified)?
       fixedProcessLines.reduce((n,x)=>n+BigInt(x.net_krw),0n).toString():null,
     original_process_names:p.processNames.slice(0,100),
     original_process_ids:p.processIds.slice(0,100),
     process_count:p.processIds.length,
     price_evidence_status:p.priceEvidenceStatus||"UNVERIFIED",
     needs_current_native_process_price:true
   });
 }
 const feeLines=Array.isArray(proposed.quoteFeeLines)?proposed.quoteFeeLines:[];
 const fees=feeLines.slice(0,15).map(x=>({
   fee_type:x.feeType||"SOURCE_FEE",
   source_product_name:x.sourceProductName||"",
   reference_fee_net_krw:x.netKrw??null,
   included_in_new_quote:false
 }));
 // Include explicit fixed Process lines in the *comparison* total; the
 // operator-entered per-sample rate is NOT the whole Quote. Do not invent
 // Cloud/Pack/Fee charges and never convert a comparison into approval.
 const comparisonReady=subtotalsReliable&&fixedProcessReliable;
 const comparisonNet=comparisonReady?provisionalNet+fixedProcessNet:null;
 const comparisonVat=comparisonNet!==null&&comparisonNet%10n===0n?
   (comparisonNet/10n).toString():null;
 const comparisonGross=comparisonNet!==null&&comparisonVat!==null?
   (comparisonNet+BigInt(comparisonVat)).toString():null;
 return {
   status:"QUEUE_REVIEW_READY_SFDC_NATIVE_RECHECK_REQUIRED",
   requestId:expectedId,createdAtUtc:entry.receivedAtUtc||null,
   queueStatus:entry.status,savePermitted:false,salesforceWrite:false,
   crmWrites:0,actualOpportunityCreated:false,actualQuotationCreated:false,
   name:proposed.name,requestedDateKst:proposed.date||"",
   closeDateKst:proposed.closeDate||"",
   description:proposed.description||"",
   sourceQid:ref.qid||"",
   sourceOpportunityId:ref.opportunityId||"",
   sourceQuoteId:ref.sourceQuoteId||"",
   account:{name:account.name||"",nativeIdVerified:false,
     sourceIdPresent:CRM_ID(account.id,"001")},
   contact:{name:contact.name||"",nativeIdVerified:false,
     sourceIdPresent:CRM_ID(contact.id,"003")},
   cloudAndFeeStatus:"HOLD_SOURCE_RECHECK",fees,
   productCount:previews.length,products:previews,
   provisionalSampleOnlySubtotalKrw:subtotalsReliable?
     provisionalNet.toString():null,
   provisionalExcludesCloudFeeAndProcessDifferences:true,
   provisionalFixedProcessNetKrw:fixedProcessReliable?fixedProcessNet.toString():null,
   provisionalProcessInclusiveNetKrw:comparisonNet===null?null:comparisonNet.toString(),
   provisionalVat10Krw:comparisonVat,
   provisionalGross10Krw:comparisonGross,
   provisionalCloudRatePresent:cloudRatePresent,
   fixedProcessSourceConsistent:fixedProcessReliable,
   comparisonOnlyNotNativePriceApproval:true,
   requiredChecks:checks,verifiedCheckCount:0,
   nativeFieldsAvailable:null,
   nativeFormAuditStatus:"NOT_RUN",
   salesforceCreateEnabled:false,
   approvalLocked:true
 };
}
export function isQueueRequestId(value){return typeof value==="string"&&ID.test(value)}
