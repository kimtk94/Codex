"use client";
import {useEffect,useState} from "react";
import {reconcileQuoteSource} from "../../../../lib/sfdc-source-identity.mjs";
import {verifiedSourcePrice} from "../../../../lib/sfdc-pair-auto-krw.mjs";
import styles from "./page.module.css";

const ID=/^a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;
const OPP=/^006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;

async function readLive(resource,recordId){
  const response=await fetch("/api/sfdc/records-local",{
    method:"POST",credentials:"omit",cache:"no-store",
    headers:{"Content-Type":"application/json","X-SFDC-Command":"1"},
    body:JSON.stringify({mode:"detail",resource,recordId,forceLive:true})
  });
  const result=await response.json();
  if(!response.ok||result.status!=="PASS")throw Error(result.code||"SFDC_UI_UNAVAILABLE");
  return result;
}

export default function SourceSalesforceEvidence({quote,onVerified}){
  const [busy,setBusy]=useState(false);
  const [result,setResult]=useState(null);
  const [attempted,setAttempted]=useState(false);
  const sourceId=quote?.sfdc_record_id||"";
  const native=ID.test(sourceId);

  async function verify(){
    if(busy||!native)return;
    setBusy(true);setResult(null);setAttempted(true);
    try{
      const q=await readLive("quote",sourceId);
      if(q.id!==sourceId||!OPP.test(q.opportunityId))
        throw Error("QUOTE_NATIVE_OPPORTUNITY_UNAVAILABLE");
      const opp=await readLive("opportunity",q.opportunityId);
      const checked=reconcileQuoteSource(quote,q,opp);
      const price=checked.status==="PASS"?verifiedSourcePrice(q,checked):
        {ok:false,code:"SOURCE_IDENTITY_NOT_VERIFIED"};
      // Quotation Fees are separate from process unit pricing. Absence of
      // this extra readback does not invalidate independently checked identity.
      let feeEvidence={status:"HOLD",code:"FEE_SOURCE_NOT_READ"};
      if(checked.status==="PASS"){
        try{
          const response=await fetch("/api/sfdc/quote-fees-local",{
            method:"POST",cache:"no-store",credentials:"omit",
            headers:{"Content-Type":"application/json","X-SFDC-Command":"1"},
            body:JSON.stringify({mode:"READ_SOURCE_QUOTE_FEES",sourceQuoteId:sourceId})
          });
          const data=await response.json();
          if(response.ok&&data.status==="PASS"&&data.nativeQuoteId===sourceId)
            feeEvidence=data;
          else feeEvidence={status:"HOLD",code:data.code||"FEE_SOURCE_UNAVAILABLE"};
        }catch{feeEvidence={status:"HOLD",code:"FEE_SOURCE_UNAVAILABLE"}}
      }
      const verified={...checked,priceEvidence:price,feeEvidence};
      setResult(verified);
      if(checked.status==="PASS")onVerified(verified);
    }catch(e){
      setResult({status:"HOLD",code:e.message||"SALESFORCE_SOURCE_UNAVAILABLE"});
    }finally{setBusy(false);}
  }

  // An authenticated source Quote is selected explicitly. Fetch its KRW
  // evidence automatically; never require the user to retype verified rates.
  useEffect(()=>{
    if(native)verify();
    // Source ID changes remount this keyed component in the pair editor.
  },[sourceId]);

  return <div className={styles.subsection} aria-label="Salesforce 원본 대조">
    <h3>기존 Salesforce 고객·KRW 단가 자동 불러오기</h3>
    <p className={styles.hint}>
      선택한 Quote의 실제 Salesforce 원본을 자동 조회합니다. 고객 ID와 공정별
      KRW 단가·Pack·AliCloud 수량이 일치할 때 샘플 단가를 자동 채웁니다.
      실제 저장은 별도 건별 승인이 필요합니다.
    </p>
    <div className={styles.actions}>
      <button type="button" onClick={verify} disabled={!native||busy}>
        {busy?"Salesforce 원본 대조 중":"기존 Quote·Oppo 고객 ID 대조"}
      </button>
      <span className={styles.state} data-ok={result?.status==="PASS"}>
        {result?.status||(!native?"NATIVE_QUOTE_ID_MISSING":"NOT_CHECKED")}
      </span>
    </div>
    {!native&&<p className={styles.warning}>
      Feishu 참조 Quote에 Salesforce 고유 ID가 없어 직접 대조할 수 없습니다.
      원본 CRM Quote를 찾아 ID를 확인해야 합니다.
    </p>}
    {attempted&&result?.status==="HOLD"&&<p className={styles.warning} role="alert">
      원본 대조 보류: {result.code}. 고객 ID 자동 상속을 허용하지 않습니다.
    </p>}
    {result?.status==="PASS"&&<div className={styles.identitySummary} role="status">
      <div><b>Account ID 확인</b><span>{result.account.name}</span>
        <small>{result.account.id}</small></div>
      <div><b>Contact ID 확인</b><span>{result.contact.name}</span>
        <small>{result.contact.id}</small></div>
      <div><b>원본 연결 Opportunity</b><span>{result.opportunityName}</span>
        <small>{result.nativeOpportunityId}</small></div>
      <div><b>별도 배송·반송 Fee</b>
        <span>{result.feeEvidence?.status==="PASS"?
          result.feeEvidence.feeCount+"개 / "+
          result.feeEvidence.totalFeeKrw.toLocaleString("ko-KR")+" KRW":
          "원본 Fee 확인 필요"}</span>
        <small>{result.feeEvidence?.status==="PASS"?
          "Product 공정 단가와 별도 관리":result.feeEvidence?.code||"FEE_NOT_CHECKED"}</small></div>
      <div><b>원본 KRW 단가</b><span>{result.priceEvidence?.ok?
        result.priceEvidence.sampleUnitKrw.toLocaleString("ko-KR")+" KRW / sample":
        "공정별 KRW 검증 보류"}</span>
        <small>{result.priceEvidence?.ok?
          "AliCloud "+result.priceEvidence.cloudUnitKrw.toLocaleString("ko-KR")+" KRW/100Gb":
          result.priceEvidence?.code||"SOURCE_PRICE_NOT_VERIFIED"}</small></div>
    </div>}
    {result?.nameReview&&<p className={styles.warning} role="status">
      기존 Opportunity와 Quote 이름이 서로 다릅니다.
      새로 생성할 Opportunity·Quote에는 아래에서 지정한 동일 이름을 사용하세요.
      원본 이름 차이는 확인 항목이며 고객 ID 불일치로 간주하지 않습니다.
    </p>}
    <p className={styles.hint}>
      판정: {result?.code||"NOT_CHECKED"} · KRW: {result?.priceEvidence?.code||"SOURCE_NOT_CHECKED"} · Salesforce 저장 없음
    </p>
  </div>;
}
