"use client";

import Link from "next/link";
import {useCallback,useEffect,useRef,useState} from "react";
import styles from "./page.module.css";
import ReportOppoDraft from "./ReportOppoDraft";

const ENDPOINT="/api/sfdc/feishu-report-local";
const BASE="https://ocnz4cb25scn.feishu.cn/base/IpMkbUD0vaFqtYs93a3csXtdn1b?table=tblHme64Ccdj4Fwv";
const kst=value=>value?new Date(value).toLocaleString("ko-KR",{
  timeZone:"Asia/Seoul",hour12:false
}):"확인 전";

async function read(body){
  const res=await fetch(ENDPOINT,{
    method:"POST",cache:"no-store",credentials:"omit",
    headers:{"Content-Type":"application/json","X-SFDC-Command":"1"},
    body:JSON.stringify(body)
  });
  const data=await res.json();
  if(!res.ok||data.status!=="PASS")throw Error(data.code||"FEISHU_REFERENCE_UNAVAILABLE");
  return data;
}
async function state(){
  const r=await fetch(ENDPOINT,{
    cache:"no-store",credentials:"omit",headers:{"X-SFDC-Command":"1"}
  });
  const data=await r.json();
  if(!r.ok||data.status!=="PASS")throw Error(data.code||"FEISHU_SOURCE_UNAVAILABLE");
  return data;
}
function StateTag({value}){
  const ok=value==="PASS"||value==="INDEX_READY"||value==="REFERENCE_READY";
  return <span className={styles.state} data-ok={ok}>{value||"HOLD"}</span>;
}
export default function PairedQuoteWeb(){
  const [reportStatus,setReportStatus]=useState(null);
  const [referenceStatus,setReferenceStatus]=useState(null);
  const [query,setQuery]=useState("");
  const [rows,setRows]=useState([]);
  const [selectionMode,setSelectionMode]=useState("OPPORTUNITY");
  const [selectedOppo,setSelectedOppo]=useState(null);
  const [quoteChoices,setQuoteChoices]=useState([]);
  const [selected,setSelected]=useState(null);
  const [working,setWorking]=useState("");
  const [parallelBusy,setParallelBusy]=useState(false);
  const [parallelResult,setParallelResult]=useState(null);
  const [error,setError]=useState("");
  const mounted=useRef(false);
  const seq=useRef(0);
  const queryRef=useRef("");
  const [lastSearch,setLastSearch]=useState("");
  const indexReady=reportStatus?.status==="PASS"&&
    referenceStatus?.status==="PASS"&&
    referenceStatus?.line_digest_crosschecked===true&&
    referenceStatus?.quote_count===reportStatus?.quote_count&&
    referenceStatus?.source_mail_received_kst===reportStatus?.source_mail_received_kst;

  const find=useCallback(async(text="",mode=selectionMode)=>{
    const token=++seq.current;
    setLastSearch(text.trim());
    setSelected(null);setSelectedOppo(null);setQuoteChoices([]);
    setWorking("SEARCH");
    setError("");
    try{
      const exactQid=mode==="QUOTE"&&/^QID-[0-9-]{8,50}$/.test(text.trim());
      if(exactQid){
        // A QID is an exact immutable identity. Avoid an unnecessary and
        // sometimes empty fuzzy-search result list; open its verified Detail.
        const detail=await read({mode:"DETAIL",id:text.trim()});
        if(detail.qid!==text.trim())throw Error("QUOTE_QID_DETAIL_MISMATCH");
        if(token===seq.current){
          setRows([{qid:detail.qid,
            sfdc_record_id:detail.sfdc_record_id||"",
            account_name:detail.reference?.accountName||"",
            contact_name:detail.reference?.contactName||"",
            opportunity_name:detail.reference?.opportunityName||"",
            product_count:detail.product_count}]);
          setSelected(detail);
        }
      }else{
        const data=await read({mode:mode==="OPPORTUNITY"?"OPPORTUNITY_SEARCH":"SEARCH",query:text.trim(),limit:25});
        if(token===seq.current)setRows(data.rows||[]);
      }
    }catch(e){
      if(token===seq.current){setRows([]);setError(e.message||"SEARCH_FAILED");}
    }finally{if(token===seq.current)setWorking("");}
  },[selectionMode]);

  const initialize=useCallback(async()=>{
    setError("");
    try{
      const [source,index]=await Promise.all([
        state(),read({mode:"REFERENCE_STATUS"})
      ]);
      setReportStatus(source);
      setReferenceStatus(index);
      if(index.quote_count!==source.quote_count||
         index.line_digest_crosschecked!==true||
         index.source_mail_received_kst!==source.source_mail_received_kst)
        throw Error("PRECLASSIFIED_INDEX_MISMATCH");
      // Initial empty-list load must never replace a user-entered search.
      if(!queryRef.current.trim())await find("");
    }catch(e){
      setError(e.message||"FEISHU_PREINDEX_UNAVAILABLE");
    }
  },[find]);

  useEffect(()=>{
    if(mounted.current)return;
    mounted.current=true;
    initialize();
  },[initialize]);

  async function select(row,expectedExternal=""){
    if(!indexReady||working)return;
    const token=++seq.current;
    setWorking("DETAIL");setError("");setSelected(null);
    try{
      const detail=await read({mode:"DETAIL",id:row.qid});
      const external=expectedExternal||selectedOppo?.opportunity_external||"";
      if(external&&detail.reference?.opportunityExternalId!==external)
        throw Error("SOURCE_OPPO_QUOTE_LINK_MISMATCH");
      if(token===seq.current)setSelected(detail);
    }catch(e){
      if(token===seq.current)setError(e.message||"DETAIL_UNAVAILABLE");
    }finally{if(token===seq.current)setWorking("");}
  }
  async function selectOppo(row){
    if(!indexReady||working)return;
    const token=++seq.current;
    setWorking("OPPORTUNITY_QUOTES");setError("");
    setSelected(null);setSelectedOppo(null);setQuoteChoices([]);
    try{
      if(row.group_status!=="PASS")throw Error(row.group_status||"OPPO_PARENT_HOLD");
      const data=await read({mode:"OPPORTUNITY_QUOTES",
        opportunityExternal:row.opportunity_external});
      if(data.opportunity_external!==row.opportunity_external||
         data.quote_count!==data.quotes?.length||!data.quotes.length)
        throw Error("OPPO_QUOTE_LIST_MISMATCH");
      if(token!==seq.current)return;
      setSelectedOppo(row);
      if(data.quotes.length===1){
        // An unambiguous single linked Quote can fill the same draft immediately.
        const detail=await read({mode:"DETAIL",id:data.quotes[0].qid});
        if(detail.qid!==data.quotes[0].qid||
           detail.reference?.opportunityExternalId!==row.opportunity_external)
          throw Error("SOURCE_OPPO_QUOTE_LINK_MISMATCH");
        if(token===seq.current)setSelected(detail);
      }else{
        // Preserve every linked Quote as an explicit choice.
        setQuoteChoices(data.quotes);
      }
    }catch(e){
      if(token===seq.current){
        setSelectedOppo(null);setQuoteChoices([]);
        setError(e.message||"OPPO_QUOTES_UNAVAILABLE");
      }
    }finally{if(token===seq.current)setWorking("");}
  }
  function changeSelectionMode(mode){
    if(mode===selectionMode||working)return;
    setSelectionMode(mode);setRows([]);setSelected(null);
    setSelectedOppo(null);setQuoteChoices([]);setError("");
    find(queryRef.current,mode);
  }
  async function refresh(){
    if(working)return;
    const token=++seq.current;
    setWorking("REFRESH");setError("");setSelected(null);
    setSelectedOppo(null);setQuoteChoices([]);setRows([]);
    try{
      const result=await read({mode:"REFRESH"});
      if(result.preclassified_ready!==true)throw Error("PRECLASSIFIED_REFRESH_NOT_READY");
      const [source,index]=await Promise.all([state(),read({mode:"REFERENCE_STATUS"})]);
      if(token!==seq.current)return;
      setReportStatus(source);setReferenceStatus(index);
      if(index.quote_count!==source.quote_count||
         index.line_digest_crosschecked!==true)throw Error("PRECLASSIFIED_INDEX_MISMATCH");
      const search=await read({mode:selectionMode==="OPPORTUNITY"?"OPPORTUNITY_SEARCH":"SEARCH",query:queryRef.current.trim(),limit:25});
      if(token===seq.current){
        setRows(search.rows||[]);
        setLastSearch(queryRef.current.trim());
      }
    }catch(e){if(token===seq.current)setError(e.message||"SOURCE_REFRESH_FAILED");
    }finally{if(token===seq.current)setWorking("");}
  }
  async function verifyParallel(){
    if(parallelBusy)return;
    const ids=[selected?.sfdc_record_id,
      ...rows.map(x=>x.sfdc_record_id||"")].filter(x=>
        typeof x==="string"&&/^a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/.test(x));
    const unique=[...new Set(ids)].slice(0,3);
    if(!unique.length){setParallelResult({status:"HOLD",code:"QUOTE_NATIVE_IDS_UNAVAILABLE"});return;}
    setParallelBusy(true);setParallelResult(null);
    try{
      const r=await fetch("/api/sfdc/parallel-check-local",{
        method:"POST",cache:"no-store",credentials:"omit",
        headers:{"Content-Type":"application/json","X-SFDC-Command":"1"},
        body:JSON.stringify({mode:"QUOTE_UI_BATCH",recordIds:unique})
      });
      const data=await r.json();
      setParallelResult(data);
    }catch(e){setParallelResult({status:"HOLD",code:e.message||"PARALLEL_SOURCE_UNAVAILABLE"})}
    finally{setParallelBusy(false)}
  }

  return <main className={styles.page}>
    <header className={styles.header}>
      <div>
        <p className={styles.eyebrow}>NOVOGENE / FEISHU SALES WORKSPACE</p>
        <h1>Oppo + Quote 간편 생성</h1>
        <p>기존 Opportunity 선택 → 필요한 부분만 수정 → 금액 확인 → 실제 저장</p>
      </div>
      <nav className={styles.nav} aria-label="화면 이동">
        <Link href="/sales/commands">영업 홈</Link>
        <Link href="/sales/projects">프로젝트 관리</Link>
        <Link href="/sales/mail">메일 · Lead</Link>
        <a href={BASE} rel="noreferrer" target="_blank">Quote 원본 Report</a>
      </nav>
    </header>
    <div className={styles.notice} role="status">
      <b>실제 SFDC 저장 지원 · 건별 승인</b>
      <span>기존 Oppo·Quote에서 고객·Product·KRW 단가를 자동 조회합니다.
        저장 직전에 다시 검증하고 최종 확인한 건만 Salesforce에 생성합니다.</span>
    </div>
    <section className={styles.panel} aria-label="사전 분류 운영 현황">
      <div className={styles.panelHead}>
        <span className={styles.step}>00</span>
        <div>
          <h2>① 기존 Opportunity 찾기</h2>
          <p>고객 이름·기관·프로젝트로 검색하세요. 기존 Oppo에 연결된 Quote를 자동 사용하고,
            여러 개일 때만 기준 Quote를 한 번 선택합니다.</p>
        </div>
        <StateTag value={indexReady?"INDEX_READY":working==="REFRESH"?"REFRESHING":"INDEX_HOLD"}/>
      </div>
      <details className={styles.subsection} data-testid="source-index-advanced">
        <summary>원본 Report 최신성·색인 통계 (선택)</summary>
      <div className={styles.statStrip}>
        <div><small>사전 색인 Quote</small><strong>{indexReady?referenceStatus.quote_count:"—"}건</strong></div>
        <div><small>공통 프로젝트 유형</small><strong>{indexReady?referenceStatus.project_classes:"—"}개</strong></div>
        <div><small>Feishu 공정·가격 행</small><strong>{reportStatus?.process_rows??"—"}행</strong></div>
        <div><small>고객 ID 미매핑</small><strong>{reportStatus?.unmapped_sfdc_record_count??"—"}건</strong></div>
      </div>
      <p className={styles.hint}>
        QQ 메일 수신: {reportStatus?.source_mail_received_kst||"미확인"}
        {" · "}Feishu 색인 갱신: {kst(referenceStatus?.indexed_at_utc)}
        {" · "}원본 해시 교차 검증: {referenceStatus?.line_digest_crosschecked?"PASS":"HOLD"}
        {" · "}Salesforce Report 생성 시각: 미확인
      </p>
      </details>
      <div className={styles.actions} role="group" aria-label="원본 선택 유형">
        <button type="button" aria-pressed={selectionMode==="OPPORTUNITY"}
          onClick={()=>changeSelectionMode("OPPORTUNITY")} disabled={!!working}>
          기존 Opportunity 선택
        </button>
        <button type="button" aria-pressed={selectionMode==="QUOTE"}
          onClick={()=>changeSelectionMode("QUOTE")} disabled={!!working}>
          기존 Quote 선택
        </button>
      </div>
      <form className={styles.search} onSubmit={e=>{e.preventDefault();
        // Take the actual input value even if the user typed during hydration.
        const typed=e.currentTarget.querySelector("input")?.value??queryRef.current;
        queryRef.current=typed;setQuery(typed);find(typed);
      }}>
        <input value={query} onChange={e=>{queryRef.current=e.target.value;setQuery(e.target.value);}}
          aria-label={selectionMode==="QUOTE"?"기존 Quote 검색":"기존 Opportunity 검색"} maxLength={80}
          placeholder="고객 한글 이름 · 기관 · 프로젝트명 · QID (정확 일치 시 상세 바로 열기)"/>
        <button type="submit" disabled={!indexReady||!!working}>
          {working==="SEARCH"?"검색 중":selectionMode==="QUOTE"?"기존 Quote 검색":"기존 Oppo 검색"}
        </button>
        <button type="button" disabled={!!working} onClick={refresh}>
          {working==="REFRESH"?"Feishu 재색인 중":"Feishu 사전 색인 갱신"}
        </button>
      </form>
      <details className={styles.subsection} data-testid="parallel-audit-advanced">
        <summary>기존 Quote 병렬 재검증 (필요할 때만)</summary>
      <div className={styles.actions}>
        <button type="button" disabled={parallelBusy||!!working} onClick={verifyParallel}
          data-testid="parallel-quote-readonly-check">
          {parallelBusy?"최대 3개 탭 병렬 검증 중":"기존 Quote 최대 3건 병렬 확인 (저장 없음)"}
        </button>
        {parallelResult&&<span className={styles.state}
          data-ok={parallelResult.status==="PASS"}>
          {parallelResult.status} · {parallelResult.results?.length||0}건 ·
          {parallelResult.durationMs?Math.round(parallelResult.durationMs/1000)+"초":parallelResult.code||""}
        </span>}
      </div>
      {parallelResult?.results?.length>0&&<p className={styles.hint} role="status">
        {parallelResult.results.map(x=>x.status).join(" · ")}
        {" · "}독립 Chrome 탭(최대 3개) · Salesforce 저장 없음
      </p>}
      </details>
      {error&&<p className={styles.warning} role="alert">{error}</p>}
      {lastSearch&&<p className={styles.hint} role="status">
        검색 기준: {lastSearch} · 결과 {rows.length}건
      </p>}
      <div className={styles.results} aria-label={selectionMode==="QUOTE"?"Quote Report 검색 결과":"Opportunity 검색 결과"}>
        {rows.map(row=><button type="button"
          key={selectionMode==="QUOTE"?row.qid:row.opportunity_external}
          data-selected={selectionMode==="QUOTE"?selected?.qid===row.qid:
            selectedOppo?.opportunity_external===row.opportunity_external}
          disabled={!indexReady||!!working||(
            selectionMode==="OPPORTUNITY"&&row.group_status!=="PASS")}
          onClick={()=>selectionMode==="QUOTE"?select(row):selectOppo(row)}>
          <strong>{row.account_name||"기관 미확인"} · {row.contact_name||"고객 미확인"}</strong>
          <small>{row.opportunity_name||"프로젝트명 미확인"}</small>
          <small>{selectionMode==="QUOTE"?
            row.qid+" · Product "+row.product_count+"개":
            row.opportunity_external+" · 연결된 Quote "+row.quote_count+"개"+
            (row.group_status!=="PASS"?" · 관계 검증 HOLD":"")+
            (row.identity_evidence!=="PASS"?" · 고객 ID 재검증":"")}</small>
        </button>)}
        {rows.length===0&&!working&&<p className={styles.hint}>
          선택 가능한 기존 {selectionMode==="QUOTE"?"Quote":"Oppo"}가 없거나 검색 결과가 없습니다.
        </p>}
      </div>
      {selectedOppo&&quoteChoices.length>1&&
        <div className={styles.results} aria-label="선택한 Opportunity의 Quote 선택">
          <p className={styles.hint}>
            {selectedOppo.opportunity_name}에 연결된 {quoteChoices.length}개 Quote 중
            신규 견적의 기준으로 사용할 하나를 선택하세요.
          </p>
          {quoteChoices.map(item=><button type="button" key={item.qid}
            disabled={!!working} onClick={()=>select(item,selectedOppo.opportunity_external)}>
            <strong>{item.qid}</strong>
            <small>기존 Quote의 공정·제품·생산량(Gb)·고객 정보를 초안으로 가져오기</small>
          </button>)}
        </div>}
    </section>
    {selected?<section className={styles.panel} aria-label="선택한 기존 Quote">
      <div className={styles.panelHead}>
        <span className={styles.step}>01</span>
        <div><h2>② 확인하고 Oppo + Quote 생성하기</h2>
          <p>{selected.reference?.opportunityName||selected.qid} · Product {selected.product_count}개.
            기존 고객·서비스·단가를 자동 불러옵니다. 원본 레코드는 변경하지 않습니다.</p></div>
        <StateTag value={selected.reference?.preclassified?"REFERENCE_READY":"REFERENCE_HOLD"}/>
      </div>
      <ReportOppoDraft key={selected.qid} quote={selected}
        enabled={indexReady&&Boolean(selected.reference?.preclassified)}/>
    </section>:<section className={styles.panel} aria-label="견적 작성 안내">
      <div className={styles.panelHead}>
        <span className={styles.step}>01</span>
        <div><h2>② 신규 Oppo + Quote</h2>
          <p>기존 Opportunity를 선택하면 고객과 견적 정보를 자동으로 불러옵니다. 바꿀 사항만 수정한 뒤 생성하세요.</p>
        </div>
      </div>
      <div className={styles.sourceGrid}>
        <div><span>Account / Contact</span><strong>유지 또는 변경</strong></div>
        <div><span>Product 구분</span><strong>공정 + 생산량(Gb)</strong></div>
        <div><span>신규 가격</span><strong>샘플당 KRW · VAT 10%</strong></div>
        <div><span>Description</span><strong>날짜·Gb·수량·단가 편집</strong></div>
      </div>
    </section>}
    <footer className={styles.footer}>
      인증된 PC 전용 · Feishu Report 및 SFDC 원본 교차 검증 · 실제 저장은 건별 최종 승인 · 고객 메일 자동 발송 없음
    </footer>
  </main>;
}
