"use client";

import {useMemo,useState} from "react";
import {fromFeishuQuote,calculateDraft,draftDescription,draftPreflight} from "../../../../lib/sfdc-report-quote-draft.mjs";
import styles from "./page.module.css";

const fmt=value=>Number.isSafeInteger(value)?value.toLocaleString("ko-KR")+" KRW":"미입력";
export default function ReportOppoDraft({quote,enabled=true}){
  const [draft,setDraft]=useState(null);
  const [descriptionEdit,setDescriptionEdit]=useState(null);
  const [check,setCheck]=useState(null);
  const [notice,setNotice]=useState("");
  const amounts=useMemo(()=>draft?calculateDraft(draft):null,[draft]);
  const descriptionAuto=useMemo(()=>draft?draftDescription(draft,amounts):"",[draft,amounts]);
  const description=descriptionEdit===null?descriptionAuto:descriptionEdit;

  const prepare=()=>{
    if(!enabled){setNotice("Feishu 원본을 선택한 경우에만 사용할 수 있습니다.");return;}
    const result=fromFeishuQuote(quote);
    if(!result.ok){setNotice(result.code);return;}
    setDraft(result.draft);
    setDescriptionEdit(null);
    setCheck(null);
    setNotice("기존 Quote는 참고 사례입니다. 공정 구성·생산량(Gb)을 확인한 후 신규 견적의 샘플 수와 단가를 입력하세요.");
  };
  const edit=(key,value)=>{
    setDraft(old=>old?{...old,[key]:value}:old);
    setCheck(null);
  };
  const editProduct=(idx,key,value)=>{
    setDraft(old=>old?{...old,products:old.products.map((p,i)=>i===idx?{...p,[key]:value}:p)}:old);
    setCheck(null);
  };
  const validate=()=>{
    if(draft)setCheck(draftPreflight({...draft,description}));
  };
  const copy=async()=>{
    try{
      await navigator.clipboard.writeText(description);
      setNotice("Description 복사 완료. Salesforce·Feishu 저장은 수행하지 않았습니다.");
    }catch{setNotice("클립보드를 사용할 수 없습니다. Description을 직접 선택해 복사하세요.");}
  };
  return <>
    <div className={styles.actions}>
      <button type="button" onClick={prepare} disabled={!enabled}>
        기존 Oppo–Quote를 참고하여 새 초안 불러오기
      </button>
    </div>
    {draft&&<section className={styles.source} aria-label="Oppo Quote 참고 초안 편집">
      <div className={styles.panelHead}>
        <span className={styles.step}>D</span>
        <div>
          <h2>신규 Oppo–Quote 초안 · 단가·Description 수정</h2>
          <p>프로젝트 구분은 공정 구성과 생산량(Gb) 기준입니다. 기존 공정별 수량은 구분이나 견적 계산에 사용하지 않습니다.</p>
        </div>
        <span className={styles.state} data-ok={check?.status==="PREVIEW_READY"}>
          {check?.status||"EDITABLE_REFERENCE"}
        </span>
      </div>
      <div className={styles.grid}>
        <label>Opportunity · Quote 공통 이름
          <input aria-label="새 Oppo Quote 이름" placeholder="Korea-기관-서비스-프로젝트"
            value={draft.name} onChange={e=>edit("name",e.target.value)}/>
        </label>
        <label>기준일
          <input aria-label="새 견적 날짜" type="date" value={draft.date}
            onChange={e=>edit("date",e.target.value)}/>
        </label>
      </div>
      <p className={styles.hint}>
        참고 Quote {draft.qid} · QQ 메일 수신 {draft.sourceReceivedKst||"미확인"}
        · 기존 Product 가격 USD는 비교 근거일 뿐 KRW/샘플 단가는 아닙니다.
      </p>
      {draft.products.map((p,index)=>{
        const item=amounts?.items[index];
        return <div className={styles.draftProduct} key={p.id}>
          <div className={styles.inlineHead}>
            <b>Product {index+1} · {p.processes.slice(0,3).map(x=>x.name).join(" + ")}</b>
            <small>기존 Product 합계 {p.referenceTotalUsd||"미확인"} USD (참고)</small>
          </div>
          <p className={styles.hint}>
            기존 생산량(Gb): {p.gbCandidates.length?p.gbCandidates.join(" / "):"확인 필요"}.
            공정 구성과 Gb가 같으면 프로젝트 템플릿을 재사용하며 기존 수량은 무시합니다.
          </p>
          <div className={styles.grid}>
            <label>생산량 (Gb) · 프로젝트 구분
              <input aria-label={"Product "+(index+1)+" 생산량 Gb"}
                inputMode="decimal" placeholder="예: 6" value={p.productionGb}
                onChange={e=>editProduct(index,"productionGb",e.target.value)}/>
            </label>
            <label>새 견적 샘플 수
              <input aria-label={"Product "+(index+1)+" 신규 샘플 수"}
                inputMode="numeric" placeholder="신규 수량" value={p.samples}
                onChange={e=>editProduct(index,"samples",e.target.value)}/>
            </label>
            <label>샘플당 단가 (KRW)
              <input aria-label={"Product "+(index+1)+" 샘플당 KRW 단가"}
                inputMode="numeric" placeholder="신규 단가" value={p.sampleUnitKrw}
                onChange={e=>editProduct(index,"sampleUnitKrw",e.target.value)}/>
            </label>
          </div>
          <p className={styles.hint}>기존 공정 단가 참고:
            {" "+p.processes.map(x=>x.name+" "+(x.sourceUnitUsd||"—")+" USD/"+(x.dataUnit||"단위 미확인")).join(" · ")}
          </p>
          <div className={styles.totals}>
            <div><span>신규 Product 공급가액 (VAT 제외)</span><strong>{fmt(item?.netKrw)}</strong></div>
          </div>
        </div>;
      })}
      <div className={styles.totals}>
        <div><span>공급가액 합계 (VAT 제외)</span><strong>{fmt(amounts?.netKrw)}</strong></div>
        <div><span>VAT 10%</span><strong>{fmt(amounts?.vatKrw)}</strong></div>
        <div className={styles.grand}><span>VAT 포함 예상 합계</span><strong>{fmt(amounts?.grossKrw)}</strong></div>
      </div>
      <label className={styles.draftTextLabel}>Description · 자동 작성 후 직접 수정
        <textarea aria-label="새 Oppo Quote Description 편집" rows={7}
          value={description} onChange={e=>{setDescriptionEdit(e.target.value);setCheck(null);}}/>
      </label>
      <div className={styles.actions}>
        <button type="button" onClick={validate}>초안 검증 (저장 없음)</button>
        <button type="button" className={styles.secondary} onClick={()=>{
          setDescriptionEdit(null);setCheck(null);
        }}>현재 입력값으로 Description 재생성</button>
        <button type="button" className={styles.secondary} onClick={copy}>Description 복사</button>
      </div>
      {check&&<div className={styles.source} role="status">
        <b>초안 검증 · {check.status}</b>
        {check.errors.length>0&&<p className={styles.warning}>{check.errors.join(" · ")}</p>}
        <p className={styles.hint}>
          Oppo와 Quote 이름 동일 · 원본 가격은 USD 참고값 · 고객/Contact와 KRW 단가 원본 미검증 ·
          Salesforce 또는 Feishu 저장 0건
        </p>
      </div>}
    </section>}
    {notice&&<p className={styles.hint} role="status">{notice}</p>}
  </>;
}
