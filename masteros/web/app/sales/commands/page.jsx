"use client";

import {useCallback,useEffect,useMemo,useRef,useState} from "react";
import Link from "next/link";
import {alicloudUnits,freshProgress,validateRequest} from "../../../lib/sfdc-commands.mjs";
import {recordToDraft,recordSelectionSummary} from "../../../lib/sfdc-record-picker.mjs";
import {buildPairDraft,derivePairPrice} from "../../../lib/sfdc-paired-clone.mjs";
import styles from "./page.module.css";

const common={confirmSave:false,noDuplicateConfirmed:false};
const initial={
  lead_convert:{leadId:"",accountName:"",koreanName:"",englishName:""},
  opportunity_create:{referenceOpportunityId:"",accountId:"",contactId:"",
    accountName:"",contactName:"",opportunityName:"",samples:1,
    amountKrw:0,closeDate:"",progressDescription:"",service:"",dataSize:1,unit:"Gb",referenceAmea:""},
  quote_create:{opportunityId:"",sourceQuoteId:"",quoteName:"",
    accountName:"",contactName:"",productCategory:"",productName:"",
    samples:1,dataSize:1,unit:"Gb",processNames:""},
};
const tabs=[
  {id:"lead_convert",name:"Lead Convert",caption:"기존 Account → Contact · Oppo 생성 안 함"},
  {id:"opportunity_create",name:"Opportunity 생성",caption:"기존 Oppo 참조 · 새 Progress Description"},
  {id:"quote_create",name:"Quote 생성",caption:"기존 제품만 · 가격 검증 우선"},
];
function Field({label,value,onChange,required=true,type="text",step,placeholder}){
  return <label className={styles.field}><span>{label}</span>
    <input type={type} value={value??""} onChange={e=>onChange(type==="number"?Number(e.target.value):e.target.value)}
      required={required} step={step} placeholder={placeholder||""}/></label>;
}
function Flag({label,state}){
  const p=String(state||"BLOCK");
  const color=["PASS","PREFLIGHT_PASS","SNAPSHOT_READY"].includes(p)?"ok":p.includes("BLOCK")?"bad":"warn";
  return <div className={styles.flag}><span>{label}</span><b data-tone={color}>{p}</b></div>;
}
export default function SfdcCommandCenter(){
  const [tab,setTab]=useState("lead_convert");
  const [forms,setForms]=useState(()=>structuredClone(initial));
  const [health,setHealth]=useState(null);
  const [healthBusy,setHealthBusy]=useState(false);
  const [busy,setBusy]=useState(false);
  const [result,setResult]=useState(null);
  const [preflight,setPreflight]=useState("");
  const [confirmed,setConfirmed]=useState(false);
  const [dedup,setDedup]=useState(false);
  const [catalogue,setCatalogue]=useState({lead:[],opportunity:[],quote:[]});
  const [query,setQuery]=useState("");
  const [catalogueStatus,setCatalogueStatus]=useState("NOT_CHECKED");
  const [catalogueBusy,setCatalogueBusy]=useState(false);
  const pickerSequence=useRef(0);
  const [loadingDetail,setLoadingDetail]=useState(false);
  const [selectedRecord,setSelectedRecord]=useState(null);
  const [originalDraft,setOriginalDraft]=useState(null);
  const [advanced,setAdvanced]=useState(false);
  const [pairedQuote,setPairedQuote]=useState(null);
  const [pairStatus,setPairStatus]=useState("NOT_CHECKED");
  const resource=tab==="lead_convert"?"lead":tab==="opportunity_create"?"opportunity":"quote";
  const form=forms[tab];
  const signature=useMemo(()=>JSON.stringify({tab,...form}),[tab,form]);
  const ready=signature===preflight && selectedRecord?.resource===resource;
  const update=(key,value)=>{
    setForms(prev=>{
      const next={...prev[tab],[key]:value};
      if(tab==="opportunity_create"&&pairedQuote&&["samples","dataSize"].includes(key)){
        const price=derivePairPrice(pairedQuote,next.samples,next.dataSize);
        next.amountKrw=price.ok?price.netKrw:0;
      }
      return {...prev,[tab]:next};
    });
    setResult(null);setPreflight("");
  };
  const loadHealth=useCallback(async()=>{
    setHealthBusy(true);
    try{
      const r=await fetch("/api/sfdc/commands-local",{
        cache:"no-store",headers:{"X-SFDC-Command":"1"},credentials:"omit"
      });
      if(!r.ok)throw Error("LOCAL_HEALTH_UNAVAILABLE");
      setHealth(await r.json());
    }catch{setHealth({status:"SOURCE_UNAVAILABLE"});}
    finally{setHealthBusy(false);}
  },[]);
  useEffect(()=>{loadHealth();},[loadHealth]);
  const browse=useCallback(async(kind,search="")=>{
    const seq=++pickerSequence.current;
    setCatalogueBusy(true);
    setCatalogueStatus("LOADING");
    setCatalogue(prev=>({...prev,[kind]:[]}));
    setSelectedRecord(null);
    setOriginalDraft(null);
    setPreflight("");setPairedQuote(null);setPairStatus("NOT_CHECKED");
    try{
      let data=null;
      for(let attempt=0;attempt<9;attempt++){
        if(seq!==pickerSequence.current)return;
        const response=await fetch("/api/sfdc/records-local",{
          method:"POST",headers:{"Content-Type":"application/json","X-SFDC-Command":"1"},
          credentials:"omit",cache:"no-store",
          body:JSON.stringify({resource:kind,mode:"list",query:search})
        });
        data=await response.json();
        if(response.status!==409||data.code!=="PICKER_BUSY")break;
        await new Promise(resolve=>setTimeout(resolve,1500));
      }
      if(seq!==pickerSequence.current)return;
      if(data?.status!=="PASS"||!Array.isArray(data.records))
        throw new Error(data?.code||"SOURCE_UNAVAILABLE");
      setCatalogue(prev=>({...prev,[kind]:data.records}));
      setCatalogueStatus("PASS");
    }catch(e){
      if(seq!==pickerSequence.current)return;
      setCatalogue(prev=>({...prev,[kind]:[]}));
      setCatalogueStatus(e?.message||"SOURCE_UNAVAILABLE");
    }finally{
      if(seq===pickerSequence.current)setCatalogueBusy(false);
    }
  },[]);
  useEffect(()=>{
    setQuery("");setSelectedRecord(null);setOriginalDraft(null);setAdvanced(false);
    setPairedQuote(null);setPairStatus("NOT_CHECKED");
    setResult(null);setPreflight("");
    browse(resource,"");
  },[resource,browse]);
  async function chooseRecord(id){
    if(loadingDetail||busy)return;
    setLoadingDetail(true);setResult(null);setPreflight("");
    setPairedQuote(null);setPairStatus("NOT_CHECKED");
    try{
      const response=await fetch("/api/sfdc/records-local",{
        method:"POST",headers:{"Content-Type":"application/json","X-SFDC-Command":"1"},
        credentials:"omit",cache:"no-store",
        body:JSON.stringify({resource,mode:"detail",recordId:id})
      });
      const item=await response.json();
      if(!response.ok||item.status!=="PASS"||item.id!==id)throw Error(item.code||"DETAIL_UNAVAILABLE");
      const next=recordToDraft(resource,item,initial[tab]);
      if(!next)throw Error("RECORD_MISMATCH");
      setForms(prev=>({...prev,[tab]:next}));
      setSelectedRecord(item);
      setOriginalDraft(next);
      setDedup(false);setConfirmed(false);
    }catch(e){
      setSelectedRecord(null);setOriginalDraft(null);
      setResult({status:"BLOCK",code:e?.message||"DETAIL_UNAVAILABLE"});
    }finally{setLoadingDetail(false);}
  }
  const pairProjection=useMemo(()=>{
    if(!pairedQuote||tab!=="opportunity_create")return null;
    return derivePairPrice(pairedQuote,form.samples,form.dataSize);
  },[pairedQuote,form.samples,form.dataSize,tab]);
  async function loadLinkedQuote(){
    if(tab!=="opportunity_create"||!selectedRecord?.id||busy||loadingDetail)return;
    setLoadingDetail(true);setPreflight("");setPairStatus("LOADING");
    try{
      const r=await fetch("/api/sfdc/records-local",{
        method:"POST",cache:"no-store",credentials:"omit",
        headers:{"Content-Type":"application/json","X-SFDC-Command":"1"},
        body:JSON.stringify({resource:"opportunity",mode:"bundle",recordId:selectedRecord.id})
      });
      const bundle=await r.json();
      if(!r.ok||bundle.status!=="PASS")throw Error(bundle.code||"QUOTE_LINK_UNAVAILABLE");
      const draft=buildPairDraft(bundle,form);
      if(!draft.ok)throw Error(draft.code);
      if(draft.quote.opportunityId!==selectedRecord.id)throw Error("WRONG_PARENT_OPPORTUNITY");
      setPairedQuote(draft.quote);setPairStatus("PASS");
      setForms(prev=>({...prev,[tab]:{...draft.form,closeDate:form.closeDate}}));
      setResult(null);
    }catch(e){
      setPairedQuote(null);setPairStatus("BLOCK");
      setResult({status:"BLOCK",code:e?.message||"SOURCE_PRICE_UNVERIFIED"});
    }finally{setLoadingDetail(false);}
  }
  const changedFields=useMemo(()=>{
    if(!originalDraft)return [];
    return Object.keys(originalDraft).filter(k=>form[k]!==originalDraft[k] &&
      !["progressDescription","referenceAmea"].includes(k));
  },[form,originalDraft]);
  function switchTab(next){
    setTab(next);setResult(null);setPreflight("");setConfirmed(false);setDedup(false);
  }
  async function run(mode){
    if(busy||catalogueBusy||loadingDetail)return;
    if(!selectedRecord || selectedRecord.resource!==resource){
      setResult({status:"BLOCK",code:"SELECT_EXISTING_RECORD_FIRST"});return;
    }
    const sourceKey=resource==="lead"?"leadId":resource==="opportunity"?"referenceOpportunityId":"sourceQuoteId";
    if(form[sourceKey]!==selectedRecord.id){
      setResult({status:"BLOCK",code:"SOURCE_ID_CHANGED"});return;
    }
    const req={...form,action:tab,mode,confirmSave:mode==="save"&&confirmed,
      noDuplicateConfirmed:mode==="save"&&dedup};
    if(tab==="opportunity_create"&&pairedQuote&&
       (!pairProjection?.ok||form.amountKrw!==pairProjection.netKrw)){
      setResult({status:"BLOCK",code:"CLOUD_PRICE_MISMATCH"});return;
    }
    if(mode==="save"&&!ready){
      setResult({status:"BLOCK",code:"PREFLIGHT_REQUIRED"});return;
    }
    const validity=validateRequest(req);
    if(!validity.ok){setResult({status:"BLOCK",code:validity.code});return;}
    setBusy(true);
    try{
      const response=await fetch("/api/sfdc/commands-local",{
        method:"POST",headers:{"Content-Type":"application/json","X-SFDC-Command":"1"},
        cache:"no-store",credentials:"omit",body:JSON.stringify(req)
      });
      const data=await response.json();
      setResult(data);
      if(mode==="check")setPreflight(data.status==="PREFLIGHT_PASS"?signature:"");
      if(mode==="save"){setPreflight("");setConfirmed(false);setDedup(false);loadHealth();}
    }catch{
      setResult({status:"BLOCK",code:"LOCAL_REQUEST_FAILED"});
    }finally{setBusy(false);}
  }
  function regenerate(){
    try{
      const description=freshProgress({
        accountName:form.accountName,contactName:form.contactName,
        service:form.service,samples:form.samples,dataSize:form.dataSize,
        unit:form.unit,referenceAmea:form.referenceAmea
      });
      update("progressDescription",description);
    }catch{setResult({status:"BLOCK",code:"PROGRESS_FIELDS_INCOMPLETE"});}
  }
  const totalGb=tab==="opportunity_create"&&form.unit==="Gb"?
    form.samples*form.dataSize:null;
  return <main className={styles.wrap}>
    <header className={styles.top}>
      <div><p className={styles.eyebrow}>SALES AUTOMATION</p>
        <h1>업무 실행</h1><p>입력 → 검증 → 실행 → 결과 확인</p></div>
      <div className={styles.navigation}>
        <Link href="/sales/projects">프로젝트</Link>
        <button type="button" onClick={loadHealth} disabled={healthBusy}>{healthBusy?"점검 중":"Health Check"}</button>
      </div>
    </header>
    <section className={styles.health}>
      <div className={styles.sectionHead}><h2>Health Check</h2><span>{health?.status||"점검 전"}</span></div>
      <div className={styles.healthGrid}>
        <Flag label="Lead 접속" state={health?.lead_view}/>
        <Flag label="Oppo 접속" state={health?.opportunity_view}/>
        <Flag label="Quote 접속" state={health?.quote_view}/>
        <Flag label="Contact 조회" state={health?.contact_lookup}/>
        <Flag label="Lead Convert" state={health?.lead_convert}/>
        <Flag label="Oppo 생성" state={health?.opportunity_create}/>
        <Flag label="Quote 저장" state={health?.quote_create}/>
      </div>
    </section>
    <section className={styles.commands}>
      <div className={styles.tabbar}>
        {tabs.map(x=><button type="button" key={x.id} data-active={tab===x.id}
          onClick={()=>switchTab(x.id)}>
          <b>{x.name}</b><small>{x.caption}</small></button>)}
      </div>
      <section className={styles.picker} aria-label="기존 Salesforce 레코드 선택">
        <div className={styles.pickerTop}>
          <div><h2>1. 기존 {resource==="lead"?"Lead":resource==="opportunity"?"Opportunity":"Quote"} 불러오기</h2>
            <p>현재 Salesforce 목록 · 검색 후 선택</p></div>
          <span data-status={catalogueStatus}>{catalogueStatus}</span>
        </div>
        <form className={styles.pickerSearch} onSubmit={e=>{e.preventDefault();browse(resource,query)}}>
          <input aria-label="기존 레코드 검색" placeholder="이름 · 기관 · AMEA 검색"
            value={query} onChange={e=>setQuery(e.target.value)}/>
          <button type="submit" disabled={catalogueBusy||loadingDetail}>
            {catalogueBusy?"조회 중":"검색"}
          </button>
          <button type="button" disabled={catalogueBusy||loadingDetail}
            onClick={()=>browse(resource,query)}>새로고침</button>
        </form>
        <div className={styles.recordList}>
          {(catalogue[resource]||[]).map(item=>
            <button type="button" key={item.id} className={styles.recordItem}
              data-selected={selectedRecord?.id===item.id}
              onClick={()=>chooseRecord(item.id)} disabled={catalogueBusy||loadingDetail||busy}>
              <b>{item.name}</b>
              <span>{[item.institution,item.contact,item.quotationNumber,item.status].filter(Boolean).join(" · ")}</span>
            </button>)}
          {!catalogueBusy && (catalogue[resource]||[]).length===0 &&
            <p className={styles.noRecords}>검색 결과가 없습니다. Salesforce 목록 필터를 확인하세요.</p>}
        </div>
        {selectedRecord&&<div className={styles.selectedInfo}>
          <strong>선택: {selectedRecord.name||selectedRecord.id}</strong>
          <span>{selectedRecord.id} · 원본 선택 완료</span>
          <span>{changedFields.length}개 항목 수정됨</span>
          <p>{recordSelectionSummary(selectedRecord)?.warnings.join(" · ")}</p>
        </div>}
      </section>
      <div className={styles.content}>
        <div className={styles.fields}>
          {tab==="lead_convert"&&<>
            <p className={styles.hint}>Lead 목록에서 선택하면 이름·기관이 자동 입력됩니다.</p>
            <Field label="기존 Account 이름" value={form.accountName} onChange={v=>update("accountName",v)}/>
            <Field label="Contact 한글 이름" value={form.koreanName} onChange={v=>update("koreanName",v)}/>
            <Field label="Contact 영어 이름" value={form.englishName} onChange={v=>update("englishName",v)} placeholder="OhJunHyeok"/>
            <p className={styles.hint}>기존 Account 사용 · 신규 Contact 생성 · Opportunity 생성하지 않음</p>
          </>}
          {tab==="opportunity_create"&&<>
            <div className={styles.field}>
              <span>연결된 기존 Quote 기준 가격</span>
              <button type="button" className={styles.subtle} onClick={loadLinkedQuote}
                disabled={!selectedRecord||loadingDetail||busy}>
                기존 Oppo → Quote 공정·단가 불러오기
              </button>
              <small>{pairStatus==="PASS"?"견적 공정 검증 PASS":pairStatus==="BLOCK"?"연결 Quote 검증 차단":""}</small>
              {pairedQuote&&pairProjection?.ok&&<div className={styles.selectedInfo}>
                <strong>시료당 {pairProjection.unitPriceNetKrw.toLocaleString()} KRW</strong>
                <span>Cloud 100 Gb당 1개 · {pairProjection.cloudUnits}개 × {pairProjection.cloudUnitNetKrw.toLocaleString()} KRW</span>
                <span>총 {pairProjection.totalDataGb} Gb · VAT 제외 {pairProjection.netKrw.toLocaleString()} KRW</span>
                <span>VAT 포함 {pairProjection.grossKrw.toLocaleString()} KRW</span>
                <p>기존 공정별 단가로 계산한 예상액입니다. 새 Quote의 최종 가격은 저장 후 확인해야 합니다.</p>
              </div>}
              {pairedQuote&&!pairProjection?.ok&&<p className={styles.hint}>{pairProjection?.code||"PRICE_NOT_VERIFIED"}</p>}
            </div>
            <p className={styles.hint}>기존 Oppo를 선택한 뒤 바꿀 값만 수정하세요. Progress Description은 원본에서 복제하지 않습니다.</p>
            <button type="button" className={styles.subtle} onClick={()=>setAdvanced(x=>!x)}>
              {advanced?"고급 ID 편집 숨기기":"Account·Contact ID 편집"}
            </button>
            {advanced&&<div className={styles.two}>
              <Field label="Account ID (001)" value={form.accountId} onChange={v=>update("accountId",v)}/>
              <Field label="Contact ID (003)" value={form.contactId} onChange={v=>update("contactId",v)}/>
            </div>}
            <Field label="기관 이름" value={form.accountName} onChange={v=>update("accountName",v)}/>
            <Field label="고객 이름" value={form.contactName} onChange={v=>update("contactName",v)}/>
            <Field label="Opportunity 이름" value={form.opportunityName} onChange={v=>update("opportunityName",v)}/>
            <Field label="서비스" value={form.service} onChange={v=>update("service",v)}/>
            <div className={styles.two}>
              <Field label="시료 수" type="number" value={form.samples} onChange={v=>update("samples",v)}/>
              <Field label="시료당 데이터량" type="number" step="any" value={form.dataSize} onChange={v=>update("dataSize",v)}/>
            </div>
            <div className={styles.two}>
              <Field label="금액 (KRW, VAT 제외)" type="number" value={form.amountKrw} onChange={v=>update("amountKrw",v)}/>
              <Field label="Close Date" type="date" value={form.closeDate} onChange={v=>update("closeDate",v)}/>
            </div>
            <Field label="참고 AMEA (선택)" required={false} value={form.referenceAmea} onChange={v=>update("referenceAmea",v)}/>
            {totalGb>0&&<p className={styles.hint}>AliCloud: {alicloudUnits(totalGb)}개 (100 Gb당 1개)</p>}
            <div className={styles.field}><span>Progress Description · 신규 작성</span>
              <textarea rows={5} value={form.progressDescription} onChange={e=>update("progressDescription",e.target.value)} />
              <button className={styles.subtle} type="button" onClick={regenerate}>현재 입력값으로 새로 작성</button>
            </div>
          </>}
          {tab==="quote_create"&&<>
            <Field label="대상 Opportunity ID (006)" value={form.opportunityId} onChange={v=>update("opportunityId",v)}/>
            <p className={styles.hint}>기존 Quote에서 고객·연결 Oppo·제품을 불러왔습니다. 수정할 항목만 변경하세요.</p>
            <Field label="Quote 이름 (Oppo와 동일)" value={form.quoteName} onChange={v=>update("quoteName",v)}/>
            <Field label="기관 이름" value={form.accountName} onChange={v=>update("accountName",v)}/>
            <Field label="Contact 이름" value={form.contactName} onChange={v=>update("contactName",v)}/>
            <Field label="기존 제품 카테고리" value={form.productCategory} onChange={v=>update("productCategory",v)}/>
            <Field label="기존 제품명 (정확히)" value={form.productName} onChange={v=>update("productName",v)}/>
            <Field label="공정명 (쉼표로 구분)" value={form.processNames} onChange={v=>update("processNames",v)} placeholder="NovaSeq Reagent Kit (500 Cycles), Data quality control, AliCloud"/>
            <div className={styles.two}>
              <Field label="시료 수" type="number" value={form.samples} onChange={v=>update("samples",v)}/>
              <Field label="데이터량" type="number" step="any" value={form.dataSize} onChange={v=>update("dataSize",v)}/>
            </div>
            <p className={styles.hint}>KRW · Korea · VAT 10% · Coop TS Yoo Ji In · 기존 제품 재사용. 공정·수량·가격 확인 후 저장하세요.</p>
          </>}
        </div>
        <aside className={styles.actionBox}>
          <h2>2. 검증·실행</h2>
          <p>{selectedRecord?"선택한 기존 건을 기준으로 검증합니다.":"먼저 기존 레코드를 선택하세요."}</p>
          <button className={styles.check} type="button" disabled={busy||catalogueBusy||loadingDetail||!selectedRecord}
            onClick={()=>run("check")}>{busy?"처리 중":"1. 사전 검증"}</button>
          <span className={styles.ready} data-ready={ready}>
            {ready?"사전 검증 PASS":"사전 검증 필요"}
          </span>
          <label className={styles.checkbox}><input type="checkbox" checked={dedup} onChange={e=>setDedup(e.target.checked)}/>
            중복 생성 여부 확인</label>
          <label className={styles.checkbox}><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>
            실제 Salesforce 저장 승인</label>
          <button className={styles.save} type="button"
            disabled={busy||catalogueBusy||loadingDetail||!ready||!dedup||!confirmed}
            onClick={()=>run("save")}>2. 실제 실행</button>
          <p className={styles.hint}>검증 실패 시 저장하지 않습니다. Quote는 제품 포함 저장 후 재조회합니다.</p>
          {result&&<section className={styles.result} aria-live="polite">
            <strong data-status={result.status}>{result.status}</strong>
            <p>{result.code||result.detail||""}</p>
            {result.record_id&&<a target="_blank" rel="noreferrer" href={result.url}>생성 레코드 확인</a>}
            <div className={styles.small}>Save: {result.save_clicked?"SUBMITTED":"NOT SUBMITTED"}</div>
          </section>}
        </aside>
      </div>
    </section>
  </main>;
}
