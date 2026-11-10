"use client";

import Link from "next/link";
import {useCallback,useEffect,useMemo,useRef,useState} from "react";
import {previewCandidate,pairWebRequest,priceLines,cloudQuantity} from "../../../../../lib/sfdc-pair-workspace.mjs";
import styles from "../page.module.css";
import ReportOppoDraft from "../ReportOppoDraft";

const FEISHU_BASE="https://ocnz4cb25scn.feishu.cn/base/IpMkbUD0vaFqtYs93a3csXtdn1b?table=blkzYT2OAVQssL3Y";
const FEISHU_REPORT_LINES="https://ocnz4cb25scn.feishu.cn/base/IpMkbUD0vaFqtYs93a3csXtdn1b?table=tblHme64Ccdj4Fwv";
const FEISHU_REPORT_PRODUCTS="https://ocnz4cb25scn.feishu.cn/base/IpMkbUD0vaFqtYs93a3csXtdn1b?table=tbl2tGZyBlEbyruO";
const FEISHU_REPORT_PROCESSES="https://ocnz4cb25scn.feishu.cn/base/IpMkbUD0vaFqtYs93a3csXtdn1b?table=tblD2XMNWeAcvGWe";
const money=(x)=>Number.isSafeInteger(x)?x.toLocaleString("ko-KR")+" KRW":"검증 전";
const bytes=(v)=>Number.isFinite(v)?(v>=1024?(v/1024).toFixed(1)+" KiB":v.toLocaleString("ko-KR")+" B"):"—";
const kst=(value)=>value?new Date(value).toLocaleString("ko-KR",{timeZone:"Asia/Seoul",hour12:false}):"기록 없음";
const empty={sourceOpportunityId:"",sourceQuoteId:"",newOpportunityName:"",
  samples:1,dataSizeGb:1,productUnitOverrideKrw:"",
  cloudUnitOverrideKrw:"",newOpportunityId:""};

async function localRead(url,body){
  const response=await fetch(url,{
    method:"POST",cache:"no-store",credentials:"omit",
    headers:{"Content-Type":"application/json","X-SFDC-Command":"1"},
    body:JSON.stringify(body)
  });
  const value=await response.json();
  if(response.status===409)throw Error(value.code||"LOCAL_OPERATION_BUSY");
  if(!response.ok&&value.status!=="BLOCK"&&value.status!=="PREFLIGHT_BLOCK")
    throw Error(value.code||"LOCAL_SOURCE_UNAVAILABLE");
  return value;
}

function Status({value}){
  const ok=["PASS","PREFLIGHT_PASS","PREVIEW_READY"].includes(value);
  return <span className={styles.state} data-ok={ok}>{value||"NOT_CHECKED"}</span>;
}

