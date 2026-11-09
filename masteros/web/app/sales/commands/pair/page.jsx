"use client";

import Link from "next/link";
import {useCallback,useEffect,useMemo,useRef,useState} from "react";
import {previewCandidate,pairWebRequest,priceLines,cloudQuantity} from "../../../../lib/sfdc-pair-workspace.mjs";
import styles from "./page.module.css";

const FEISHU_BASE="https://ocnz4cb25scn.feishu.cn/base/IpMkbUD0vaFqtYs93a3csXtdn1b?table=blkzYT2OAVQssL3Y";
const money=(x)=>Number.isSafeInteger(x)?x.toLocaleString("ko-KR")+" KRW":"검증 전";
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
  const [query,setQuery]=useState("");
  const [list,setList]=useState([]);
  const [listStatus,setListStatus]=useState("NOT_CHECKED");
  const [selected,setSelected]=useState(null);
  const [form,setForm]=useState(empty);
  const [result,setResult]=useState(null);
  const [busy,setBusy]=useState("");
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
      for(let retry=0;retry<5;retry++){
        try{
          data=await localRead("/api/sfdc/records-local",{
            resource:"opportunity",mode:"list",query:term
          });
          break;
        }catch(e){
          if(!String(e.message).includes("BUSY")||retry===4)throw e;
          await new Promise(resolve=>setTimeout(resolve,1500));
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
  useEffect(()=>{browse("");},[browse]);

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
        <h1>Opportunity → Quote 통합 검증</h1>
        <p>기존 Salesforce Quote 공정·품목별 가격 → 수량 재계산 → 신규 연결 검증</p></div>
      <div className={styles.nav}>
        <Link href="/sales/commands">기존 업무 실행</Link>
        <a href={FEISHU_BASE} target="_blank" rel="noreferrer">Feishu Base</a>
      </div>
    </header>
    <div className={styles.notice} role="status">
      <b>CHECK ONLY · Salesforce 저장 0건</b>
      <span>이 화면은 로컬 PC의 인증된 Salesforce를 조회합니다. Feishu의 기존 요청 큐는 유지되며, 이 화면에서 고객 데이터 전송·견적 발행·Salesforce 저장은 수행하지 않습니다.</span>
    </div>
    <section className={styles.panel}>
      <div className={styles.panelHead}><span className={styles.step}>01</span>
        <div><h2>기존 Opportunity 선택</h2><p>Salesforce 현재 목록에서 검색하고, 연결된 Quote를 정확히 하나만 확인합니다.</p></div>
        <Status value={listStatus}/></div>
      <form className={styles.search} onSubmit={e=>{e.preventDefault();browse(query);}}>
        <input aria-label="기존 Opportunity 검색" value={query}
          onChange={e=>setQuery(e.target.value)} placeholder="Opportunity · 기관 · AMEA"/>
        <button disabled={Boolean(busy)} type="submit">검색</button>
        <button disabled={Boolean(busy)} type="button" onClick={()=>browse(query)}>새로고침</button>
      </form>
      <div className={styles.results} aria-label="Opportunity 검색 결과">
        {list.map(item=><button type="button" key={item.id}
          data-selected={form.sourceOpportunityId===item.id}
          disabled={Boolean(busy)} onClick={()=>choose(item)}>
          <strong>{item.name}</strong>
          <small>{[item.institution,item.contact,item.status].filter(Boolean).join(" · ")}</small>
        </button>)}
        {!list.length&&<p className={styles.hint}>표시할 Opportunity가 없습니다. 현재 Salesforce 목록 필터 또는 로그인 상태를 확인하세요.</p>}
      </div>
      {source.ok&&<div className={styles.source}>
        <div className={styles.inlineHead}><b>원본 Quote</b><Status value={source.priceStatus}/></div>
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
