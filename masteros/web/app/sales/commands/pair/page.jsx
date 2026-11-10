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
  const [selected,setSelected]=useState(null);
  const [working,setWorking]=useState("");
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

  const find=useCallback(async(text="")=>{
    const token=++seq.current;
    setLastSearch(text.trim());
    setSelected(null);
    setWorking("SEARCH");
    setError("");
    try{
      const data=await read({mode:"SEARCH",query:text.trim(),limit:25});
      if(token===seq.current)setRows(data.rows||[]);
    }catch(e){
      if(token===seq.current){setRows([]);setError(e.message||"SEARCH_FAILED");}
    }finally{if(token===seq.current)setWorking("");}
  },[]);

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

  async function select(row){
    if(!indexReady||working)return;
    const token=++seq.current;
    setWorking("DETAIL");setError("");setSelected(null);
    try{
      const detail=await read({mode:"DETAIL",id:row.qid});
      if(token===seq.current)setSelected(detail);
    }catch(e){
      if(token===seq.current)setError(e.message||"DETAIL_UNAVAILABLE");
    }finally{if(token===seq.current)setWorking("");}
  }
  async function refresh(){
    if(working)return;
    const token=++seq.current;
    setWorking("REFRESH");setError("");setSelected(null);
    try{
      const result=await read({mode:"REFRESH"});
      if(result.preclassified_ready!==true)throw Error("PRECLASSIFIED_REFRESH_NOT_READY");
      const [source,index]=await Promise.all([state(),read({mode:"REFERENCE_STATUS"})]);
      if(token!==seq.current)return;
      setReportStatus(source);setReferenceStatus(index);
      if(index.quote_count!==source.quote_count||
         index.line_digest_crosschecked!==true)throw Error("PRECLASSIFIED_INDEX_MISMATCH");
      const search=await read({mode:"SEARCH",query:queryRef.current.trim(),limit:25});
      if(token===seq.current){
        setRows(search.rows||[]);
        setLastSearch(queryRef.current.trim());
      }
    }catch(e){if(token===seq.current)setError(e.message||"SOURCE_REFRESH_FAILED");
    }finally{if(token===seq.current)setWorking("");}
  }
  return <main className={styles.page}>
    <header className={styles.header}>
      <div>
        <p className={styles.eyebrow}>NOVOGENE / FEISHU SALES WORKSPACE</p>
        <h1>Opportunity → Quote 통합 검증</h1>
        <p>기존 Oppo–Quote 참고 사례를 빠르게 불러와 새 견적을 작성합니다.</p>
      </div>
      <nav className={styles.nav} aria-label="화면 이동">
        <Link href="/sales/commands/pair/advanced">기존 Salesforce 고급 검증</Link>
        <a href={BASE} rel="noreferrer" target="_blank">Feishu Quote Report</a>
      </nav>
    </header>
    <div className={styles.notice} role="status">
      <b>NEW DRAFT · NO SAVE</b>
      <span>메일 → Feishu → 사전 분류 색인에서 읽습니다. 이 화면은 Salesforce 또는 Feishu에 새 Opportunity·Quote를 저장하지 않습니다.</span>
    </div>
    <section className={styles.panel} aria-label="사전 분류 운영 현황">
      <div className={styles.panelHead}>
        <span className={styles.step}>00</span>
        <div>
          <h2>사전 분류된 Quote 검색</h2>
          <p>검색 때마다 3,905행을 다시 계산하지 않습니다. 공통 공정 구성과 생산량(Gb)으로 미리 묶인 프로젝트 유형을 재사용합니다.</p>
        </div>
        <StateTag value={indexReady?"INDEX_READY":working==="REFRESH"?"REFRESHING":"INDEX_HOLD"}/>
      </div>
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
      <form className={styles.search} onSubmit={e=>{e.preventDefault();find(queryRef.current);}}>
        <input value={query} onChange={e=>{queryRef.current=e.target.value;setQuery(e.target.value);}}
          aria-label="기존 Quote 검색" maxLength={80}
          placeholder="고객 한글 이름 · 기관 · 프로젝트명 · QID"/>
        <button type="submit" disabled={!indexReady||!!working}>
          {working==="SEARCH"?"검색 중":"기존 Quote 검색"}
        </button>
        <button type="button" disabled={!!working} onClick={refresh}>
          {working==="REFRESH"?"Feishu 재색인 중":"Feishu 사전 색인 갱신"}
        </button>
      </form>
      {error&&<p className={styles.warning} role="alert">{error}</p>}
      {lastSearch&&<p className={styles.hint} role="status">
        검색 기준: {lastSearch} · 결과 {rows.length}건
      </p>}
      <div className={styles.results} aria-label="Quote Report 검색 결과">
        {rows.map(row=><button type="button" key={row.qid}
          data-selected={selected?.qid===row.qid} disabled={!indexReady||!!working}
          onClick={()=>select(row)}>
          <strong>{row.account_name||"기관 미확인"} · {row.contact_name||"고객 미확인"}</strong>
          <small>{row.opportunity_name||"프로젝트명 미확인"}</small>
          <small>{row.qid} · Product {row.product_count}개</small>
        </button>)}
        {rows.length===0&&!working&&<p className={styles.hint}>
          사전 분류된 Quote가 없거나 검색 결과가 없습니다.
        </p>}
      </div>
    </section>
    {selected?<section className={styles.panel} aria-label="선택한 기존 Quote">
      <div className={styles.panelHead}>
        <span className={styles.step}>01</span>
        <div><h2>기존 Oppo–Quote 참고 구성</h2>
          <p>{selected.reference?.opportunityName||selected.qid} · Product {selected.product_count}개. 기존 데이터는 복제 대상이 아닌 참고 근거입니다.</p></div>
        <StateTag value={selected.reference?.preclassified?"REFERENCE_READY":"REFERENCE_HOLD"}/>
      </div>
      <ReportOppoDraft key={selected.qid} quote={selected}
        enabled={indexReady&&Boolean(selected.reference?.preclassified)}/>
    </section>:<section className={styles.panel} aria-label="견적 작성 안내">
      <div className={styles.panelHead}>
        <span className={styles.step}>01</span>
        <div><h2>새 Opportunity · Quote 작성</h2>
          <p>위에서 기존 견적을 선택하면 두 가지 Account·Contact 모드와 Product별 Gb·단가·Description 편집 화면이 나타납니다.</p>
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
      인증된 PC 전용 · Feishu의 기존 Report를 참조 · 실제 신규 저장 및 고객 메일 발송 없음
    </footer>
  </main>;
}
