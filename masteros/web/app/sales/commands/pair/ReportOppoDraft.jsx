"use client";

import {useMemo,useState} from "react";
import {fromFeishuQuote,calculateDraft,draftDescription,draftPreflight}
  from "../../../../lib/sfdc-report-quote-draft.mjs";
import styles from "./page.module.css";

const money=value=>Number.isSafeInteger(value)?value.toLocaleString("ko-KR")+" KRW":"입력 필요";
async function searchIdentities(query){
  const r=await fetch("/api/sfdc/feishu-report-local",{
    method:"POST",cache:"no-store",credentials:"omit",
    headers:{"Content-Type":"application/json","X-SFDC-Command":"1"},
    body:JSON.stringify({mode:"IDENTITY_SEARCH",query:query.trim(),limit:20})
  });
  const obj=await r.json();
  if(!r.ok||obj.status!=="PASS")throw Error(obj.code||"IDENTITY_SOURCE_UNAVAILABLE");
  return obj.rows||[];
}
export default function ReportOppoDraft({quote,enabled=true}){
  const [draft,setDraft]=useState(()=>{
    const result=fromFeishuQuote(quote);
    return enabled&&result.ok?result.draft:null;
  });
  const [descriptionEdit,setDescriptionEdit]=useState(null);
  const [preflight,setPreflight]=useState(null);
  const [notice,setNotice]=useState("");
  const [identityTerm,setIdentityTerm]=useState("");
  const [identityRows,setIdentityRows]=useState([]);
  const [identityLoading,setIdentityLoading]=useState(false);
  const [chosenIdentity,setChosenIdentity]=useState(null);
  const amounts=useMemo(()=>draft?calculateDraft(draft):null,[draft]);
  const descriptionAuto=useMemo(()=>draft?draftDescription(draft,amounts):"",[draft,amounts]);
  const description=descriptionEdit===null?descriptionAuto:descriptionEdit;

  const edit=(key,value)=>{
    setDraft(old=>old?{...old,[key]:value}:old);
    setPreflight(null);
  };
  const editProduct=(i,key,value)=>{
    setDraft(old=>old?{...old,products:old.products.map((p,n)=>n===i?{...p,[key]:value}:p)}:old);
    setPreflight(null);
  };
  function changeMode(mode){
    setDraft(old=>old?{
      ...old,accountMode:mode,
      account:mode==="KEEP"?{...old.referenceAccount}:{id:"",name:""},
      contact:mode==="KEEP"?{...old.referenceContact}:{id:"",externalId:"",name:"",email:""}
    }:old);
    setIdentityTerm("");setIdentityRows([]);setChosenIdentity(null);setPreflight(null);
  }
  async function findIdentity(e){
    e.preventDefault();
    if(identityLoading||!identityTerm.trim())return;
    setIdentityLoading(true);setNotice("");
    try{
      setIdentityRows(await searchIdentities(identityTerm));
    }catch(err){setIdentityRows([]);setNotice(err.message||"고객 색인 조회 불가");
    }finally{setIdentityLoading(false);}
  }
  function useIdentity(row){
    setChosenIdentity(row);
    setDraft(old=>old?{
      ...old,
      account:{id:row.account_id,name:row.account_name},
      contact:{id:row.contact_id,externalId:row.contact_external_id,
        name:row.contact_name,email:row.contact_email}
    }:old);
    setPreflight(null);
    setNotice("Feishu 참고 Quote "+row.source_qid+"의 Account·Contact를 가져왔습니다. 기존 Salesforce 연결은 별도 검증이 필요합니다.");
  }
  function check(){
    if(!draft)return;
    setPreflight(draftPreflight({...draft,description}));
  }
  async function copy(which){
    if(!draft)return;
    const data=which==="json"?
      JSON.stringify({
        ...draftPreflight({...draft,description}),
        account:draft.account,contact:draft.contact,
        products:amounts?.items.map(p=>({
          projectKey:p.projectKey,productionGb:p.productionGb,
          samples:p.samples,sampleUnitKrw:p.sampleUnitKrw,
          priceReferenceUsd:p.referenceTotalUsd,
          processIds:p.processes.map(x=>x.processId)
        }))
      },null,2):description;
    try{
      await navigator.clipboard.writeText(data);
      setNotice(which==="json"?"초안 JSON 복사 완료 (저장 없음)":"Description 복사 완료 (저장 없음)");
    }catch{setNotice("클립보드 사용 불가. 텍스트 필드에서 직접 복사하세요.");}
  }
  if(!draft)return <p className={styles.warning}>
    사전 분류된 Feishu Quote 참조가 완전하지 않아 초안을 생성할 수 없습니다.
  </p>;
  return <div aria-label="Oppo Quote 참고 초안 편집">
    <div className={styles.sourceGrid}>
      <div><span>참고 Quote</span><strong>{draft.qid}</strong></div>
      <div><span>참고 Opportunity</span><strong>{draft.originalOpportunityName||"기존 프로젝트명 미확인"}</strong></div>
      <div><span>공통 템플릿</span><strong>{draft.products.length} Product</strong></div>
      <div><span>사전 분류</span><strong>{draft.referenceIndexStatus}</strong></div>
    </div>
    <div className={styles.subsection}>
      <h3>02 · Account / Contact 처리 방식</h3>
      <p className={styles.hint}>두 모드 모두 참조만 불러옵니다. 기존 Salesforce 레코드 변경·생성은 하지 않습니다.</p>
      <fieldset className={styles.accountOptions} aria-label="Account Contact 처리 방식">
        <legend>고객 연결 선택</legend>
        <label className={styles.modeOption}>
          <input type="radio" name="identity-mode" checked={draft.accountMode==="KEEP"}
            onChange={()=>changeMode("KEEP")}/>
          기존 Account·Contact 유지
        </label>
        <label className={styles.modeOption}>
          <input type="radio" name="identity-mode" checked={draft.accountMode==="CHANGE"}
            onChange={()=>changeMode("CHANGE")}/>
          Account·Contact 변경
        </label>
        {draft.accountMode==="CHANGE"&&<>
          <form className={styles.search} onSubmit={findIdentity}>
            <input aria-label="Account Contact 참조 검색" value={identityTerm}
              placeholder="한글 고객 이름 · 기관 · 이메일"
              maxLength={80} onChange={e=>setIdentityTerm(e.target.value)}/>
            <button disabled={identityLoading||!identityTerm.trim()} type="submit">
              {identityLoading?"검색 중":"기존 Account·Contact 검색"}
            </button>
          </form>
          <div className={styles.results} aria-label="Account Contact 검색 결과">
            {identityRows.map((x,i)=><button key={x.source_qid+"-"+i} type="button"
              data-selected={chosenIdentity?.source_qid===x.source_qid}
              onClick={()=>useIdentity(x)}>
              <strong>{x.account_name} · {x.contact_name}</strong>
              <small>{x.contact_email||"이메일 미확인"}</small>
              <small>{x.crm_account_verified?"Account ID 보유":"Account ID 미확인"}
                {" / "}{x.crm_contact_verified?"Contact ID 보유":"Contact ID 미확인"} · 참고 {x.source_qid}</small>
            </button>)}
          </div>
          <p className={styles.hint}>동명이인은 기관과 Contact를 함께 선택합니다. 해당 고객의 예전 견적 존재만으로 현재 CRM ID가 검증된 것은 아닙니다.</p>
        </>}
        <div className={styles.identitySummary}>
          <div><b>Account</b><span>{draft.account?.name||"미선택"}</span>
            <small>{draft.account?.id||"SFDC Account ID 미확인"}</small></div>
          <div><b>Contact</b><span>{draft.contact?.name||"미선택"}</span>
            <small>{draft.contact?.id||draft.contact?.externalId||"SFDC Contact ID 미확인"}</small>
            <small>{draft.contact?.email||""}</small></div>
        </div>
        {draft.accountMode==="CHANGE"&&<div className={styles.grid}>
          <label>변경 Account 이름
            <input aria-label="변경 Account 이름" value={draft.account?.name||""}
              onChange={e=>{edit("account",{id:"",name:e.target.value});setChosenIdentity(null);}}/>
          </label>
          <label>변경 Contact 이름
            <input aria-label="변경 Contact 이름" value={draft.contact?.name||""}
              onChange={e=>{edit("contact",{id:"",externalId:"",name:e.target.value,email:""});setChosenIdentity(null);}}/>
          </label>
        </div>}
      </fieldset>
    </div>
    <div className={styles.subsection}>
      <h3>03 · 신규 견적 구성 및 단가</h3>
      <div className={styles.grid}>
        <label>Opportunity · Quote 공통 이름
          <input aria-label="새 Oppo Quote 이름" value={draft.name}
            placeholder="Korea-기관-서비스-프로젝트"
            onChange={e=>edit("name",e.target.value)}/>
        </label>
        <label>기준일 (KST)
          <input aria-label="새 견적 날짜" type="date" value={draft.date}
            onChange={e=>edit("date",e.target.value)}/>
        </label>
      </div>
      <p className={styles.hint}>기존 공정 수량은 프로젝트 구분에 사용하지 않습니다. 생산량(Gb)과 공정 구성만 참조하고 샘플 수·단가는 새로 입력합니다.</p>
      {draft.products.map((p,i)=>{
        const item=amounts?.items[i];
        return <div className={styles.draftProduct} key={p.id}>
          <div className={styles.inlineHead}>
            <b>Product {i+1} · {p.processes.map(x=>x.name).slice(0,3).join(" + ")}</b>
            <small>기존 총액 {p.referenceTotalUsd||"—"} USD (참고)</small>
          </div>
          <p className={styles.hint}>공정+Gb 유형:
            {" "}{p.preclassified?"사전 색인됨":"참조 미확인"}
            {" · "}기존 생산량 {p.gbCandidates.length?p.gbCandidates.join(" / ")+" Gb":"미확인"}
          </p>
          <div className={styles.grid}>
            <label>생산량 (Gb)
              <input aria-label={"Product "+(i+1)+" 생산량 Gb"} inputMode="decimal"
                value={p.productionGb} placeholder="예: 6"
                onChange={e=>editProduct(i,"productionGb",e.target.value)}/>
            </label>
            <label>신규 샘플 수
              <input aria-label={"Product "+(i+1)+" 신규 샘플 수"} inputMode="numeric"
                value={p.samples} placeholder="예: 12"
                onChange={e=>editProduct(i,"samples",e.target.value)}/>
            </label>
            <label>샘플당 단가 (KRW)
              <input aria-label={"Product "+(i+1)+" 샘플당 KRW 단가"} inputMode="numeric"
                value={p.sampleUnitKrw} placeholder="예: 90000"
                onChange={e=>editProduct(i,"sampleUnitKrw",e.target.value)}/>
            </label>
          </div>
          <p className={styles.hint}>기존 공정 단가(환산 USD):
            {" "}{p.processes.map(x=>x.name+" "+(x.sourceUnitUsd||"—")+
              " USD/"+(x.dataUnit||"단위 미확인")).join(" · ")}
          </p>
          <div className={styles.totals}>
            <div><span>신규 Product 공급가액 · VAT 제외</span><strong>{money(item?.netKrw)}</strong></div>
          </div>
        </div>;
      })}
      <div className={styles.totals}>
        <div><span>공급가액 합계 · VAT 제외</span><strong>{money(amounts?.netKrw)}</strong></div>
        <div><span>VAT 10%</span><strong>{money(amounts?.vatKrw)}</strong></div>
        <div className={styles.grand}><span>VAT 포함 예상액</span><strong>{money(amounts?.grossKrw)}</strong></div>
      </div>
    </div>
    <div className={styles.subsection}>
      <h3>04 · Description 및 저장 전 검증</h3>
      <p className={styles.hint}>날짜·기관·공정·생산량·신규 수량·단가가 자동 반영됩니다. 기존 Progress Description 문구를 그대로 복제하지 않습니다.</p>
      <label className={styles.draftTextLabel}>Opportunity Description 초안 (직접 수정)
        <textarea aria-label="새 Oppo Quote Description 편집" rows={7}
          value={description} onChange={e=>{setDescriptionEdit(e.target.value);setPreflight(null);}}/>
      </label>
      <div className={styles.actions}>
        <button type="button" onClick={check}>초안 검증 (저장 없음)</button>
        <button type="button" className={styles.secondary} onClick={()=>{
          setDescriptionEdit(null);setPreflight(null);
        }}>Description 재생성</button>
        <button type="button" className={styles.secondary} onClick={()=>copy("desc")}>Description 복사</button>
        <button type="button" className={styles.secondary} onClick={()=>copy("json")}>초안 JSON 복사</button>
      </div>
      {preflight&&<div className={styles.output} role="status">
        <div className={styles.inlineHead}>
          <b>사전 검증 결과</b>
          <span className={styles.state} data-ok={preflight.status==="PREVIEW_READY"}>
            {preflight.status}
          </span>
        </div>
        {preflight.errors.length>0&&<p className={styles.warning}>
          확인 필요: {preflight.errors.join(" · ")}
        </p>}
        <p className={styles.hint}>
          이름: Opportunity = Quote · Account/Contact {draft.accountMode==="KEEP"?"기존 유지":"변경"}
          {" · "}기존 단가는 USD 참고값 · 실제 Salesforce Account/Contact 상태·KRW 가격 미검증
          {" · "}CRM 저장 금지
        </p>
      </div>}
      {notice&&<p className={styles.hint} role="status">{notice}</p>}
    </div>
  </div>;
}
