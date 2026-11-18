"use client";
import {useState} from "react";

const base={border:"1px solid #35526c",borderRadius:10,padding:15,
 background:"#14283b",color:"#d6e7f3",marginTop:18};
const btn={padding:"10px 15px",background:"#25435b",color:"#d6e7f3",
 border:"1px solid #35526c",borderRadius:8,fontWeight:650,cursor:"pointer"};
const money=x=>Number.isSafeInteger(x)?x.toLocaleString("ko-KR")+" KRW":"확인 필요";

export default function PairedSaveApproval({review}){
 const [busy,setBusy]=useState(false),[precheck,setPrecheck]=useState(null);
 const [confirmation,setConfirmation]=useState("");
 const [duplicateConfirmed,setDuplicateConfirmed]=useState(false);
 const [outcome,setOutcome]=useState(null),[error,setError]=useState("");
 const approve=async mode=>{
  if(busy||!review?.requestId)return;
  if(mode==="COMMIT"){
   if(!precheck||precheck.status!=="READY_FOR_OPERATOR_APPROVAL"||
      confirmation!==precheck.typedConfirmation||!duplicateConfirmed)return;
   if(!window.confirm(
     "SFDC에 신규 Opportunity와 Quotation을 실제 저장합니다. "+
     "Quote Product 입력 단계가 실패하면 미완성 Quote가 남을 수 있습니다. "+
     "자동 재실행은 금지됩니다. 요청 "+review.requestId+" / 승인 "+precheck.approvalDigest+
     "에 동의하십니까?"))return;
  }
  setBusy(true);setError("");
  if(mode==="PRECHECK"){setPrecheck(null);setOutcome(null);setConfirmation("");
    setDuplicateConfirmed(false)}
  try{
   const payload={mode,requestId:review.requestId};
   if(mode==="COMMIT"){
    payload.nonce=precheck.nonce;
    payload.approvalDigest=precheck.approvalDigest;
    payload.confirmation=confirmation;
    payload.duplicateConfirmed=duplicateConfirmed;
   }
   const res=await fetch("/api/sfdc/pair-native-create-local",{
    method:"POST",credentials:"omit",cache:"no-store",
    headers:{"Content-Type":"application/json","X-SFDC-Command":"1"},
    body:JSON.stringify(payload)});
   const data=await res.json();
   if(mode==="PRECHECK")setPrecheck(data);
   else{setOutcome(data);setPrecheck(null);setConfirmation("")}
   if(!res.ok)throw Error(data.code||data.status||"NATIVE_CREATE_BLOCKED");
  }catch(e){setError(e.message||"NATIVE_CREATE_UNAVAILABLE")}
  finally{setBusy(false)}
 };
 return <section style={base} data-testid="sfdc-paired-native-create">
  <h3 style={{margin:"0 0 8px",fontSize:16}}>
    04 · Opportunity + Quotation 실제 저장 (검증된 단일 Product)
  </h3>
  <p style={{fontSize:12,lineHeight:1.75,color:"#a4bdd1"}}>
    인증된 원본 Quote에서 고객 KRW 단가와 Pack·AliCloud를 재검증한 후,
    Opportunity → Research-AMEA Quotation Header → Product·공정 가격·Pack을
    입력합니다. 저장 후 신규 레코드를 다시 읽어 비교합니다.
    복수 Product, 고객 변경, 미검증 가격, 별도 Fee 및 고정 Data release는 차단합니다.
  </p>
  <p style={{fontSize:12,color:"#eac48e",lineHeight:1.7}}>
    Quote Header가 먼저 저장되므로 Product 생성 실패 시 미완성 Quote가 남을 수 있습니다.
    부분 생성·불명확한 저장은 자동 재실행하지 않습니다.
  </p>
  <button data-testid="pair-real-save-precheck" type="button" style={btn}
    disabled={busy||review?.queueStatus!=="PENDING_APPROVAL"}
    onClick={()=>approve("PRECHECK")}>
    {busy?"원본·가격·폼 재검증 중":"실제 저장 전 교차 검증"}
  </button>
  {review?.queueStatus!=="PENDING_APPROVAL"&&<p style={{fontSize:12,color:"#edc58e"}}>
    현재 {review?.queueStatus||"HOLD"} · 원본 KRW 단가를 검증한
    PENDING_APPROVAL 요청만 저장 가능합니다.
  </p>}
  {precheck&&<div data-testid="pair-real-save-review" style={{...base,background:"#0d1928"}}>
    <strong>{precheck.status}</strong>
    {precheck.code&&<p>{precheck.code}</p>}
    {precheck.status==="READY_FOR_OPERATOR_APPROVAL"&&<>
     <p>공급가액 {money(precheck.expectedNetKrw)}
       {" · "}VAT 포함 {money(precheck.expectedGrossKrw)}
       {" · "}샘플 {precheck.samples}개 · AliCloud {precheck.cloudUnits}개 ·
       공정 {precheck.processCount}행</p>
     <p>승인번호 <code>{precheck.approvalDigest}</code> · 3분 유효</p>
     <label htmlFor="paired-save-confirm" style={{fontSize:12}}>
       정확히 <code>{precheck.typedConfirmation}</code> 입력
     </label>
     <input id="paired-save-confirm" value={confirmation}
       onChange={e=>setConfirmation(e.target.value)}
       autoComplete="off" spellCheck={false}
       placeholder={precheck.typedConfirmation}
       style={{display:"block",padding:10,marginTop:8,width:"100%",maxWidth:390,
         background:"#14283b",color:"#d6e7f3",border:"1px solid #35526c",borderRadius:8}}/>
     <label style={{display:"flex",gap:8,alignItems:"start",fontSize:12,marginTop:13}}>
       <input type="checkbox" data-testid="paired-duplicate-confirmation"
         checked={duplicateConfirmed}
         onChange={e=>setDuplicateConfirmed(e.target.checked)}/>
       신규 견적 이름·Account·Contact의 기존 Salesforce 레코드를 직접 확인했고,
       동일 건이 중복 생성되지 않음을 확인했습니다.
       최근 조회 목록 검색만으로 전체 CRM 중복 부재가 보장되지 않는다는 점을 이해합니다.
     </label>
     <button data-testid="pair-real-save-commit" type="button"
       style={{...btn,background:"#9d493c",marginTop:12}}
       disabled={busy||!duplicateConfirmed||
         confirmation!==precheck.typedConfirmation}
       onClick={()=>approve("COMMIT")}>
       실제 Salesforce Opportunity + Quotation 저장
     </button>
    </>}
  </div>}
  {outcome&&<div data-testid="pair-real-save-result" role="status"
    style={{...base,background:"#0d1928"}}>
    <strong>{outcome.status}</strong>
    {outcome.code&&<p>상태 코드: {outcome.code}</p>}
    {outcome.opportunityId&&<p><a target="_blank" rel="noreferrer"
      href={"https://novogene.lightning.force.com/lightning/r/Opportunity/"+
        outcome.opportunityId+"/view"}>
      신규 Opportunity 확인</a></p>}
    {outcome.quoteId&&<p><a target="_blank" rel="noreferrer"
      href={"https://novogene.lightning.force.com/lightning/r/Quotation__c/"+
        outcome.quoteId+"/view"}>
      신규 Quotation 확인</a></p>}
    {outcome.status!=="PAIR_CREATED_VERIFIED"&&<p style={{color:"#eac48e"}}>
      부분 저장 가능성을 배제할 수 없습니다. 자동 재시도하지 말고
      Salesforce에서 생성 기록을 대조해야 합니다.</p>}
  </div>}
  {error&&<p role="alert" style={{color:"#f4b69c",fontSize:12}}>{error}</p>}
 </section>
}
