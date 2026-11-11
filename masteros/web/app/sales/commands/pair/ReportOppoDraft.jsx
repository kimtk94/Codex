"use client";

import {useMemo,useState} from "react";
import {fromFeishuQuote,calculateDraft,opportunityUnitPriceSummary,draftDescription,draftPreflight,descriptionBasis,descriptionReview,draftChanges}
  from "../../../../lib/sfdc-report-quote-draft.mjs";
import styles from "./page.module.css";
import SourceSalesforceEvidence from "./SourceSalesforceEvidence";
import {applyVerifiedSource} from "../../../../lib/sfdc-source-identity.mjs";
import {REGION_OPTIONS,regionByCode} from "../../../../lib/sfdc-amplicon-regions.mjs";
import IdentityPicker from "../IdentityPicker";
import {reportProcessComposition} from "../../../../lib/sfdc-quote-process-review.mjs";

const money=value=>Number.isSafeInteger(value)?value.toLocaleString("ko-KR")+" KRW":"입력 필요";
export default function ReportOppoDraft({quote,enabled=true}){
  const [draft,setDraft]=useState(()=>{
    const result=fromFeishuQuote(quote);
    return enabled&&result.ok?result.draft:null;
  });
  const [descriptionEdit,setDescriptionEdit]=useState(null);
  const [descriptionEditBasis,setDescriptionEditBasis]=useState(null);
  const [preflight,setPreflight]=useState(null);
  const [notice,setNotice]=useState("");
  const [regionToAdd,setRegionToAdd]=useState({});
  const amounts=useMemo(()=>draft?calculateDraft(draft):null,[draft]);
  const oppUnits=useMemo(()=>opportunityUnitPriceSummary(amounts),[amounts]);
  const changes=useMemo(()=>draft?draftChanges(draft):[],[draft]);
  const descriptionAuto=useMemo(()=>draft?draftDescription(draft,amounts):"",[draft,amounts]);
  const description=descriptionEdit===null?descriptionAuto:descriptionEdit;
  const isManualDescription=descriptionEdit!==null;
  const descriptionCheck=useMemo(()=>draft?descriptionReview(
    draft,description,isManualDescription?descriptionEditBasis:null):null,
    [draft,description,isManualDescription,descriptionEditBasis]);
  const descriptionPayload=()=>({...draft,description,
    descriptionManualBasis:isManualDescription?descriptionEditBasis:null});

  const onSourceVerified=(result)=>{
    setDraft(current=>applyVerifiedSource(current,result));
    setPreflight(null);
    setNotice("Salesforce 원본 고객 ID 대조 완료 · 가격과 저장은 별도 검증 필요");
  };

  const edit=(key,value)=>{
    setDraft(old=>old?{...old,[key]:value}:old);
    setPreflight(null);
  };
  const editProduct=(i,key,value)=>{
    setDraft(old=>old?{...old,products:old.products.map((p,n)=>n===i?{...p,[key]:value}:p)}:old);
    setPreflight(null);
  };

  function updateAmplicon(i,fn){
    setDraft(old=>old?{...old,
      products:old.products.map((p,n)=>n===i?
        {...p,amplicon:fn(p.amplicon||{
          enabled:false,regions:[],referenceStatus:"USER_SELECTED"
        })}:p)
    }:old);
    setPreflight(null);
  }
  function addRegion(i,code){
    const candidate=regionByCode(code);
    if(!candidate)return;
    updateAmplicon(i,old=>{
      if(old.regions.some(x=>x.code===candidate.code))return old;
      return {...old,enabled:true,regions:[...old.regions,candidate]};
    });
    setRegionToAdd(old=>({...old,[i]:""}));
  }
  function removeRegion(i,code){
    updateAmplicon(i,old=>({...old,
      regions:old.regions.filter(x=>x.code!==code)}));
  }
  function editRegionPrice(i,code,value){
    updateAmplicon(i,old=>({...old,
      regions:old.regions.map(x=>x.code===code?{...x,unitKrw:value}:x)}));
  }
  function changeMode(mode){
    setDraft(old=>old?{
      ...old,accountMode:mode,
      account:mode==="KEEP"?{...old.referenceAccount}:{id:"",name:""},
      contact:mode==="KEEP"?{...old.referenceContact}:{id:"",externalId:"",name:"",email:""}
    }:old);
    setPreflight(null);
  }
  function chooseAccount(account){
    if(!account?.name){
      setDraft(old=>old?{...old,account:{id:"",name:""},
        contact:{id:"",externalId:"",name:"",email:""}}:old);
      setPreflight(null);
      return;
    }
    setDraft(old=>old?{...old,
      account:{id:account.id||"",name:account.name},
      contact:{id:"",externalId:"",name:"",email:""}
    }:old);
    setPreflight(null);
    setNotice("기관 선택 완료 · 같은 기관의 고객을 검색해 선택하세요.");
  }
  function chooseContact(pair){
    if(!pair?.ok||!pair.account?.name||!pair.contact?.name)return;
    setDraft(old=>old?{...old,
      account:pair.account,contact:pair.contact
    }:old);
    setPreflight(null);
    setNotice("고객 및 소속 기관을 함께 선택했습니다. Salesforce 현재 연결 상태는 저장 전 재검증이 필요합니다.");
  }
  function check(){
    if(!draft)return;
    setPreflight(draftPreflight(descriptionPayload()));
  }
  async function copy(which){
    if(!draft)return;
    const data=which==="json"?
      JSON.stringify({
        ...draftPreflight(descriptionPayload()),
        account:draft.account,contact:draft.contact,
        products:amounts?.items.map(p=>({
          projectKey:p.projectKey,productionGb:p.productionGb,
          samples:p.samples,sampleUnitKrw:p.sampleUnitKrw,
          priceReferenceUsd:p.referenceTotalUsd,
          sourceQuoteProductId:p.id,
          ampliconRegions:p.amplicon?.enabled?p.regionLines:[],
          effectiveServiceQuantity:p.serviceQuantity,
          processIds:p.processes.map(x=>x.processId)
        })),
        editedFields:changes,
        sourceRecordIsReferenceOnly:true
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
    <SourceSalesforceEvidence quote={quote} onVerified={onSourceVerified}/>
    <div className={styles.sourceGrid}>
      <div><span>참고 Quote</span><strong>{draft.qid}</strong></div>
      <div><span>참고 Opportunity</span><strong>{draft.originalOpportunityName||"기존 프로젝트명 미확인"}</strong></div>
      <div><span>공통 템플릿</span><strong>{draft.products.length} Product</strong></div>
      <div><span>사전 분류</span><strong>{draft.referenceIndexStatus}</strong></div>
      <div><span>원본 대비 변경</span><strong>{changes.length}개 항목</strong></div>
    </div>
    <p className={styles.hint}>기존 Opportunity/Quote의 가능한 값을 먼저 채웁니다. 바꾸는 필드만 수정하세요.
      계정·Contact·Region·공정은 원본을 참고하며, 검증된 KRW 단가가 없는 경우에만 금액 확인이 필요합니다.</p>
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
        {draft.accountMode==="CHANGE"&&<IdentityPicker
          account={draft.account} contact={draft.contact}
          onAccount={chooseAccount} onContact={chooseContact}/>}
        <div className={styles.identitySummary}>
          <div><b>Account</b><span>{draft.account?.name||"미선택"}</span>
            <small>{draft.account?.id||"SFDC Account ID 미확인"}</small></div>
          <div><b>Contact</b><span>{draft.contact?.name||"미선택"}</span>
            <small>{draft.contact?.id||draft.contact?.externalId||"SFDC Contact ID 미확인"}</small>
            <small>{draft.contact?.email||""}</small></div>
        </div>

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
        <label>Opportunity Close Date · 오늘부터 한 달 뒤
          <input aria-label="신규 Opportunity Close Date" type="date"
            value={draft.closeDate||""} onChange={e=>edit("closeDate",e.target.value)}/>
        </label>
      </div>
      <p className={styles.hint}>샘플이 곧 입고될 예정이며 아직 입고·QC·PO는 확인되지 않았습니다.
        Opportunity/Quote는 동일 이름, Coop TS Yoo Ji In, Pack 수량은 샘플 수 기준으로 검토합니다.</p>
      <p className={styles.hint}>기존 서비스·Product·Region 값이 확인되면 그대로 가져옵니다.
        변경된 부분만 수정하고, 기존 공정별 수량을 생물학적 샘플 수로 오해하지 않습니다.</p>
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
            <label>서비스명 (기존 견적 참고 · 수정 가능)
              <input aria-label={"Product "+(i+1)+" 서비스명"} value={p.serviceLabel||""}
                placeholder="예: mRNA-Seq" onChange={e=>editProduct(i,"serviceLabel",e.target.value)}/>
            </label>
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
            <label>{p.amplicon?.enabled?"공통 Region당 단가 (KRW/샘플/Region)":"샘플당 단가 (KRW)"}
              <input aria-label={"Product "+(i+1)+" 샘플당 KRW 단가"} inputMode="numeric"
                value={p.sampleUnitKrw} placeholder="예: 90000"
                onChange={e=>editProduct(i,"sampleUnitKrw",e.target.value)}/>
            </label>
          </div>
          {(p.amplicon?.enabled||/amplicon|16s|18s|archaeal|its[12]/i.test(
              p.serviceLabel+" "+draft.originalOpportunityName))&&
            <fieldset className={styles.accountOptions} aria-label={"Product "+(i+1)+" Amplicon Region 설정"}>
              <legend>Amplicon Region · 동일 샘플에 Region별 서비스 적용</legend>
              <label className={styles.modeOption}>
                <input aria-label={"Product "+(i+1)+" Amplicon Region 활성화"}
                  type="checkbox" checked={Boolean(p.amplicon?.enabled)}
                  onChange={e=>updateAmplicon(i,old=>({...old,enabled:e.target.checked}))}/>
                Region별 견적 사용
              </label>
              {p.amplicon?.enabled&&<>
                <p className={styles.hint}>원본 Region 근거: {p.amplicon.referenceStatus}.
                  {" "}생물학적 샘플 {p.samples||"미확인"}개 ×
                  {" "}{p.amplicon.regions.length} Region =
                  {" "}{item?.serviceQuantity??"확인 필요"} 서비스 건.
                  같은 샘플을 별도 Region으로 분석하며 샘플 수는 중복 증가하지 않습니다.</p>
                <div className={styles.grid}>
                  <label>Region 추가
                    <select aria-label={"Product "+(i+1)+" Region 선택"}
                      value={regionToAdd[i]||""}
                      onChange={e=>{
                        setRegionToAdd(old=>({...old,[i]:e.target.value}));
                        addRegion(i,e.target.value);
                      }}>
                      <option value="">선택해 추가</option>
                      {REGION_OPTIONS.filter(r=>!p.amplicon.regions.some(
                        x=>x.code===r.code)).map(r=>
                          <option key={r.code} value={r.code}>{r.label}</option>)}
                    </select>
                  </label>
                </div>
                {p.amplicon.regions.map((r,j)=><div key={r.code}
                  className={styles.inlineHead}>
                  <b>Region {j+1}. {r.label}</b>
                  <label>Region별 단가 (KRW/샘플 · 비우면 공통 단가)
                    <input aria-label={"Product "+(i+1)+" "+r.label+" Region 단가"}
                      inputMode="numeric" value={r.unitKrw||""}
                      placeholder="공통 단가 적용"
                      onChange={e=>editRegionPrice(i,r.code,e.target.value)}/>
                  </label>
                  <button className={styles.secondary} type="button"
                    onClick={()=>removeRegion(i,r.code)}>이 Region 제외</button>
                </div>)}
              </>}
            </fieldset>}
          <div className={styles.output} data-testid={"report-process-inclusions-"+i}>
            <strong>기존 Quote Report 포함 공정 · 샘플당 금액 구성</strong>
            <p className={styles.hint}>참고 USD는 환산값입니다. 검증된 KRW 공정 단가가
              아니므로 신규 KRW 단가로 자동 대체하지 않습니다.</p>
            <div className={styles.tableScroll}><table><thead><tr>
              <th>포함 공정</th><th>원본 단위</th><th>참고 USD 단가</th><th>신규 수량 기준</th>
            </tr></thead><tbody>{reportProcessComposition(p).rows.map((row,j)=><tr key={j}>
              <td>{row.name}</td><td>{row.dataUnit||"미확인"}</td>
              <td>{row.sourceUnitUsd||"확인 필요"}</td>
              <td>{row.quantityBasis==="100_GB"?"100 Gb당 1":
                row.quantityBasis==="DATA_SIZE"?"Gb 기준":"샘플/Pack 확인"}</td>
            </tr>)}</tbody></table></div>
            <p className={styles.hint}>Pack 계획: 생물학적 샘플
              {" "}{p.samples||"미확인"}개 → Pack 수량
              {" "}{reportProcessComposition(p).pack.quantity??"확인 필요"}개.
              원본 Pack No./Product 공정 할당 재확인 필요.</p>
          </div>
          <div className={styles.totals}>
            <div><span>Oppo 샘플당 단가 · VAT 제외</span>
              <strong>{money(oppUnits.ok?oppUnits.products[i]?.unitPriceNetKrw:null)}</strong></div>
            {p.amplicon?.enabled&&<p className={styles.hint}>위 단가는 Region별 서비스를 모두 합친 생물학적 샘플 1개 기준 금액입니다. Region별 개별 단가와 구분합니다.</p>}
            <div><span>신규 Product 공급가액 · VAT 제외</span><strong>{money(item?.netKrw)}</strong></div>
            {p.amplicon?.enabled&&<div>
              <span>Region 서비스 횟수 · 생물학적 샘플과 별도</span>
              <strong>{item?.serviceQuantity??"확인 필요"}건</strong>
            </div>}
          </div>
        </div>;
      })}
      <div className={styles.totals} data-testid="oppo-price-summary">
        <div><span>Opportunity 샘플당 단가 · VAT 제외</span>
          <strong>{oppUnits.ok&&oppUnits.singleProduct?
            money(oppUnits.overallPerSampleNetKrw):
            oppUnits.ok?"제품별 단가 별도 표시":"단가 확인 필요"}</strong></div>
        <div><span>공급가액 합계 · VAT 제외</span><strong>{money(amounts?.netKrw)}</strong></div>
        <div><span>VAT 10%</span><strong>{money(amounts?.vatKrw)}</strong></div>
        <div className={styles.grand}><span>VAT 포함 예상액</span><strong>{money(amounts?.grossKrw)}</strong></div>
      </div>
    </div>
    <div className={styles.subsection}>
      <h3>04 · Progress Description 및 저장 전 검증</h3>
      {changes.length>0&&<p className={styles.hint}>원본 대비 변경 항목 {changes.length}개:
        {" "}{changes.slice(0,12).map(x=>x.field).join(", ")}
        {changes.length>12?" 외 "+(changes.length-12)+"개":""}</p>}
      <p className={styles.hint}>실제 Opportunity에서 쓰던 짧은 양식: 0407 Quote Issued mRNA-Seq 12 samples * 250,000KRW. 새 초안은 발송 전이므로 Quote Draft로 표시합니다.</p>
      <p className={styles.hint}>MMDD · 상태 · 서비스 · Gb(해당 시) · 수량 · 단가만 표시합니다. 직접 수정하면 문구를 잠그며, 이후 값이 바뀌면 재검증이 필요합니다.</p>
      <div className={styles.inlineHead}>
        <b>현재 편집 상태</b>
        <span className={styles.state} data-ok={!descriptionCheck?.stale&&descriptionCheck?.complete}>
          {descriptionCheck?.stale?"수동 잠금 · 현재 입력값과 불일치":
           isManualDescription?"수동 잠금 · 검증 필요":"자동 연동 · 기존 한 줄 양식"}
        </span>
      </div>
      <label className={styles.draftTextLabel}>Opportunity Progress Description (직접 수정 가능)
        <textarea aria-label="새 Oppo Quote Description 편집" rows={7}
          value={description} onChange={e=>{
            setDescriptionEdit(e.target.value);
            setDescriptionEditBasis(descriptionBasis(draft));
            setPreflight(null);
          }}/>
      </label>
      {descriptionCheck?.stale&&<p className={styles.warning} role="alert">
        가격·수량·Gb·고객·날짜가 변경됐지만 수동 Description은 유지됐습니다. 내용 확인 후 직접 수정하거나 재생성해야 검증할 수 있습니다.
      </p>}
      {!descriptionCheck?.complete&&<p className={styles.warning} role="status">
        현재 Description에 필수 값이 부족합니다. 날짜·Gb·샘플 수·단가 표기를 확인하세요.
      </p>}
      <div className={styles.actions}>
        <button type="button" onClick={check}>초안 검증 (저장 없음)</button>
        <button type="button" className={styles.secondary} onClick={()=>{
          setDescriptionEdit(null);setDescriptionEditBasis(null);setPreflight(null);
        }}>현재 입력값으로 Description 재생성 (잠금 해제)</button>
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
          {" · "}Close Date {draft.closeDate} · 샘플 입고 예정 · Pack 동일 샘플 수
          {" · "}기존 단가는 USD 참고값 · 실제 Salesforce Account/Contact 상태·KRW 가격 미검증
          {" · "}CRM 저장 금지
        </p>
      </div>}
      {notice&&<p className={styles.hint} role="status">{notice}</p>}
    </div>
  </div>;
}
