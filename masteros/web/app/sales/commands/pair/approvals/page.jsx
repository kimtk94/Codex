"use client";
import {useCallback,useEffect,useState} from "react";
import Link from "next/link";
import PairedSaveApproval from "./PairedSaveApproval";

const endpoint="/api/sfdc/pair-approval-review-local";
async function local(body){
 const res=await fetch(endpoint,{method:"POST",credentials:"omit",cache:"no-store",
  headers:{"Content-Type":"application/json","X-SFDC-Command":"1"},
  body:JSON.stringify(body)});
 const data=await res.json();
 if(!res.ok||data.status==="BLOCK")throw Error(data.code||"LOCAL_OPERATOR_REVIEW_UNAVAILABLE");
 return data;
}
const money=n=>{
 if(!/^(0|[1-9]\d*)$/.test(String(n??"")))return "미확정";
 return BigInt(n).toLocaleString("ko-KR")+" KRW";
};
const kst=x=>x?new Date(x).toLocaleString("ko-KR",{timeZone:"Asia/Seoul",hour12:false}):"기록 없음";
const bg="#0d1928",surface="#14283b",border="#35526c",ink="#d6e7f3",sub="#a4bdd1";
const pane={border:"1px solid "+border,borderRadius:13,padding:17,background:surface,marginTop:16};
const button={border:"1px solid "+border,borderRadius:9,padding:"10px 15px",
 color:ink,background:"#25435b",cursor:"pointer",fontSize:13,fontWeight:650};
const tabCell={padding:"9px 11px",borderBottom:"1px solid "+border,textAlign:"left",fontSize:12};
const format=x=>JSON.stringify(x,null,2);

