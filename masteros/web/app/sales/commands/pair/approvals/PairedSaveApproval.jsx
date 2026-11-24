"use client";
import {useEffect,useRef,useState} from "react";

// Reusable inline two-step approval. No separate approval page or manual
// Account/Contact/Process/Unit-Price re-entry: all come from the source Oppo
// + Quote referenced by the immutable local request and rechecked by SFDC.
const card={border:"1px solid #cfdae2",borderRadius:12,padding:16,
  background:"#f5f9fb",color:"#143040",marginTop:16};
const button={padding:"10px 17px",border:"1px solid #8ba7b7",
  borderRadius:8,background:"#17617d",color:"#fff",fontWeight:700,
  cursor:"pointer"};
const krw=value=>/^(0|[1-9]\d*)$/.test(String(value??""))?
  Number(value).toLocaleString("ko-KR")+"원":"확인 필요";
const endpoint="/api/sfdc/pair-native-create-local";

export default function PairedSaveApproval({review,compact=false}){
 const [busy,setBusy]=useState(false),[precheck,setPrecheck]=useState(null);
 const initialCheckId=useRef(null);
 const [duplicateChecked,setDuplicateChecked]=useState(false);
 const [outcome,setOutcome]=useState(null),[error,setError]=useState("");
 const status=review?.queueStatus||"NEEDS_REVIEW";
 const ready=status==="PENDING_APPROVAL";
 const send=async(mode)=>{
  if(!review?.requestId||busy)return;
  if(mode==="COMMIT"){
    if(precheck?.status!=="READY_FOR_OPERATOR_APPROVAL"||!duplicateChecked)return;
    const accepted=window.confirm(
      "다음 고객의 신규 Opportunity와 Quote를 실제 Salesforce에 저장합니다.\n"+
      (review.name||"")+(review.accountName?"\n기관: "+review.accountName:"")+
      "\n공급가액: "+krw(precheck.expectedNetKrw)+
      " / VAT 포함: "+krw(precheck.expectedGrossKrw)+
      "\n검증번호: "+precheck.approvalDigest+
      "\n\n저장 실패 시 일부 레코드가 남을 수 있으며 자동 재실행하지 않습니다.\n진행하시겠습니까?");
    if(!accepted)return;
  }
  setBusy(true);setError("");
  if(mode==="PRECHECK"){
    setPrecheck(null);setDuplicateChecked(false);setOutcome(null);
  }
  try{
    const payload={mode,requestId:review.requestId};
    if(mode==="COMMIT"){
      payload.nonce=precheck.nonce;
      payload.approvalDigest=precheck.approvalDigest;
      payload.confirmation=precheck.typedConfirmation;
      payload.duplicateConfirmed=duplicateChecked;
    }
    const response=await fetch(endpoint,{method:"POST",cache:"no-store",credentials:"omit",
      headers:{"Content-Type":"application/json","X-SFDC-Command":"1"},
      body:JSON.stringify(payload)});
    const data=await response.json();
    if(mode==="PRECHECK")setPrecheck(data);
    else{setOutcome(data);setPrecheck(null);setDuplicateChecked(false)}
    if(!response.ok||["HOLD","BLOCK"].includes(data.status))
      throw Error(data.code||data.status||"SFDC_SAVE_BLOCKED");
  }catch(e){setError(e.message||"SFDC_SOURCE_UNAVAILABLE")}
  finally{setBusy(false)}
 };
 // Inline workflow: run the read-only native preflight automatically as soon as
 // the newly submitted immutable request is ready. The Salesforce write still
 // requires the operator checkbox and the explicit browser confirmation.
 useEffect(()=>{
  if(!compact||!ready||!review?.requestId||initialCheckId.current===review.requestId)return;
  initialCheckId.current=review.requestId;
  send("PRECHECK");
  // One preflight per immutable request; manual retry remains available below.
  // eslint-disable-next-line react-hooks/exhaustive-deps
 },[compact,ready,review?.requestId]);
 return <section style={card} data-testid="sfdc-paired-native-create">
  {!compact&&<h3 style={{margin:"0 0 8px",fontSize:17}}>Opportunity + Quote 실제 생성</h3>}
  <p style={{fontSize:13,marginTop:0}}>
    <strong>원본 Oppo·Quote 정보 자동 적용</strong> · 고객/공정/단가 재입력 없이 생성합니다.
  </p>
  {review?.name&&<p style={{fontSize:12}}>신규 이름: <b>{review.name}</b>
    {review.accountName?" · "+review.accountName:""}</p>}
  <p style={{fontSize:12}}>
    {ready?"원본 가격 확인됨 · 저장 전 최종 검증 가능":
      "원본 KRW 단가 또는 필수 정보 검증이 필요합니다. 실제 저장은 차단됩니다."}
  </p>
  <button type="button" style={button} data-testid="pair-real-save-precheck"
    disabled={busy||!ready} onClick={()=>send("PRECHECK")}>
    {busy?"원본 자동 검증 중…":compact?"원본·가격 재검증":"① 원본 대조 및 최종 금액 확인"}
  </button>
  {precheck&&<div data-testid="pair-real-save-review"
    style={{borderTop:"1px solid #c6d6df",paddingTop:12,marginTop:12}}>
    <strong style={{fontSize:13}}>{precheck.status==="READY_FOR_OPERATOR_APPROVAL"?
      "검증 완료 · 저장 전 마지막 확인":precheck.status}</strong>
    {precheck.code&&<p style={{fontSize:12,color:"#ae4b31"}}>보류: {precheck.code}</p>}
    {precheck.status==="READY_FOR_OPERATOR_APPROVAL"&&<>
      <p style={{fontSize:13,margin:"10px 0"}}>
        샘플 <b>{precheck.samples}</b>개 · 공정 <b>{precheck.processCount}</b>개 ·
        AliCloud <b>{precheck.cloudUnits}</b>개
      </p>
      <p style={{fontSize:14,margin:"8px 0"}}>
        공급가액 <strong>{krw(precheck.expectedNetKrw)}</strong> ·
        VAT 포함 <strong>{krw(precheck.expectedGrossKrw)}</strong>
      </p>
      <label style={{display:"flex",alignItems:"start",gap:8,fontSize:12,
        margin:"13px 0",cursor:"pointer"}}>
        <input type="checkbox" data-testid="paired-duplicate-confirmation"
          checked={duplicateChecked} onChange={e=>setDuplicateChecked(e.target.checked)}/>
        같은 Account·Contact의 동일 견적이 이미 생성되지 않았는지 확인했습니다.
      </label>
      <button type="button" style={{...button,background:"#ad4d34"}}
        data-testid="pair-real-save-commit" disabled={busy||!duplicateChecked}
        onClick={()=>send("COMMIT")}>
        Oppo + Quote 최종 저장
      </button>
      <p style={{fontSize:11,color:"#5c7180"}}>
        3분 이내 승인 · 한 건씩 저장 · 부분 실패 시 자동 중복 생성 방지
      </p>
    </>}
  </div>}
  {outcome&&<div data-testid="pair-real-save-result" role="status"
    style={{marginTop:12,fontSize:12}}>
    <strong>{outcome.status==="PAIR_CREATED_VERIFIED"?"Oppo·Quote 생성 및 재조회 완료":
      "저장 결과 확인 필요: "+outcome.status}</strong>
    {outcome.code&&<p>{outcome.code}</p>}
    {outcome.opportunityId&&<p><a target="_blank" rel="noreferrer"
      href={"https://novogene.lightning.force.com/lightning/r/Opportunity/"+
        outcome.opportunityId+"/view"}>신규 Opportunity 열기</a></p>}
    {outcome.quoteId&&<p><a target="_blank" rel="noreferrer"
      href={"https://novogene.lightning.force.com/lightning/r/Quotation__c/"+
        outcome.quoteId+"/view"}>신규 Quote 열기</a></p>}
    {outcome.status!=="PAIR_CREATED_VERIFIED"&&<p>
      추가 저장을 누르지 말고 생성된 Salesforce ID를 먼저 확인하세요.
    </p>}
  </div>}
  {error&&<p role="alert" style={{color:"#ae4b31",fontSize:12}}>확인 필요: {error}</p>}
 </section>;
}