export default function PairedQuoteWeb(){
  const [reportQuery,setReportQuery]=useState("");
  const [reportBackend,setReportBackend]=useState("FEISHU");
  const reportEndpoint=reportBackend==="FEISHU"?"/api/sfdc/feishu-report-local":"/api/sfdc/report-local";
  const [reportStatus,setReportStatus]=useState(null);
  const [referenceStatus,setReferenceStatus]=useState(null);
  const [reportRows,setReportRows]=useState([]);
  const [reportSelected,setReportSelected]=useState(null);
  const [reportBusy,setReportBusy]=useState("");
  const [reportError,setReportError]=useState("");
  const reportStarted=useRef(false);
  const [query,setQuery]=useState("");
  const [list,setList]=useState([]);
  const [listStatus,setListStatus]=useState("REPORT_FIRST");
  const [selected,setSelected]=useState(null);
  const [form,setForm]=useState(empty);
  const [result,setResult]=useState(null);
  const [busy,setBusy]=useState("");
  const [cacheInfo,setCacheInfo]=useState(null);
  const [cacheBusy,setCacheBusy]=useState(false);
  const [cacheOffset,setCacheOffset]=useState(0);
  const [cacheNotice,setCacheNotice]=useState("");
  const seq=useRef(0);
  const source=useMemo(()=>previewCandidate(selected),[selected]);
  const lines=useMemo(()=>priceLines(result?.pricing),[result]);
  const totalGb=form.samples*form.dataSizeGb;
  const set=(k,v)=>{
    setForm(prev=>({...prev,[k]:v}));
    setResult(null);
  };
  const browse=useCallback(async(term="")=>{
    const current=++seq.current;
    setBusy("LIST");setListStatus("LOADING");setSelected(null);setResult(null);setForm(empty);
    try{
      let data;
      for(let retry=0;retry<20;retry++){
        try{
          data=await localRead("/api/sfdc/records-local",{
            resource:"opportunity",mode:"list",query:term
          });
          break;
        }catch(e){
          if(!String(e.message).includes("BUSY")||retry===19)throw e;
          await new Promise(resolve=>setTimeout(resolve,2000));
        }
      }
      if(current!==seq.current)return;
      if(data.status!=="PASS"||!Array.isArray(data.records))
        throw Error(data.code||"LIST_SOURCE_UNAVAILABLE");
      setList(data.records);setListStatus("PASS");
    }catch(e){
      if(current===seq.current){setList([]);setListStatus(e.message||"SOURCE_UNAVAILABLE");}
    }finally{if(current===seq.current)setBusy("");}
  },[]);

  const loadCacheStatus=useCallback(async()=>{
    try{
      const response=await fetch("/api/sfdc/cache-local",{
        cache:"no-store",credentials:"omit",headers:{"X-SFDC-Command":"1"}
      });
      const value=await response.json();
      if(value.status!=="PASS")throw Error(value.code||"CACHE_STATUS_UNAVAILABLE");
      setCacheInfo(value);
      return value;
    }catch{
      setCacheInfo({cache_status:"SOURCE_UNAVAILABLE",tiers:{}});
      return null;
    }
  },[]);
  useEffect(()=>{loadCacheStatus();},[loadCacheStatus]);

  async function warmCache(){
    if(cacheBusy||busy)return;
    setCacheBusy(true);setCacheNotice("Salesforce 읽기 전용 사전 수집 중 · 선택한 최대 3건...");
    try{
      const response=await fetch("/api/sfdc/cache-local",{
        method:"POST",cache:"no-store",credentials:"omit",
        headers:{"X-SFDC-Command":"1","Content-Type":"application/json"},
        body:JSON.stringify({mode:"WARM",limit:3,offset:cacheOffset})
      });
      const value=await response.json();
      if(!["PASS","PARTIAL"].includes(value.status))
        throw Error(value.code||value.stage||"SOURCE_UNAVAILABLE");
      setCacheNotice(`수집 ${value.sampled??0}건 · 캐시 보유 ${value.bundles_available??0}건 · 원본 가격 확인 ${value.source_price_verified??0}건 · 보류 ${value.source_price_hold??0}건`);
      setCacheOffset(prev=>(prev+3)>=30?0:prev+3);
      await loadCacheStatus();
      if(!selected)browse("");
    }catch(e){
      setCacheNotice("사전 수집 실패: "+(e?.message||"SOURCE_UNAVAILABLE"));
      await loadCacheStatus();
    }finally{setCacheBusy(false);}
  }

  const getReferenceStatus=useCallback(async()=>{
    try{
      const data=await localRead("/api/sfdc/feishu-report-local",{mode:"REFERENCE_STATUS"});
      setReferenceStatus(data);
      return data;
    }catch{
      const fail={status:"BLOCK",code:"PRECLASSIFIED_INDEX_NOT_AVAILABLE"};
      setReferenceStatus(fail);
      return fail;
    }
  },[]);

  const getReportStatus=useCallback(async()=>{
    try{
      const response=await fetch(reportEndpoint,{
        headers:{"X-SFDC-Command":"1"},cache:"no-store",credentials:"omit"
      });
      const data=await response.json();
      setReportStatus(data.status==="PASS"?data:null);
      if(data.status!=="PASS")setReportError(data.code||"REPORT_NOT_INDEXED");
      return data;
    }catch{setReportStatus(null);setReportError("REPORT_SOURCE_UNAVAILABLE");return null;}
  },[reportEndpoint]);

  const searchReport=useCallback(async(text="")=>{
    setReportBusy("SEARCH");setReportError("");setReportSelected(null);
    try{
      const data=await localRead(reportEndpoint,{
        mode:"SEARCH",query:text,limit:25
      });
      if(data.status!=="PASS")throw Error(data.code||"REPORT_SEARCH_FAILED");
      setReportRows(data.rows||[]);
    }catch(e){setReportRows([]);setReportError(e.message||"REPORT_SEARCH_FAILED");
    }finally{setReportBusy("");}
  },[reportEndpoint]);

  useEffect(()=>{
    if(reportStarted.current===reportBackend)return;
    reportStarted.current=reportBackend;
    getReportStatus();
    if(reportBackend==="FEISHU")getReferenceStatus();else setReferenceStatus(null);
    searchReport("");
  },[getReportStatus,getReferenceStatus,searchReport,reportBackend]);

  async function chooseReport(item){
    setReportBusy("DETAIL");setReportError("");setReportSelected(null);
    try{
      const data=await localRead(reportEndpoint,{
        mode:"DETAIL",id:item.qid
      });
      if(data.status!=="PASS")throw Error(data.code||"REPORT_DETAIL_UNAVAILABLE");
      setReportSelected(data);
    }catch(e){setReportError(e.message||"REPORT_DETAIL_UNAVAILABLE");
    }finally{setReportBusy("");}
  }

  async function syncStagedReport(){
    setReportBusy("SYNC");setReportError("");setReportSelected(null);
    try{
      const data=await localRead(reportEndpoint,{mode:reportBackend==="FEISHU"?"REFRESH":"SYNC_STAGED"});
      if(data.status!=="PASS")throw Error(data.code||"SHEET_SYNC_FAILED");
      setReportStatus(data);
      setReportRows([]);
      await getReportStatus();
      if(reportBackend==="FEISHU")await getReferenceStatus();
      await searchReport("");
    }catch(e){setReportError(e.message||"SHEET_SYNC_FAILED");
    }finally{setReportBusy("");}
  }

  async function choose(item){
    if(busy)return;
    setBusy("BUNDLE");setResult(null);setSelected(null);
    try{
      const bundle=await localRead("/api/sfdc/records-local",{
        resource:"opportunity",mode:"bundle",recordId:item.id
      });
      const review=previewCandidate(bundle);
      if(!review.ok)throw Error(review.code);
      const q=review.quote,opp=review.opportunity;
      setSelected(bundle);
      setForm({
        ...empty,sourceOpportunityId:opp.id,sourceQuoteId:q.id,
        newOpportunityName:(opp.name+"-New").slice(0,230),
        samples:Number.isInteger(q.samples)?q.samples:1,
        dataSizeGb:Number.isFinite(q.dataSize)&&q.dataSize>0?q.dataSize:1
      });
    }catch(e){setResult({status:"BLOCK",code:e.message||"SOURCE_BUNDLE_UNAVAILABLE"});}
    finally{setBusy("");}
  }

  async function run(mode){
    if(busy||!source.ok)return;
    const checked=pairWebRequest(form,mode);
    if(!checked.ok){setResult({status:"BLOCK",code:checked.code});return;}
    setBusy(mode);setResult(null);
    try{
      const value=await localRead("/api/sfdc/pair-check-local",checked.body);
      setResult(value);
    }catch(e){setResult({status:"BLOCK",code:e.message||"LOCAL_CHECK_UNAVAILABLE"});}
    finally{setBusy("");}
  }

  return <main className={styles.page}>
    <header className={styles.header}>
      <div><p className={styles.eyebrow}>SALES AUTOMATION / VERIFIED WORKSPACE</p>
        <h1>Opportunity → Quote 기존 검증</h1>
        <p>Feishu의 저장된 Quote Report → 공정별 단가 조회 → 필요한 경우에만 Salesforce 재검증</p></div>
      <div className={styles.nav}>
        <Link href="/sales/commands">기존 업무 실행</Link>
        <a href={FEISHU_REPORT_LINES} target="_blank" rel="noreferrer">Feishu Quote 상세 Report</a>
        <a href={FEISHU_BASE} target="_blank" rel="noreferrer">Feishu Base</a>
      </div>
    </header>
    <div className={styles.notice} role="status">
      <b>CHECK ONLY · Salesforce 저장 0건</b>
      <span>이 화면은 로컬 PC의 인증된 Salesforce를 조회합니다. Feishu의 기존 요청 큐는 유지되며, 이 화면에서 고객 데이터 전송·견적 발행·Salesforce 저장은 수행하지 않습니다.</span>
    </div>
    <section className={styles.panel} aria-label="Quote Report 빠른 검색">
      <div className={styles.panelHead}>
        <span className={styles.step}>R</span>
        <div><h2>Quote Report 우선 검색</h2>
          <p>메일 Report → Feishu 상세 테이블 → 웹용 검색 캐시. 기본값은 로그인된 Feishu 원본이며 Salesforce 화면을 열지 않습니다.</p></div>
        <Status value={reportStatus?.source_state||"REPORT_NOT_READY"}/>
      </div>
      <div className={styles.statStrip}>
        <div><small>Report Quote</small><strong>{reportStatus?.quote_count??"—"}건</strong></div>
        <div><small>Quote Products</small><strong>{reportStatus?.product_count??"—"}개</strong></div>
        <div><small>공정별 가격 행</small><strong>{reportStatus?.process_rows??"—"}행</strong></div>
        <div><small>공통 공정 구조</small><strong>{reportStatus?.unique_process_definitions??"—"}종</strong></div>
        <div><small>Record ID 매핑</small><strong>{reportStatus?.linked_sfdc_record_count??"—"}건</strong></div>
        <div><small>매핑 대기</small><strong>{reportStatus?.unmapped_sfdc_record_count??"—"}건</strong></div>
      </div>
      {reportBackend==="FEISHU"&&<div className={styles.statStrip} aria-label="Oppo Quote 사전 분류 상태">
        <div><small>미리 색인한 Quote</small><strong>{referenceStatus?.status==="PASS"?referenceStatus.quote_count:"—"}건</strong></div>
        <div><small>공통 프로젝트 유형 (공정+Gb)</small><strong>{referenceStatus?.status==="PASS"?referenceStatus.project_classes:"—"}개</strong></div>
        <div><small>색인 준비</small><strong>{referenceStatus?.status==="PASS"?"PASS":"HOLD"}</strong></div>
      </div>}
      {reportBackend==="FEISHU"&&<p className={styles.hint}>사전 분류 색인: {referenceStatus?.index_freshness||referenceStatus?.code||"확인 전"} · 마지막 갱신 {kst(referenceStatus?.indexed_at_utc)} · 원본 행 해시 교차검증 {referenceStatus?.line_digest_crosschecked?"PASS":"미검증"}. Oppo–Quote 선택 시 전체 Report를 다시 분류하지 않습니다.</p>}
      <p className={styles.hint}>조회 경로: {reportBackend==="FEISHU"?"로그인된 Feishu → 검증된 로컬 검색 캐시":"Google Sheet Report 보조 캐시"} · Feishu 읽기 시각 {kst(reportStatus?.ingested_at_utc)} · QQ 메일 수신 시각 {reportStatus?.source_mail_received_kst||"미검증"} · Salesforce 공정 Report 생성 시각 별도 미확인 · KRW 단가 미검증</p>
      <div className={styles.nav}>
        <a href={FEISHU_REPORT_LINES} target="_blank" rel="noreferrer">Feishu 공정별 견적 {reportStatus?.process_rows??"—"}행</a>
        <a href={FEISHU_REPORT_PRODUCTS} target="_blank" rel="noreferrer">Product 템플릿 {reportStatus?.product_template_count??"—"}개</a>
        <a href={FEISHU_REPORT_PROCESSES} target="_blank" rel="noreferrer">공통 공정 37개</a>
      </div>
      <p className={styles.hint}>최신 Quote 생성일: {reportStatus?.latest_quote_created||reportStatus?.newest_quote_created_date||"미확인"} · Feishu 원본 상태: {reportStatus?.source_state||"미검증"} · {reportStatus?.source||"SOURCE_NOT_READY"}</p>
      <div className={styles.warning}>
        Report 금액은 **USD 환산값**입니다. KRW 원본 단가·할인·Cloud 수량·현재 Salesforce 견적은 별도 검증이 필요하며, 이 화면은 보고서 금액만으로 신규 견적을 확정하지 않습니다.
      </div>
      <form className={styles.search} onSubmit={e=>{e.preventDefault();searchReport(reportQuery);}}>
        <input aria-label="Quote Report 검색" value={reportQuery}
          onChange={e=>setReportQuery(e.target.value)}
          placeholder="Quote ID · 기관 · Contact · 공정명"/>
        <button type="submit" disabled={Boolean(reportBusy)||!reportStatus}>Report 검색</button>
        <button type="button" disabled={Boolean(reportBusy)}
          onClick={syncStagedReport}>{reportBackend==="FEISHU"?"Feishu 원본 다시 불러오기":"보조 Report 재색인"}</button>
        <button type="button" disabled={Boolean(reportBusy)}
          onClick={()=>{setReportBackend(reportBackend==="FEISHU"?"LOCAL":"FEISHU");setReportRows([]);setReportSelected(null);setReportStatus(null);setReportError("");}}>
          {reportBackend==="FEISHU"?"보조 Google Report 대조":"Feishu 원본 사용"}
        </button>
      </form>
      {reportError&&<p className={styles.warning} role="alert">Report 확인 필요: {reportError}</p>}
      <div className={styles.results} aria-label="Quote Report 검색 결과">
        {reportRows.map(item=><button type="button" key={item.qid}
          disabled={Boolean(reportBusy)} data-selected={reportSelected?.qid===item.qid}
          onClick={()=>chooseReport(item)}>
          <strong>{item.qid} · {item.product_count} Product · {item.process_lines} 공정</strong>
          <small>{[item.account_name,item.contact_name,item.created_date].filter(Boolean).join(" · ")}</small>
          <small>{item.sfdc_record_id?"Salesforce Record 연결됨":"Salesforce Record ID 매핑 대기"}</small>
        </button>)}
        {reportRows.length===0&&<p className={styles.hint}>Quote Report 데이터가 없거나 아직 검색하지 않았습니다.</p>}
      </div>
      {reportSelected&&<div className={styles.source} aria-live="polite">
        <div className={styles.inlineHead}><b>{reportSelected.qid} · Report 공정별 단가</b>
          <Status value={reportBackend==="FEISHU"?"FEISHU_REPORT_USD_ONLY":"GOOGLE_REPORT_USD_ONLY"}/></div>
        <div className={styles.tableScroll}>
          <table><thead><tr><th>Quote Product</th><th>공정</th><th>Data Unit</th>
            <th>공정 단가 (환산 USD)</th><th>생산량(Gb) 기준값</th></tr></thead>
            <tbody>{(reportSelected.process_lines||[]).map((line,i)=><tr key={i}>
              <td>{line.quotation_product_id}</td><td>{line.process_name}</td>
              <td>{line.data_unit||"—"}</td>
              <td>{line.unit_price_usd??"—"} USD</td>
              <td>{/^(?:g(?:b)?\s*(?:raw\s*data|data|produced|production)?|gigabytes?)$/i.test((line.data_unit||"").trim())?(line.data_size||"확인 필요")+" Gb":"—"}</td>
            </tr>)}</tbody></table>
        </div>
        <p className={styles.hint}>{reportSelected.sfdc_record_id
          ?"Report의 Salesforce Record ID 연결 확인 · 현재 가격이 변경됐는지는 별도 검증 필요"
          :"신규 Quote로 Report ID만 확인됨 · Salesforce Record ID 연결 검증 대기"}</p>
        <ReportOppoDraft key={reportSelected.qid} quote={reportSelected}
          enabled={reportBackend==="FEISHU"}/>
      </div>}
    </section>
    <section className={styles.panel} aria-label="Salesforce 사전 캐시">
      <div className={styles.panelHead}><span className={styles.step}>00</span>
        <div><h2>Salesforce 사전 캐시 · 빠른 조회</h2>
          <p>로컬 PC 비공개 보관 · 목록 15분 / Quote·단가 근거 20분 유효 · 만료 시 원본 재조회</p></div>
        <Status value={cacheInfo?.cache_status}/>
      </div>
      <div className={styles.statStrip}>
        <div><small>유효한 Opportunity 목록</small><strong>{cacheInfo?.tiers?.list?.fresh??"—"}개 스냅샷</strong></div>
        <div><small>유효한 연결 Quote</small><strong>{cacheInfo?.tiers?.bundle?.fresh??"—"}건</strong></div>
        <div><small>만료된 연결 Quote</small><strong>{cacheInfo?.tiers?.bundle?.stale??"—"}건</strong></div>
        <div><small>고유 Product Line 템플릿</small><strong>{cacheInfo?.product_line_dictionary?.unique_templates??"—"}개</strong></div>
        <div><small>중복 재사용 템플릿</small><strong>{cacheInfo?.product_line_dictionary?.reused_templates??"—"}개</strong></div>
        <div><small>중복 구조 절감량 (논리 데이터)</small><strong>{bytes(cacheInfo?.product_line_dictionary?.logical_bytes_saved)}</strong></div>
      </div>
      <p className={styles.hint}>동일 Product·공정 구성만 공통 저장합니다. 고객별 단가·할인·수량·Quote 금액은 별도 보관하며, 중복이 없으면 템플릿도 생성하지 않습니다. 절감량은 JSON 논리 크기 비교로 SQLite 실제 파일 크기와 다를 수 있습니다.</p>
      <p className={styles.hint}>마지막 Quote 조회: {kst(cacheInfo?.tiers?.bundle?.last_checked_at_utc)} · 수집값은 예상 견적용이며 새로운 Salesforce Quote 저장 및 최종 금액 검증에 재사용하지 않습니다.</p>
      <div className={styles.actions}>
        <button type="button" disabled={Boolean(busy)||cacheBusy} onClick={warmCache}>
          {cacheBusy?"사전 수집 중":"다음 3건 미리 수집 · 비공개 저장"}
        </button>
        <button type="button" className={styles.secondary} disabled={cacheBusy}
          onClick={loadCacheStatus}>캐시 상태 확인</button>
      </div>
      {cacheNotice&&<p className={styles.hint} role="status">{cacheNotice}</p>}
    </section>
    <section className={styles.panel}>
      <div className={styles.panelHead}><span className={styles.step}>01</span>
        <div><h2>필요할 때만 Salesforce 원본 검증</h2><p>Report에 없는 KRW 원본 단가·Cloud 구성·신규 Record ID가 필요할 때만 인증된 Salesforce 화면을 조회합니다.</p></div>
        <Status value={listStatus}/></div>
      <form className={styles.search} onSubmit={e=>{e.preventDefault();browse(query);}}>
        <input aria-label="기존 Opportunity 검색" value={query}
          onChange={e=>setQuery(e.target.value)} placeholder="Opportunity · 기관 · AMEA"/>
        <button disabled={Boolean(busy)} type="submit">Salesforce 목록 수동 조회</button>
        <button disabled={Boolean(busy)} type="button" onClick={()=>browse(query)}>새로고침</button>
      </form>
      <div className={styles.results} aria-label="Opportunity 검색 결과">
        {list.map(item=><button type="button" key={item.id}
          data-selected={form.sourceOpportunityId===item.id}
          disabled={Boolean(busy)} onClick={()=>choose(item)}>
          <strong>{item.name}</strong>
          <small>{[item.institution,item.contact,item.status].filter(Boolean).join(" · ")}</small>
        </button>)}
        {!list.length&&<p className={styles.hint}>기본 조회는 Quote Report입니다. Salesforce 실시간 목록은 위 버튼으로 필요한 경우에만 불러옵니다.</p>}
      </div>
      {source.ok&&<div className={styles.source}>
        <div className={styles.inlineHead}><b>원본 Quote</b><Status value={source.priceStatus}/></div>
        {selected?.cache&&<p className={styles.hint}>원본 조회: {selected.cache.state} · 확인 {kst(selected.cache.checked_at_utc)} · 유효 기한 {kst(selected.cache.expires_at_utc)}. 캐시값은 실시간 Salesforce 상태를 보증하지 않습니다.</p>}
        <div className={styles.sourceGrid}>
          <div><span>연결 관계</span><strong>1 Opportunity ↔ 1 Quote</strong></div>
          <div><span>Product 개수</span><strong>{source.productCount??"확인 필요"}</strong></div>
          <div><span>Source Pricing</span><strong>{source.quote.pricingStatus||"미확인"}</strong></div>
          <div><span>Product Category</span><strong>{source.quote.productCategory||"미확인"}</strong></div>
        </div>
        {source.productCount===1&&<p className={styles.hint}>기존 Product: {source.quote.productName||"검증 필요"}</p>}
        {source.productCount>1&&<div className={styles.warning}>
          다중 Product Quote입니다. 개별 Product 상세 {source.productEvidence.length}건을 읽었더라도 공정·Pack·Cloud 및 원본 금액이 완전하게 대응되기 전에는 가격을 확정하지 않습니다.
          {source.productEvidence.map((p,i)=><div key={p.productKey||i}>품목 {i+1}: {p.productName} · 상세 {p.evidenceStatus||"검증 필요"}</div>)}
        </div>}
      </div>}
    </section>

    <section className={styles.panel}>
      <div className={styles.panelHead}><span className={styles.step}>02</span>
        <div><h2>견적 조건 및 가격 검증</h2><p>단일 Product 단가 또는 품목별 원본 공정 가격을 검증한 뒤 계산합니다.</p></div>
        <Status value={result?.status}/></div>
      <div className={styles.grid}>
        <label>신규 Opportunity / Quote 동일 이름
          <input value={form.newOpportunityName} onChange={e=>set("newOpportunityName",e.target.value)}
            placeholder="기존 Opportunity와 다른 이름"/></label>
        <label>샘플 수량
          <input type="number" min="1" max="500" value={form.samples}
            onChange={e=>set("samples",Number(e.target.value))}/></label>
        <label>샘플당 Data Size (Gb)
          <input type="number" step="any" min="0.001" value={form.dataSizeGb}
            onChange={e=>set("dataSizeGb",Number(e.target.value))}/></label>
        <label>Product 단가 변경 (KRW, 선택)
          <input type="number" min="0" value={form.productUnitOverrideKrw} 
            disabled={source.productCount>1}
            placeholder={source.productCount>1?"다중 품목 합산 단가 변경 불가":"원본 단가 사용"}
            onChange={e=>set("productUnitOverrideKrw",e.target.value===""?"":Number(e.target.value))}/></label>
        <label>AliCloud 단가 변경 (KRW/100Gb, 선택)
          <input type="number" min="0" value={form.cloudUnitOverrideKrw}
            placeholder="원본 단가 사용"
            onChange={e=>set("cloudUnitOverrideKrw",e.target.value===""?"":Number(e.target.value))}/></label>
      </div>
      <div className={styles.statStrip}>
        <div><small>총 데이터량</small><strong>{Number.isFinite(totalGb)?totalGb.toLocaleString("ko-KR"):"—"} Gb</strong></div>
        <div><small>AliCloud 예상 수량</small><strong>{cloudQuantity(form.samples,form.dataSizeGb)??"—"}개</strong></div>
        <div><small>VAT 기준</small><strong>10%</strong></div>
      </div>
      <div className={styles.actions}>
        <button type="button" onClick={()=>run("CHECK_PRICE")} disabled={!source.ok||Boolean(busy)}>
          {busy==="CHECK_PRICE"?"원본 확인 중":"원본 단가·수량 계산"}
        </button>
        <button type="button" className={styles.secondary} onClick={()=>run("CHECK_FORMS")}
          disabled={!source.ok||!source.pricingReady||Boolean(busy)}>
          {busy==="CHECK_FORMS"?"입력 폼 확인 중":"Opportunity + Quote 폼 검증 (No Save)"}
        </button>
      </div>
      {result&&<section className={styles.output} aria-live="polite">
        <div className={styles.inlineHead}><strong>검증 결과 · {result.code||""}</strong><Status value={result.status}/></div>
        {result.cache&&<p className={styles.hint}>계산 근거: {result.cache.state} · 마지막 Salesforce 확인 {kst(result.cache.checked_at_utc)}. 원본 수정 여부는 별도 실시간 재조회가 필요합니다.</p>}
        {lines.length>0&&<div className={styles.tableScroll}>
          <table><thead><tr><th>Product</th><th>단가</th><th>수량</th><th>합계 (VAT 제외)</th></tr></thead>
            <tbody>{lines.map((p,i)=><tr key={i}><td>{p.product}</td><td>{money(p.unit_krw)}</td>
              <td>{p.qty}</td><td>{money(p.net_krw)}</td></tr>)}</tbody>
          </table>
        </div>}
        {result.pricing&&Object.keys(result.pricing).length>0&&<div className={styles.totals}>
          <div><span>Product 합계</span><strong>{money(result.pricing["Product Net KRW"])}</strong></div>
          <div><span>AliCloud · {result.pricing["Cloud Qty"]??"—"}개</span><strong>{money(result.pricing["Cloud Net KRW"])}</strong></div>
          <div><span>VAT 제외</span><strong>{money(result.pricing["Quote Net KRW"])}</strong></div>
          <div><span>VAT 10%</span><strong>{money(result.pricing["VAT KRW"])}</strong></div>
          <div className={styles.grand}><span>VAT 포함</span><strong>{money(result.pricing["Quote Gross KRW"])}</strong></div>
        </div>}
        {result.pricing?.["Price Status"]==="MANUAL_OVERRIDE_REVIEW_REQUIRED"&&
          <p className={styles.warning}>단가 변경이 있습니다. 사용자 승인 및 신규 Quote 최종 금액 재확인 전까지 저장 금지입니다.</p>}
        <p className={styles.hint}>원본 단가의 예상 금액이며 Salesforce 신규 Quote 금액으로 확정된 값이 아닙니다.</p>
      </section>}
    </section>

    <section className={styles.panel}>
      <div className={styles.panelHead}><span className={styles.step}>03</span>
        <div><h2>기존 저장 건의 신규 연결·금액 재조회</h2>
          <p>실제로 이미 존재하는 신규 Opportunity ID를 입력하면 연결된 Quote를 독립적으로 재검증합니다.</p></div></div>
      <div className={styles.readback}>
        <label>신규 Opportunity ID (006…)
          <input value={form.newOpportunityId} placeholder="검증할 신규 Opportunity의 실제 ID"
            onChange={e=>set("newOpportunityId",e.target.value.trim())}/></label>
        <button type="button" disabled={!source.ok||!form.newOpportunityId||Boolean(busy)}
          onClick={()=>run("CHECK_READBACK")}>
          {busy==="CHECK_READBACK"?"독립 재조회 중":"신규 Oppo ↔ Quote 재조회"}
        </button>
      </div>
      {result?.readback&&<div className={styles.readbackResult}>
        <Status value={result.status}/><b>연결 확인: {result.readback.verified?"PASS":"BLOCK"}</b>
        <span>Quote 순액: {money(result.readback.net_krw)} · Cloud: {result.readback.cloud_qty??"—"}개</span>
      </div>}
      <p className={styles.hint}>신규 생성 버튼은 의도적으로 제공하지 않습니다. Salesforce 저장, Feishu 큐 등록 및 고객 메일 발송은 이 검증 화면에서 실행되지 않습니다.</p>
    </section>

    <footer className={styles.footer}>운영 범위: 로컬 PC ↔ Salesforce 인증 세션 · GitHub Actions CI · Feishu 기존 Base / Vercel 제외</footer>
  </main>;
}