export default function LocalSalesforceApprovalConsole(){
 const [items,setItems]=useState([]);
 const [loading,setLoading]=useState(false);
 const [selectedId,setSelectedId]=useState("");
 const [review,setReview]=useState(null);
 const [rehearsal,setRehearsal]=useState(null);
 const [prepared,setPrepared]=useState(null);
 const [preparing,setPreparing]=useState(false);
 const [rehearsing,setRehearsing]=useState(false);
 const [error,setError]=useState("");
 const [message,setMessage]=useState("");
 const [nativeStage,setNativeStage]=useState("OPPORTUNITY");
 const [nativePrecheck,setNativePrecheck]=useState(null);
 const [nativeConfirmation,setNativeConfirmation]=useState("");
 const [nativeBusy,setNativeBusy]=useState(false);
 const [nativeSaveResult,setNativeSaveResult]=useState(null);
 const [nativeError,setNativeError]=useState("");
 const refresh=useCallback(async()=>{
  setLoading(true);setError("");
  try{
   const data=await local({mode:"LIST"});
   if(data.status!=="PASS"||!Array.isArray(data.items))throw Error("QUEUE_LIST_INVALID");
   setItems(data.items);
  }catch(e){setError(e.message);setItems([])}
  finally{setLoading(false)}
 },[]);
 useEffect(()=>{refresh()},[refresh]);
 const choose=async id=>{
  setSelectedId(id);setReview(null);setPrepared(null);setError("");setMessage("");
  setNativePrecheck(null);setNativeConfirmation("");setNativeSaveResult(null);setNativeError("");
  try{
   const data=await local({mode:"DETAIL",requestId:id});
   if(data.requestId!==id)throw Error("APPROVAL_REVIEW_ID_MISMATCH");
   setReview(data);
  }catch(e){setError(e.message)}
 };
 const runRehearsal=async()=>{
  if(rehearsing)return;
  setRehearsing(true);setRehearsal(null);setError("");
  try{
   const data=await local({mode:"FORM_REHEARSAL"});
   setRehearsal(data);
  }catch(e){setError(e.message)}
  finally{setRehearsing(false)}
 };
 const prepareOpportunity=async()=>{
  if(!review||preparing||!["PENDING_APPROVAL","NEEDS_REVIEW"].includes(review.queueStatus))return;
  setPreparing(true);setPrepared(null);setError("");
  try{
    const data=await local({mode:"OPPO_UNSAVED_PREPARE",requestId:review.requestId});
    setPrepared(data);
  }catch(e){setError(e.message)}
  finally{setPreparing(false)}
 };
 const nativeRequest=async mode=>{
  if(!review||nativeBusy)return;
  if(mode==="COMMIT"&&(!nativePrecheck||
    nativePrecheck.status!=="READY_FOR_EXACT_RECORD_SAVE_CLICK"||
    nativeConfirmation!=="SAVE "+nativePrecheck.approvalDigest.slice(-8)))return;
  if(mode==="COMMIT"&&!window.confirm(
    "Salesforce에 신규 "+(nativeStage==="OPPORTUNITY"?"Opportunity":"Quotation")+
    "을 실제 생성합니다. 요청 "+review.requestId+
    " / 승인 "+nativePrecheck.approvalDigest+
    "을 확인했습니까? Save 실행 후 되돌리기 어려울 수 있습니다."))return;
  setNativeBusy(true);setNativeError("");
  if(mode==="PRECHECK"){
   setNativePrecheck(null);setNativeConfirmation("");setNativeSaveResult(null);
  }
  try{
   const body={mode,stage:nativeStage,requestId:review.requestId};
   if(mode==="COMMIT"){
    body.approvalDigest=nativePrecheck.approvalDigest;
    body.nonce=nativePrecheck.nonce;
    body.confirmation=nativeConfirmation;
   }
   const response=await fetch("/api/sfdc/pair-native-save-local",{
    method:"POST",credentials:"omit",cache:"no-store",
    headers:{"Content-Type":"application/json","X-SFDC-Command":"1"},
    body:JSON.stringify(body)
   });
   const result=await response.json();
   if(mode==="PRECHECK"){
    setNativePrecheck(result);
   }else{
    setNativeSaveResult(result);
    setNativePrecheck(null);setNativeConfirmation("");
    if(result.status==="NATIVE_SAVE_CREATED_AND_READBACK"&&nativeStage==="OPPORTUNITY"){
      setNativeStage("QUOTATION");
    }
   }
   if(!response.ok)throw Error(result.code||result.status||"NATIVE_SAVE_REQUEST_ERROR");
  }catch(e){setNativeError(e.message||"NATIVE_SAVE_UNAVAILABLE")}
  finally{setNativeBusy(false)}
 };
 const switchNativeStage=value=>{
  setNativeStage(value);setNativePrecheck(null);setNativeConfirmation("");
  setNativeSaveResult(null);setNativeError("");
 };
 const copy=async()=>{
  if(!review)return;
  try{await navigator.clipboard.writeText(format(review));
    setMessage("로컬 검토 내용을 복사했습니다. 외부 전송·SFDC 저장은 하지 않았습니다.");
  }catch{setMessage("클립보드 권한이 없어 복사하지 못했습니다.")}
 };
 return <main style={{maxWidth:1180,margin:"0 auto",padding:"26px 16px 75px",
   background:bg,color:ink,minHeight:"100vh",fontFamily:"system-ui,sans-serif"}}>
  <nav style={{display:"flex",gap:18,fontSize:12,marginBottom:22,flexWrap:"wrap"}}>
   <Link style={{color:"#9ed7fa"}} href="/sales/commands/pair">원본 Oppo–Quote 선택 화면</Link>
   <Link style={{color:"#9ed7fa"}} href="/sales/oppo-quote/new">신규 Product·가격 초안</Link>
  </nav>
  <header>
   <p style={{fontSize:12,color:"#88c2df",letterSpacing:1,fontWeight:700}}>NGKR / SFDC / LOCAL LAPTOP ONLY</p>
   <h1 style={{fontSize:28,margin:"4px 0 8px"}}>Opportunity–Quotation 실제 저장 사전검토</h1>
   <p style={{fontSize:13,color:sub,lineHeight:1.8,maxWidth:850}}>
    기존 Quote에서 신규 견적 초안을 만들고 로컬 승인 대기열에 등록하면 이곳에서
    Account·Contact·Product·공정·가격·중복·VAT를 검토할 수 있습니다.
    Quotation은 Research-AMEA 유형을 사용하며, 사용자 승인 전에는 Salesforce 저장을 실행하지 않습니다.
   </p>
  </header>
  <section data-testid="sfdc-save-hold-banner" style={{...pane,background:"#233145"}}>
   <strong>현재 상태: 저장 승인 전 · Salesforce 쓰기 0건</strong>
   <p style={{fontSize:12,lineHeight:1.7,marginBottom:0}}>
    현재 자동화로 보장할 수 있는 범위는 승인 요청 원본 조회와 SFDC의 실제 입력 폼 점검입니다.
    <strong>실제 Save는 아래의 건별 원본 검증과 명시적 승인에 모두 통과해야 활성화됩니다.</strong>
    검증되지 않은 Quote의 Product·Process 생성은 계속 보류됩니다.
    승인 요청을 열었다고 실제 Quote가 생성되는 것은 아닙니다.
   </p>
  </section>
  <section style={pane}>
   <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",flexWrap:"wrap",gap:12}}>
    <div><h2 style={{fontSize:18,margin:"0 0 7px"}}>01 · 노트북 승인 대기열</h2>
     <p style={{fontSize:12,color:sub,margin:0}}>
      기존 Oppo–Quote 화면의 'Oppo·Quote 통합 생성 요청'으로 등록된 항목만 표시
     </p></div>
    <button type="button" style={button} disabled={loading} onClick={refresh}>
     {loading?"불러오는 중":"대기열 새로고침"}
    </button>
   </div>
   <div data-testid="queued-approval-requests" style={{display:"grid",gap:8,marginTop:13}}>
    {!loading&&items.length===0&&<p style={{fontSize:13,color:sub}}>
     현재 표시할 승인 대기 건이 없습니다. 기존 Quote를 선택한 뒤 생성 요청을 먼저 등록해 주세요.
    </p>}
    {items.map(row=><button type="button" key={row.requestId} style={{
      ...button,textAlign:"left",width:"100%",background:selectedId===row.requestId?"#255777":"#1c344a",
      display:"flex",justifyContent:"space-between",gap:12,flexWrap:"wrap"
    }} onClick={()=>choose(row.requestId)}>
      <span><strong>{row.name}</strong>
       <span style={{display:"block",fontSize:11,color:sub,marginTop:5}}>
       {row.accountName||"Account 미확인"} · {row.contactName||"Contact 미확인"}
       {" · "}Product {row.productCount}개 · {kst(row.createdAtUtc)}</span></span>
      <span style={{fontSize:12}}>재검증 {row.pendingChecks}항목 · {row.queueStatus}</span>
    </button>)}
   </div>
  </section>
  {review&&<section style={pane} data-testid="single-quote-save-review">
   <h2 style={{fontSize:18}}>02 · 저장될 내용 사전검토 — {review.name}</h2>
   <p style={{color:sub,fontSize:12}}>요청번호: <code>{review.requestId}</code>
    {" · "}원본 QID: {review.sourceQid||"미기재"}{" · "}Close Date: {review.closeDateKst||"미확인"}</p>
   <div data-testid="same-name-native-id-policy" style={{fontSize:12,
    background:bg,border:"1px solid "+border,borderRadius:9,padding:11,overflowWrap:"anywhere"}}>
     <strong>이름 유지 · Salesforce ID로 구분</strong>
     <p style={{margin:"6px 0"}}>Opportunity/Quote 이름은 원본과 같아도 됩니다.
      별도 번호·접미사를 추가하지 않습니다. 기존 레코드는 아래 원본 ID로 유지되며,
      신규 레코드는 Save 후 발급된 서로 다른 006/a0P ID로 구별합니다.</p>
     <p style={{margin:"6px 0"}}>원본 Opportunity: <code>{review.sourceOpportunityId||"ID 확인 필요"}</code>
      {" · "}원본 Quotation: <code>{review.sourceQuoteId||"ID 확인 필요"}</code></p>
   </div>
   <div data-testid="sfdc-native-source-process-audit" style={{fontSize:12,
      background:bg,border:"1px solid "+border,borderRadius:9,padding:12,marginTop:12}}>
      <strong>원본 Product·Process 실제 SFDC ID 검증</strong>
      <p style={{margin:"6px 0"}}>
        {review.sourceAudit?.status==="NOT_RUN"||!review.sourceAudit?
         "기존 Salesforce 공정 레코드의 신규 저장 검증 자료가 없습니다.":
         "검토 상태: "+review.sourceAudit.status+
         " · 원본 Process "+review.sourceAudit.processRows+"개 확인"}
      </p>
      {review.sourceAudit?.reasonCodes?.includes(
        "ALICLOUD_EXCLUDED_BUT_SOURCE_HAS_ALICLOUD_TYPED_PROCESS")&&
        <p style={{color:"#edc58e",margin:"6px 0"}}>
          AliCloud 제외 조건과 원본 Data release 30,000원(Process Type: AliCloud)이
          충돌합니다. 추가 AliCloud를 제외하되 Data release는 유지할지
          결정되기 전까지 저장할 수 없습니다.
        </p>}
      {review.sourceAudit?.reasonCodes?.filter(x=>
        x!=="ALICLOUD_EXCLUDED_BUT_SOURCE_HAS_ALICLOUD_TYPED_PROCESS")
        .map((reason,i)=><p key={i} style={{margin:"4px 0",color:"#edc58e"}}>
        {reason}</p>)}
      <p style={{margin:"6px 0",color:sub}}>
        위 결과는 원본 검증이며 새 Opportunity·Quotation 저장 승인이 아닙니다.
      </p>
   </div>
   <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))",gap:9}}>
    {[["Account",review.account.name,review.account.sourceIdPresent],
     ["Contact",review.contact.name,review.contact.sourceIdPresent],
     ["신규 Product",String(review.productCount)+"개",false],
     ["신규 저장 승인","미승인",false]].map(([title,value,hasId])=>
       <div key={title} style={{padding:12,borderRadius:9,background:bg,border:"1px solid "+border}}>
        <div style={{fontSize:11,color:sub}}>{title}</div>
        <strong style={{fontSize:14}}>{value||"원본 확인 필요"}</strong>
        <div style={{fontSize:11,color:"#e0b982",marginTop:5}}>
         {hasId?"원본 ID 존재 · 실시간 검증 전":"검증 필요"}</div>
       </div>)}
   </div>
   <h3 style={{fontSize:14,marginTop:20}}>Product별 역사적 참고 단가 (신규 가격 확정 아님)</h3>
   <div style={{overflow:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",minWidth:900}}>
    <thead><tr>{["Product","샘플 수","기존 공정/생산량","참고 KRW/sample","참고 Cloud KRW","샘플 부분합","공정 수"].map(h=>
     <th key={h} style={tabCell}>{h}</th>)}</tr></thead>
    <tbody>{review.products.map((p,i)=><tr key={p.reference_product_id+"-"+i}>
     <td style={tabCell}>{p.service||"미확인"}</td>
     <td style={tabCell}>{p.samples}</td>
     <td style={tabCell}>{p.productionGb||"미확인"} Gb</td>
     <td style={tabCell}>{money(p.historical_sample_unit_krw)}</td>
     <td style={tabCell}>{money(p.historical_cloud_unit_krw)}</td>
     <td style={tabCell}>{money(p.historical_sample_subtotal_krw)}</td>
     <td style={tabCell}>{p.process_count}</td>
    </tr>)}</tbody>
   </table></div>
   <p style={{fontSize:12,color:"#edc58e"}}>
     위 샘플 부분합은 원본 가격 * 샘플 수를 단순 계산한 참고값이며
     Cloud·Process별 수량 차이·Pack·배송비·VAT가 제외되어 <strong>최종 Quotation 금액이 아닙니다.</strong>
   </p>
   {review.products.some(p=>p.fixed_process_lines?.length>0)&&<div
     data-testid="fixed-process-quote-comparison"
     style={{marginTop:14,padding:12,background:bg,border:"1px solid "+border,borderRadius:9}}>
     <strong style={{fontSize:13}}>샘플 금액 외 추가된 Process (별도 계산)</strong>
     {review.products.flatMap((p,i)=>(p.fixed_process_lines||[]).map((f,j)=>
       <p key={i+"-"+j} style={{fontSize:12,margin:"7px 0"}}>
         {f.process_name||f.process_id} · 수량 {f.quantity} × {money(String(f.unit_price_krw))} =
         {" "}<strong>{money(f.net_krw)}</strong>
         {!f.reference_verified&&<span style={{color:"#f3ba99"}}> · 원본 불일치</span>}
       </p>
     ))}
     <p style={{fontSize:12,margin:"8px 0"}}>
       샘플 부분합 {money(review.provisionalSampleOnlySubtotalKrw)}
       {" + "}추가 공정 {money(review.provisionalFixedProcessNetKrw)}
     </p>
     <p style={{fontSize:14,margin:"8px 0"}}>
       <strong>공정 포함 참고 공급가액: {money(review.provisionalProcessInclusiveNetKrw)}</strong>
       {" · "}VAT 10%: {money(review.provisionalVat10Krw)}
       {" · "}VAT 포함: {money(review.provisionalGross10Krw)}
     </p>
     <p style={{fontSize:12,color:"#edc58e",margin:"6px 0"}}>
       2026년 원본 단가를 적용한 비교 금액입니다. 기존 견적의 승인은
       신규 고객 가격 승인과 다릅니다.
       {review.provisionalCloudRatePresent?
        " Cloud 단가가 있으므로 실제 총 Gb와 Cloud 수량을 별도로 확인해야 합니다.":
        " Cloud·Fee 포함 여부와 실제 Salesforce 공정 입력을 재검증해야 합니다."}
     </p>
   </div>}
   <details><summary style={{cursor:"pointer",fontSize:13}}>원본 Process 명칭·ID 참조 펼치기</summary>
    {review.products.map((p,i)=><p key={i} style={{fontSize:12,overflowWrap:"anywhere"}}>
      <strong>{p.service}</strong> · {p.original_process_names.join(" · ")}
    </p>)}
   </details>
   <h3 style={{fontSize:14,marginTop:20}}>필수 검증 항목</h3>
   <div style={{display:"grid",gap:8}}>
    {review.requiredChecks.map(check=><div key={check.id} style={{padding:10,border:"1px solid "+border,
      borderRadius:8,background:bg,fontSize:12}}>
      <strong style={{color:check.passed?"#79cda9":"#e3bd83"}}>
       {check.passed?"PASS":"HOLD"} · {check.label}
      </strong>
      <div style={{marginTop:4,color:sub}}>{check.evidence}</div>
    </div>)}
   </div>
   <p style={{fontSize:12,color:sub,lineHeight:1.7}}>Description: {review.description||"새로 작성 필요"}</p>
   <div style={{display:"flex",gap:9,flexWrap:"wrap",marginTop:16}}>
    <button type="button" style={button} onClick={copy}>검토 내용 JSON 복사 (로컬)</button>
    <button type="button" style={button} onClick={prepareOpportunity}
      data-testid="prepare-opportunity-unsaved"
      disabled={preparing||!["PENDING_APPROVAL","NEEDS_REVIEW"].includes(review.queueStatus)}>
      {preparing?"SFDC Opportunity 초안 입력 중":"Opportunity 입력창 열고 3개 필드 채우기 (No Save)"}
    </button>
    <button type="button" style={{...button,opacity:0.5,cursor:"not-allowed"}} disabled
      data-testid="save-to-sfdc-disabled">
      Salesforce 실제 저장 · 원본 검증·건별 승인 후 활성화
    </button>
   </div>
   {prepared&&<div data-testid="prepared-unsaved-opportunity" role="status"
     style={{marginTop:12,padding:12,border:"1px solid "+border,borderRadius:8}}>
     <strong>{prepared.status}</strong>
     <p style={{fontSize:12,color:sub}}>
       새 Salesforce Opportunity 탭에서 Name·Close Date·Progress Description만 입력합니다.
       Account·Contact·Amount·Stage·Forecast 등은 검증 전이므로 채우지 않았습니다.
       Save는 누르지 않았으며, 생성 전에 중복 및 전체 필수값을 확인해야 합니다.
     </p>
     <div style={{fontSize:12}}>
      {Object.entries(prepared.fields||{}).map(([k,v])=><span key={k} style={{marginRight:15}}>
       {k}: {v}</span>)}
     </div>
    </div>}
   {message&&<p role="status" style={{fontSize:12}}>{message}</p>}
   <PairedSaveApproval key={review.requestId} review={review}/>
   <section data-testid="sfdc-native-save-approval" style={{
     marginTop:20,padding:15,border:"1px solid #557187",borderRadius:10}}>
     <h3 style={{fontSize:16,margin:"0 0 8px"}}>04 · 실제 Salesforce Save (건별 승인)</h3>
     <p style={{fontSize:12,lineHeight:1.65,color:sub}}>
       이 기능은 실제 Salesforce 레코드를 생성합니다. 로컬 검증 파일에
       고객 Account·Contact, Product·Process·Pack, 현재 승인 KRW 단가,
       VAT/Cloud/Fee와 Salesforce 006/a0P 고유 ID·저장 재실행 여부가 확인되어야 합니다.
       동일 이름 자체는 저장 차단 사유가 아닙니다.
       Salesforce에 해당 신규 입력창을 열고 내용을 완성한 뒤,
       검증이 통과한 요청의 승인번호를 직접 입력해야 Save가 활성화됩니다.
       과거 견적 가격만으로는 승인되지 않습니다.
     </p>
     <div style={{display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}>
       <label htmlFor="native-save-stage" style={{fontSize:12}}>저장 단계</label>
       <select id="native-save-stage" value={nativeStage}
        onChange={e=>switchNativeStage(e.target.value)}
        style={{...button,padding:"9px 11px"}} disabled={nativeBusy}>
         <option value="OPPORTUNITY">1단계 · Opportunity</option>
         <option value="QUOTATION">2단계 · Quotation (Research-AMEA)</option>
       </select>
       <button type="button" data-testid="check-native-save" style={button}
        disabled={nativeBusy} onClick={()=>nativeRequest("PRECHECK")}>
         {nativeBusy?"확인 중":"현재 SFDC 입력값·단가·중복 검증"}
       </button>
     </div>
     {nativePrecheck&&<div role="status" data-testid="native-save-precheck-result"
       style={{padding:12,background:bg,borderRadius:9,marginTop:12,fontSize:12}}>
       <strong>{nativePrecheck.status}</strong>
       {nativePrecheck.code&&<p style={{color:"#f3ba99"}}>
        보류 사유: {nativePrecheck.code}</p>}
       {nativePrecheck.reasons?.length>0&&<p style={{color:"#f3ba99"}}>
        추가 확인: {nativePrecheck.reasons.join(" · ")}</p>}
       {nativePrecheck.missing?.length>0&&<p style={{color:"#f3ba99"}}>
        입력창 검증 미완료: {nativePrecheck.missing.join(" · ")}</p>}
       {nativePrecheck.status==="READY_FOR_EXACT_RECORD_SAVE_CLICK"&&<>
         <p>대상: {nativePrecheck.name} · {nativeStage} ·
          Product {nativePrecheck.productCount}개 / Process {nativePrecheck.processCount}행</p>
         <p>공급가액(부가세 제외) <strong>{money(nativePrecheck.netKrw)}</strong>
           {" · "}VAT 10% {money(nativePrecheck.vatKrw)}
           {" · "}VAT 포함 {money(nativePrecheck.grossKrw)}</p>
         <p>승인번호: <code>{nativePrecheck.approvalDigest}</code> ·
           3분 이내 1회만 사용 가능</p>
         <label htmlFor="native-save-confirm" style={{display:"block",fontSize:12,marginBottom:6}}>
           정확히 <code>{"SAVE "+nativePrecheck.approvalDigest.slice(-8)}</code> 입력
         </label>
         <input id="native-save-confirm" value={nativeConfirmation}
           onChange={e=>setNativeConfirmation(e.target.value)}
           autoComplete="off" spellCheck={false}
           placeholder={"SAVE "+nativePrecheck.approvalDigest.slice(-8)}
           style={{width:"100%",maxWidth:330,padding:"10px",borderRadius:8,
             background:surface,color:ink,border:"1px solid "+border,fontFamily:"monospace"}}/>
       </>}
     </div>}
     <div style={{display:"flex",gap:10,marginTop:12,flexWrap:"wrap"}}>
      <button type="button" style={{
        ...button,background:nativePrecheck?.status==="READY_FOR_EXACT_RECORD_SAVE_CLICK"?"#94503a":"#253344",
        opacity:nativePrecheck?.status==="READY_FOR_EXACT_RECORD_SAVE_CLICK"?1:0.55
       }} data-testid="commit-sfdc-native-save"
       disabled={nativeBusy||
         nativePrecheck?.status!=="READY_FOR_EXACT_RECORD_SAVE_CLICK"||
         nativeConfirmation!=="SAVE "+nativePrecheck?.approvalDigest?.slice(-8)}
       onClick={()=>nativeRequest("COMMIT")}>
        {nativeBusy?"SFDC 저장 처리 중":"검토한 건 실제 Salesforce Save 실행"}
      </button>
     </div>
     {nativeSaveResult&&<div role="status" data-testid="native-save-commit-result"
       style={{padding:12,background:bg,borderRadius:9,marginTop:12,fontSize:12}}>
       <strong>{nativeSaveResult.status}</strong>
       {nativeSaveResult.nativeRecordUrl&&
        <p><a style={{color:"#9bd4f6"}} href={nativeSaveResult.nativeRecordUrl}
          target="_blank" rel="noreferrer">생성된 Salesforce {nativeSaveResult.stage} 확인</a></p>}
       {nativeSaveResult.status?.includes("UNKNOWN")&&<p style={{color:"#f3ba99"}}>
         Salesforce 저장 후 확인이 불완전할 수 있습니다.
         동일한 요청을 다시 실행하지 말고 원본 SFDC를 직접 확인해야 합니다.
       </p>}
     </div>}
     {nativeError&&<p role="alert" style={{fontSize:12,color:"#f3ba99"}}>{nativeError}</p>}
   </section>
  </section>}
  <section style={pane}>
   <h2 style={{fontSize:18,margin:"0 0 8px"}}>03 · Salesforce 실제 입력 폼 테스트</h2>
   <p style={{fontSize:12,color:sub,lineHeight:1.6}}>
    노트북에서 로그인되어 있는 Salesforce Chrome을 사용합니다. Opportunity New 및
    Research-AMEA Quotation New 화면을 각각 열어 필수 필드와 Save 버튼의 존재만 확인합니다.
    값 입력이나 Save 클릭은 하지 않으며, 작업 후 테스트 탭은 닫힙니다.
   </p>
   <button type="button" style={button} onClick={runRehearsal} disabled={rehearsing}
     data-testid="sfdc-native-form-rehearsal">
    {rehearsing?"SFDC 화면 점검 중":"SFDC 실제 생성 화면 점검 (No Save)"}
   </button>
   <div style={{display:"flex",gap:16,fontSize:12,marginTop:12,flexWrap:"wrap"}}>
    <a href="https://novogene.lightning.force.com/lightning/o/Opportunity/list"
      target="_blank" rel="noreferrer" style={{color:"#9bd4f6"}}>SFDC Opportunity 목록</a>
    <a href="https://novogene.lightning.force.com/lightning/o/Quotation__c/list"
      target="_blank" rel="noreferrer" style={{color:"#9bd4f6"}}>SFDC Quotation 목록</a>
   </div>
   {rehearsal&&<div data-testid="sfdc-rehearsal-result" role="status" style={{marginTop:14,fontSize:12}}>
    <strong>{rehearsal.status}</strong>
    {rehearsal.forms.map(f=><div key={f.kind} style={{padding:12,border:"1px solid "+border,
      borderRadius:8,marginTop:8}}>
      <strong>{f.kind} · {f.status}</strong> · {f.record_type}
      <div>{f.reason}</div>
      <div style={{marginTop:4,color:sub}}>
       {Object.entries(f.required||{}).map(([k,v])=>k+" "+(v?"PASS":"HOLD")).join(" · ")}
      </div>
     </div>)}
    <p>저장·수정 요청 0건 · UI 점검만 완료</p>
   </div>}
  </section>
  {error&&<p role="alert" style={{color:"#f6b5a9",fontSize:12}}>{error}</p>}
  <footer style={{marginTop:24,fontSize:12,color:sub}}>
   GitHub Actions는 인위적으로 생성한 테스트 데이터만 검증하며,
   고객 견적이나 실제 Salesforce 저장은 노트북의 인증된 브라우저에서만 처리합니다.
  </footer>
 </main>;
}
