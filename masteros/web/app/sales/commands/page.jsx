"use client";

import {useCallback,useEffect,useMemo,useRef,useState} from "react";
import Link from "next/link";
import {alicloudUnits,freshProgress,validateRequest,opportunityPriceBreakdown} from "../../../lib/sfdc-commands.mjs";
import {recordToDraft,recordSelectionSummary} from "../../../lib/sfdc-record-picker.mjs";
import {buildPairDraft,derivePairPrice} from "../../../lib/sfdc-paired-clone.mjs";
import {matchingIdentity} from "../../../lib/sfdc-identity-picker.mjs";
import IdentityPicker from "./IdentityPicker";
import {kstOneCalendarMonthLater,EXPECTED_SAMPLE_STAGE} from "../../../lib/sfdc-new-opportunity-defaults.mjs";
import {verifiedQuoteProcessBreakdown} from "../../../lib/sfdc-quote-process-review.mjs";
import styles from "./page.module.css";

const common={confirmSave:false,noDuplicateConfirmed:false};
const initial={
  lead_convert:{leadId:"",accountName:"",koreanName:"",englishName:""},
  opportunity_create:{referenceOpportunityId:"",accountId:"",contactId:"",
    accountName:"",contactName:"",opportunityName:"",samples:1,
    amountKrw:0,unitPriceNetKrw:0,cloudUnits:0,cloudUnitNetKrw:0,
    closeDate:"",progressDescription:"",service:"",dataSize:1,unit:"Gb",referenceAmea:""},
  quote_create:{opportunityId:"",sourceQuoteId:"",quoteName:"",
    accountName:"",contactName:"",productCategory:"",productName:"",
    samples:1,dataSize:1,unit:"Gb",processNames:""},
};
const tabs=[
  {id:"lead_convert",name:"Lead Convert",caption:"기존 Account → Contact · Oppo 생성 안 함"},
  {id:"opportunity_create",name:"Oppo + Quote 함께 생성",caption:"기존 Oppo·Quote 기준 · 006 → a0P 연속 생성"},
  {id:"quote_create",name:"Quote 생성",caption:"기존 제품만 · 가격 검증 우선"},
];
function Field({label,value,onChange,required=true,type="text",step,placeholder,disabled=false}){
  return <label className={styles.field}><span>{label}</span>
    <input type={type} value={value??""} onChange={e=>onChange(type==="number"?Number(e.target.value):e.target.value)}
      required={required} step={step} disabled={disabled} placeholder={placeholder||""}/></label>;
}
function Flag({label,state}){
  const p=String(state||"BLOCK");
  const color=["PASS","PREFLIGHT_PASS","SNAPSHOT_READY"].includes(p)?"ok":p.includes("BLOCK")?"bad":"warn";
  return <div className={styles.flag}><span>{label}</span><b data-tone={color}>{p}</b></div>;
}
export default function SfdcCommandCenter(){
  const [tab,setTab]=useState("lead_convert");
  const [forms,setForms]=useState(()=>{
    const forms=structuredClone(initial);
    forms.opportunity_create.closeDate=kstOneCalendarMonthLater();
    return forms;
  });
  const [health,setHealth]=useState(null);
  const [healthBusy,setHealthBusy]=useState(false);
  const [busy,setBusy]=useState(false);
  const [result,setResult]=useState(null);
  const [preflight,setPreflight]=useState("");
  const [confirmed,setConfirmed]=useState(false);
  const [dedup,setDedup]=useState(false);
  const [priceConfirmed,setPriceConfirmed]=useState(false);
  const [packConfirmed,setPackConfirmed]=useState(false);
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
  const [selectedIdentity,setSelectedIdentity]=useState(null);
  const [unitPriceEdited,setUnitPriceEdited]=useState(false);
  const resource=tab==="lead_convert"?"lead":tab==="opportunity_create"?"opportunity":"quote";
  const form=forms[tab];
  const signature=useMemo(()=>JSON.stringify({tab,...form}),[tab,form]);
  const ready=signature===preflight && selectedRecord?.resource===resource;
  const update=(key,value)=>{
    if(tab==="opportunity_create"&&key==="unitPriceNetKrw")setUnitPriceEdited(true);
    setForms(prev=>{
      const previous=prev[tab];
      const next={...previous,[key]:value};
      if(tab==="opportunity_create"){
        const relevant=["samples","dataSize","unitPriceNetKrw","service","accountName",
          "contactName","referenceAmea","unit"];
        if(["samples","dataSize"].includes(key)){
          if(Number.isInteger(next.samples)&&next.samples>0&&Number.isFinite(next.dataSize)&&next.dataSize>0)
            next.cloudUnits=next.unit==="Gb"?Math.ceil(next.samples*next.dataSize/100):0;
          if(pairedQuote){
            const quoted=derivePairPrice(pairedQuote,next.samples,next.dataSize);
            if(quoted.ok){next.cloudUnits=quoted.cloudUnits;next.cloudUnitNetKrw=quoted.cloudUnitNetKrw;}
          }
        }
        if(["samples","dataSize","unitPriceNetKrw"].includes(key)){
          const price=opportunityPriceBreakdown(next);
          next.amountKrw=price.ok?price.netKrw:0;
        }
        if(relevant.includes(key)){
          let originalGenerated="";
          try{originalGenerated=freshProgress(previous)}catch{}
          if(!previous.progressDescription || previous.progressDescription===originalGenerated){
            try{next.progressDescription=freshProgress(next)}catch{next.progressDescription="";}
          }
        }
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
    setOriginalDraft(null);setSelectedIdentity(null);setUnitPriceEdited(false);
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
    setSelectedIdentity(null);setUnitPriceEdited(false);
    setPairedQuote(null);setPairStatus("NOT_CHECKED");
    setResult(null);setPreflight("");
    browse(resource,"");
  },[resource,browse]);
  function reflectNewCustomer(next){
    setForms(prev=>{
      const old=prev[tab],merged={...old,...next};
      if(tab==="opportunity_create"){
        let oldAuto="";
        try{oldAuto=freshProgress(old)}catch{}
        if(!old.progressDescription||old.progressDescription===oldAuto){
          try{merged.progressDescription=freshProgress(merged)}
          catch{merged.progressDescription=""}
        }
      }
      return {...prev,[tab]:merged};
    });
    setResult(null);setPreflight("");setConfirmed(false);setDedup(false);
    setPriceConfirmed(false);setPackConfirmed(false);
  }
  function selectAccount(account){
    if(!account?.name){
      setSelectedIdentity(null);
      reflectNewCustomer({accountId:"",accountName:"",contactId:"",contactName:""});
      return;
    }
    setSelectedIdentity(null);
    reflectNewCustomer({
      accountId:account.id||"",accountName:account.name,
      contactId:"",contactName:""
    });
  }
  async function selectContact(pair){
    if(!pair?.ok||!pair.account?.name||!pair.contact?.name||loadingDetail||busy)return;
    if(tab==="quote_create"&&selectedRecord?.accountName&&
       selectedRecord.accountName!==pair.account.name){
      setResult({status:"BLOCK",code:"QUOTE_PARENT_ACCOUNT_MISMATCH"});
      return;
    }
    setSelectedIdentity(null);
    reflectNewCustomer({
      accountId:pair.account.id,accountName:pair.account.name,
      contactId:"",contactName:pair.contact.name
    });
    // Feishu's Contact IDs are often external references, not native 003 IDs.
    // Resolve the precise source Quote through current authenticated Salesforce.
    if(!/^a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/.test(pair.sourceQuoteId||"")){
      setResult({status:"BLOCK",code:"NATIVE_QUOTE_CONTACT_VERIFICATION_REQUIRED"});
      return;
    }
    setLoadingDetail(true);setResult({status:"CHECKING",code:"CONTACT_SFDC_READBACK"});
    try{
      const response=await fetch("/api/sfdc/records-local",{
        method:"POST",cache:"no-store",credentials:"omit",
        headers:{"Content-Type":"application/json","X-SFDC-Command":"1"},
        body:JSON.stringify({resource:"quote",mode:"detail",
          recordId:pair.sourceQuoteId,forceLive:true})
      });
      const live=await response.json();
      if(!response.ok||live.status!=="PASS"||live.id!==pair.sourceQuoteId||
         live.accountId!==pair.account.id||live.accountName!==pair.account.name||
         live.contactName!==pair.contact.name||
         !/^003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/.test(live.contactId||""))
        throw Error("CONTACT_ACCOUNT_LIVE_MATCH_REQUIRED");
      setSelectedIdentity({
        account:{id:live.accountId,name:live.accountName},
        contact:{id:live.contactId,name:live.contactName,
          email:pair.contact.email},
        source:"SFDC_QUOTE_LIVE_VERIFIED"
      });
      reflectNewCustomer({
        accountId:live.accountId,accountName:live.accountName,
        contactId:live.contactId,contactName:live.contactName
      });
      setResult({status:"PASS",code:"CONTACT_ACCOUNT_SFDC_VERIFIED"});
    }catch(error){
      setSelectedIdentity(null);
      setResult({status:"BLOCK",code:error?.message||"CONTACT_SFDC_SOURCE_UNAVAILABLE"});
    }finally{setLoadingDetail(false)}
  }
  async function hydrateLinkedQuote(recordId,base,{preserveEdit=false}={}){
    setPairStatus("LOADING");
    try{
      const response=await fetch("/api/sfdc/records-local",{
        method:"POST",cache:"no-store",credentials:"omit",
        headers:{"Content-Type":"application/json","X-SFDC-Command":"1"},
        body:JSON.stringify({resource:"opportunity",mode:"bundle",recordId})
      });
      const bundle=await response.json();
      if(!response.ok||bundle.status!=="PASS")throw Error(bundle.code||"QUOTE_LINK_UNAVAILABLE");
      const checked=buildPairDraft(bundle,base);
      if(!checked.ok)throw Error(checked.code);
      if(checked.quote.opportunityId!==recordId)throw Error("WRONG_PARENT_OPPORTUNITY");
      const sampleRate=preserveEdit&&unitPriceEdited?base.unitPriceNetKrw:checked.form.unitPriceNetKrw;
      const populated={...base,
        ...Object.fromEntries(["sourceQuoteNetKrw","sourceQuoteSamples","sourceDataSizeGb",
          "sourceCloudUnits","productName","productCategory","processNames",
          "sampleStage","packPolicy","packQuantity","cooperativeTS"].map(k=>[k,checked.form[k]])),
        quoteName:base.opportunityName||checked.form.opportunityName,
        // Existing validated quote process rates take precedence until user overrides.
        unitPriceNetKrw:sampleRate,
        cloudUnits:checked.form.cloudUnits,
        cloudUnitNetKrw:checked.form.cloudUnitNetKrw,
        sourceQuoteId:checked.form.sourceQuoteId,
        referenceAmea:base.referenceAmea||checked.form.referenceAmea,
      };
      const totals=opportunityPriceBreakdown(populated);
      populated.amountKrw=totals.ok?totals.netKrw:0;
      let oldAuto="";
      try{oldAuto=freshProgress(base)}catch{}
      if(!base.progressDescription||base.progressDescription===oldAuto){
        try{populated.progressDescription=freshProgress(populated)}
        catch{populated.progressDescription=""}
      }
      setPairedQuote(checked.quote);setPairStatus("PASS");
      setForms(prev=>({...prev,opportunity_create:populated}));
      setResult(null);
      return true;
    }catch(error){
      setPairedQuote(null);setPairStatus("BLOCK");
      setResult({status:"BLOCK",code:error?.message||"SOURCE_PRICE_UNVERIFIED"});
      return false;
    }
  }
  async function chooseRecord(id){
    if(loadingDetail||busy)return;
    setLoadingDetail(true);setResult(null);setPreflight("");
    setPairedQuote(null);setPairStatus("NOT_CHECKED");
    setSelectedIdentity(null);setUnitPriceEdited(false);
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
      if(resource==="opportunity"){
        // This is a NEW Opportunity; do not reuse historical Close Date.
        next.closeDate=kstOneCalendarMonthLater();
        next.sampleStage=EXPECTED_SAMPLE_STAGE;
      }
      setForms(prev=>({...prev,[tab]:next}));
      setSelectedRecord(item);
      setOriginalDraft(next);
      if(resource==="opportunity"&&next.accountId&&next.contactId){
        setSelectedIdentity({
          account:{id:next.accountId,name:next.accountName},
          contact:{id:next.contactId,name:next.contactName,email:""},
          source:"SFDC_OPPORTUNITY_SOURCE"
        });
      }
      setDedup(false);setConfirmed(false);
      if(resource==="opportunity")await hydrateLinkedQuote(id,next);
    }catch(e){
      setSelectedRecord(null);setOriginalDraft(null);setSelectedIdentity(null);
      setResult({status:"BLOCK",code:e?.message||"DETAIL_UNAVAILABLE"});
    }finally{setLoadingDetail(false);}
  }
  const pairProjection=useMemo(()=>{
    if(!pairedQuote||tab!=="opportunity_create")return null;
    return derivePairPrice(pairedQuote,form.samples,form.dataSize);
  },[pairedQuote,form.samples,form.dataSize,tab]);
  async function loadLinkedQuote(){
    if(tab!=="opportunity_create"||!selectedRecord?.id||busy||loadingDetail)return;
    setLoadingDetail(true);setPreflight("");
    try{await hydrateLinkedQuote(selectedRecord.id,form,{preserveEdit:true});}
    finally{setLoadingDetail(false)}
  }
  const changedFields=useMemo(()=>{
    if(!originalDraft)return [];
    return Object.keys(originalDraft).filter(k=>form[k]!==originalDraft[k] &&
      !["progressDescription","referenceAmea"].includes(k));
  },[form,originalDraft]);
  function switchTab(next){
    setTab(next);setResult(null);setPreflight("");setConfirmed(false);setDedup(false);
    setPriceConfirmed(false);setPackConfirmed(false);
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
    if(tab==="opportunity_create"){
      const matched=matchingIdentity(form,selectedIdentity);
      if(!matched.ok){setResult({status:"BLOCK",code:matched.code});return;}
    }
    if(tab==="quote_create"&&selectedIdentity){
      if(selectedRecord?.accountName!==form.accountName ||
         selectedRecord?.contactName!==form.contactName){
        setResult({status:"BLOCK",code:"QUOTE_PARENT_CUSTOMER_MISMATCH"});return;
      }
    }
    const isPaired=tab==="opportunity_create";
    if(isPaired&&!pairedQuote){
      setResult({status:"BLOCK",code:"LINKED_SOURCE_QUOTE_REQUIRED"});return;
    }
    const req={...form,action:isPaired?"oppo_quote_pair":tab,mode,
      confirmSave:mode==="save"&&confirmed,
      noDuplicateConfirmed:mode==="save"&&dedup,
      ...(isPaired?{
        quoteName:form.opportunityName,
        packQuantity:form.samples,
        packPolicy:"SAME_SAMPLES",cooperativeTS:"Yoo Ji In",
        sampleStage:EXPECTED_SAMPLE_STAGE,
        priceConfirmed:mode==="save"&&priceConfirmed,
        packConfirmed:mode==="save"&&packConfirmed,
        processPriceReviewed:mode==="save"&&priceConfirmed&&
          processReview?.ok&&!processReview.manualOverride
      }:{})};
    if(tab==="opportunity_create"&&pairedQuote&&
       (!pairProjection?.ok||form.cloudUnits!==pairProjection.cloudUnits||
        form.cloudUnitNetKrw!==pairProjection.cloudUnitNetKrw)){
      setResult({status:"BLOCK",code:"SOURCE_CLOUD_PRICE_MISMATCH"});return;
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
        unit:form.unit,referenceAmea:form.referenceAmea,
        unitPriceNetKrw:form.unitPriceNetKrw,
        cloudUnits:form.cloudUnits,cloudUnitNetKrw:form.cloudUnitNetKrw
      });
      update("progressDescription",description);
    }catch{setResult({status:"BLOCK",code:"PROGRESS_FIELDS_INCOMPLETE"});}
  }
  const currentOppoPricing=tab==="opportunity_create"?opportunityPriceBreakdown(form):null;
  const processReview=useMemo(()=>tab==="opportunity_create"&&pairedQuote?
    verifiedQuoteProcessBreakdown(pairedQuote,form.samples,form.dataSize,
      form.unitPriceNetKrw):null,[tab,pairedQuote,form.samples,form.dataSize,form.unitPriceNetKrw]);
  const totalGb=tab==="opportunity_create"&&form.unit==="Gb"?
    form.samples*form.dataSize:null;
  return <main className={styles.wrap}>
    <header className={styles.top}>
      <div><p className={styles.eyebrow}>SALES AUTOMATION</p>
        <h1>업무 실행</h1><p>입력 → 검증 → 실행 → 결과 확인</p></div>
      <div className={styles.navigation}>
        <Link href="/sales/commands/pair">Oppo → Quote 통합 검증</Link>
        <Link href="/sales/projects">프로젝트</Link>
        <Link href="/sales/mail">메일 · Lead</Link>
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
              <span>연결된 기존 Quote 기준 가격 · Oppo + Quote 연속 생성</span>
              <button type="button" className={styles.subtle} onClick={loadLinkedQuote}
                disabled={!selectedRecord||loadingDetail||busy}>
                기존 Oppo → Quote 공정·단가 불러오기
              </button>
              <small>{pairStatus==="LOADING"?"연결 Quote 단가 자동 조회 중":
                pairStatus==="PASS"?"연결 Quote의 검증된 KRW 단가 자동 입력 완료 · 필요 시 아래에서 수정":
                pairStatus==="BLOCK"?"원본 Quote KRW 단가 미확인 · 임의 단가 입력 금지":"Oppo 선택 후 단가 자동 조회"}</small>
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
            <IdentityPicker
              account={{id:form.accountId,name:form.accountName}}
              contact={{id:form.contactId,name:form.contactName}}
              onAccount={selectAccount} onContact={selectContact}
              disabled={loadingDetail||busy}/>
            <p className={styles.hint}>기관·고객은 이름을 직접 쓰지 않고 검색 결과에서 선택합니다.
              고객 검색 결과에는 기관명이 반드시 같이 나옵니다. 동명이인 기관을 확인하세요.</p>
            <Field label="Opportunity 이름" value={form.opportunityName} onChange={v=>update("opportunityName",v)}/>
            <Field label="서비스" value={form.service} onChange={v=>update("service",v)}/>
            <div className={styles.two}>
              <Field label="시료 수" type="number" value={form.samples} onChange={v=>update("samples",v)}/>
              <Field label="시료당 데이터량" type="number" step="any" value={form.dataSize} onChange={v=>update("dataSize",v)}/>
            </div>
            <div className={styles.two}>
              <Field label="Oppo 샘플당 단가 (KRW, VAT 제외)" type="number"
                value={form.unitPriceNetKrw||""} disabled={loadingDetail}
                onChange={v=>update("unitPriceNetKrw",v)}
                placeholder="예: 250000"/>
              <Field label="Close Date · 오늘부터 한 달 뒤" type="date"
                value={form.closeDate} onChange={v=>update("closeDate",v)}/>
            </div>
            <p className={styles.hint}>신규 Oppo 기본 단계: Prospective · 샘플 입고 예정
              (실제 입고·QC·PO 확인 전). Close Date는 한국시간 오늘부터 한 달 뒤로 기본 설정됩니다.</p>
            {processReview?.ok&&<div className={styles.selectedInfo} data-testid="oppo-process-breakdown">
              <strong>기존 Quote 검증 공정별 단가 · 공급가액 (VAT 제외)</strong>
              {processReview.items.map((part,i)=><div key={i}>
                <span>{part.name}{part.packNo?" · 원본 Pack "+part.packNo:""}</span>
                <span>{part.quantity} × {part.unitPriceKrw.toLocaleString("ko-KR")} KRW
                {" = "}{part.projectedNetKrw.toLocaleString("ko-KR")} KRW</span>
              </div>)}
              <span>Pack 검토: 생물학적 샘플 {processReview.pack.biologicalSamples}개
                {" → "}Pack 수량 {processReview.pack.quantity}개
                {" · "}Coop TS: Yoo Ji In</span>
              {processReview.pack.sourcePackAmbiguous&&
                <p>원본 공정의 Pack No가 서로 다릅니다. 실제 Pack 구성 확인이 필요합니다.</p>}
              {processReview.manualOverride&&
                <p>샘플당 단가를 직접 변경했습니다. 위 공정별 가격은 원본 단가이므로
                  변경 금액을 공정에 배분하고 Quote에 적용하기 전 검토가 필요합니다.</p>}
            </div>}
            {pairedQuote&&!processReview?.ok&&
              <p className={styles.hint}>공정별 가격 검증 불가:
                {processReview?.code||"SOURCE_PROCESS_PRICE_UNVERIFIED"}</p>}
            <div className={styles.selectedInfo} data-testid="oppo-unit-price-summary">
              <strong>샘플당 단가: {currentOppoPricing?.ok?
                currentOppoPricing.unitPriceNetKrw.toLocaleString("ko-KR")+" KRW":"미확인"}</strong>
              <span>시료 {form.samples}개 × 단가 = {currentOppoPricing?.ok?
                currentOppoPricing.sampleTotalKrw.toLocaleString("ko-KR")+" KRW":"계산 대기"}</span>
              <span>AliCloud {form.cloudUnits||0}개 × {(form.cloudUnitNetKrw||0).toLocaleString("ko-KR")} KRW
                {" · "}클라우드 합계 {currentOppoPricing?.ok?
                currentOppoPricing.cloudTotalKrw.toLocaleString("ko-KR")+" KRW":"계산 대기"}</span>
              <strong>Oppo 총 공급가액 (VAT 제외): {currentOppoPricing?.ok?
                currentOppoPricing.netKrw.toLocaleString("ko-KR")+" KRW":"단가 입력 필요"}</strong>
              <span>VAT 10%: {currentOppoPricing?.ok?
                currentOppoPricing.vatKrw.toLocaleString("ko-KR")+" KRW":"—"}</span>
              {pairedQuote&&pairProjection?.ok&&form.unitPriceNetKrw!==pairProjection.unitPriceNetKrw&&
                <p>기존 Quote와 단가가 달라졌습니다. Opportunity 금액과 Description은 새 단가를 사용하지만 Quote 공정 단가는 별도 검증이 필요합니다.</p>}
            </div>
            <Field label="참고 AMEA (선택)" required={false} value={form.referenceAmea} onChange={v=>update("referenceAmea",v)}/>
            {totalGb>0&&<p className={styles.hint}>AliCloud 필요 수량: {alicloudUnits(totalGb)}개 (100 Gb당 1개). 단가는 연결된 Quote에서 확인된 경우에만 합산합니다.</p>}
            <div className={styles.field}><span>Progress Description · 신규 작성</span>
              <textarea rows={5} value={form.progressDescription} onChange={e=>update("progressDescription",e.target.value)} />
              <small>저장되는 SFDC Opportunity Progress Description에 샘플당 단가·수량·VAT 제외 합계가 포함됩니다.</small>
              <button className={styles.subtle} type="button" onClick={regenerate}>현재 입력값으로 새로 작성</button>
            </div>
          </>}
          {tab==="quote_create"&&<>
            <Field label="대상 Opportunity ID (006)" value={form.opportunityId} onChange={v=>update("opportunityId",v)}/>
            <p className={styles.hint}>기존 Quote에서 고객·연결 Oppo·제품을 불러왔습니다. 수정할 항목만 변경하세요.</p>
            <Field label="Quote 이름 (Oppo와 동일)" value={form.quoteName} onChange={v=>update("quoteName",v)}/>
            <IdentityPicker
              account={{id:selectedIdentity?.account?.id,name:form.accountName}}
              contact={{id:selectedIdentity?.contact?.id,name:form.contactName}}
              onAccount={selectAccount} onContact={selectContact}
              disabled={loadingDetail||busy}/>
            <p className={styles.hint}>Quote는 원래 연결된 Opportunity의 기관·고객과 같아야 합니다.
              다른 기관의 고객을 선택하면 저장 검증이 차단됩니다.</p>
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
          {tab==="opportunity_create"&&<>
            <label className={styles.checkbox}><input type="checkbox" checked={priceConfirmed}
              disabled={!processReview?.ok||processReview.manualOverride}
              onChange={e=>setPriceConfirmed(e.target.checked)}/>
              기존 Quote 공정 구성·샘플당 KRW 단가 확인</label>
            <label className={styles.checkbox}><input type="checkbox" checked={packConfirmed}
              disabled={!processReview?.ok}
              onChange={e=>setPackConfirmed(e.target.checked)}/>
              Pack 수량 = 샘플 수 확인 · Coop TS Yoo Ji In</label>
            {processReview?.manualOverride&&<p className={styles.hint}>
              변경된 샘플당 단가의 공정별 KRW 배분 검증 전에는 동시 저장할 수 없습니다.</p>}
          </>}
          <label className={styles.checkbox}><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>
            실제 Salesforce 저장 승인</label>
          <button className={styles.save} type="button"
            disabled={busy||catalogueBusy||loadingDetail||!ready||!dedup||!confirmed||
              (tab==="opportunity_create"&&(!priceConfirmed||!packConfirmed||
                !processReview?.ok||processReview.manualOverride))}
            onClick={()=>run("save")}>2. {tab==="opportunity_create"?"Oppo + Quote 연속 생성":"실제 실행"}</button>
          <p className={styles.hint}>Oppo → Quote를 하나의 명령으로 순차 생성합니다.
            Salesforce는 원자적 트랜잭션이 아니므로 실패 시 생성된 Oppo ID를 남기고 Quote를 HOLD 처리합니다.
            실제 Quote 제품·Pack·가격은 저장 후 재확인 필수입니다.</p>
          {result&&<section className={styles.result} aria-live="polite">
            <strong data-status={result.status}>{result.status}</strong>
            <p>{result.code||result.detail||""}</p>
            {result.record_id&&<a target="_blank" rel="noreferrer" href={result.url}>생성 레코드 확인</a>}
            {result.opportunity_id&&<p>생성 Oppo: {result.opportunity_id}</p>}
            {result.quotation_id&&<p>생성 Quote: {result.quotation_id}</p>}
            <div className={styles.small}>Save: {result.save_clicked?"SUBMITTED":"NOT SUBMITTED"}</div>
          </section>}
        </aside>
      </div>
    </section>
  </main>;
}
