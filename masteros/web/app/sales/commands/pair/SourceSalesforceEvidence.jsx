"use client";
import {useState} from "react";
import {reconcileQuoteSource} from "../../../../lib/sfdc-source-identity.mjs";
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
      setResult(checked);
      if(checked.status==="PASS")onVerified(checked);
    }catch(e){
      setResult({status:"HOLD",code:e.message||"SALESFORCE_SOURCE_UNAVAILABLE"});
    }finally{setBusy(false);}
  }

  return <div className={styles.subsection} aria-label="Salesforce 원본 대조">
    <h3>실제 Salesforce 원본 확인 (읽기 전용)</h3>
    <p className={styles.hint}>
      Feishu의 기존 Quote ID로 Salesforce를 직접 조회하고 연결된 Opportunity와
      Account·Contact의 CRM ID를 대조합니다. 이 작업은 가격 승인 또는 저장이 아닙니다.
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
    </div>}
    {result?.nameReview&&<p className={styles.warning} role="status">
      기존 Opportunity와 Quote 이름이 서로 다릅니다.
      새로 생성할 Opportunity·Quote에는 아래에서 지정한 동일 이름을 사용하세요.
      원본 이름 차이는 확인 항목이며 고객 ID 불일치로 간주하지 않습니다.
    </p>}
    <p className={styles.hint}>
      판정: {result?.code||"NOT_CHECKED"} · Salesforce 저장 불가 · KRW 원천 단가 별도 확인 필요
    </p>
  </div>;
}
