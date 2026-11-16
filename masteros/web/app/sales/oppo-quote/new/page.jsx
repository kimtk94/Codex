"use client";
import {useMemo,useState} from "react";
import KrwPricePanel from "./KrwPricePanel";
import Link from "next/link";
import styles from "../page.module.css";
import {PATTERNS,UNITS,DEFAULT_INPUT,createIntake} from "../../../../lib/sfdc-new-oppo-quote.mjs";
const labels={institution:"기관",contact:"고객 한글 이름",service:"서비스",samples:"샘플 수",production:"생산량",unit:"단위"};
function kstDate(){const p=new Intl.DateTimeFormat("en-US",{timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(new Date());const v=x=>p.find(a=>a.type===x).value;return v("year")+"-"+v("month")+"-"+v("day");}
export default function NewQuote(){
 const [input,setInput]=useState({...DEFAULT_INPUT}),[notice,setNotice]=useState(""),[show,setShow]=useState(false);
 const today=kstDate();const result=useMemo(()=>createIntake(input,today),[input,today]);
 const update=(k,v)=>{setInput(s=>({...s,[k]:v}));setShow(false);setNotice("");};
 const field=(id,label,value,onChange,placeholder="")=><div className={styles.field}><label htmlFor={id}>{label}</label><input id={id} value={value} placeholder={placeholder} onChange={e=>onChange(e.target.value)}/></div>;
 const copy=async()=>{if(result.missing.length)return;try{await navigator.clipboard.writeText(JSON.stringify(result,null,2));setNotice("검토용 JSON을 복사했습니다. Salesforce에는 전송하지 않았습니다.");}catch{setShow(true);setNotice("복사 실패: 아래 JSON을 직접 확인하세요.");}};
 return <main className={styles.page}><div className={styles.container}>
  <header className={styles.header}><div className={styles.breadcrumb}><Link href="/sales/oppo-quote">기존 PMP 시범 화면</Link><span>/</span><strong>신규 Oppo·Quote 요청</strong></div>
   <div className={styles.headerBottom}><div><p className={styles.eyebrow}>SFDC · HISTORICAL REFERENCE</p><h1>신규 Oppo + Quote</h1><p className={styles.subhead}>과거 854개 Quote의 공통 공정 구조만 참고합니다. 가격·Product·Contact ID는 추정하지 않습니다.</p></div><div className={styles.statusPill}>No Save · 검토용</div></div>
  </header>
  <div className={styles.banner} role="status"><span className={styles.bannerIcon}>!</span><span>SFDC 인증 고객 조회·실제 저장은 미연결입니다. 이 화면의 요청 정보는 브라우저 내부에서만 처리합니다. 참고 Quote 번호를 적어도 실제 Quote를 자동 복제하지 않습니다.</span></div>
  <div className={styles.grid}>
   <section className={styles.panel}>
    <div className={styles.panelHeader}><span className={styles.stepNo}>01</span><div><h2>신규 견적 정보</h2><p>바뀐 사항만 입력 · 실제 고객 정보는 SFDC 확인 필요</p></div></div>
    <form onSubmit={e=>{e.preventDefault();setShow(true);setNotice(result.missing.length?"누락 입력이 있습니다.":"검토용 명세를 생성했습니다. 실제 저장은 하지 않았습니다.");}}>
     <div className={styles.two}>
      {field("new-account","기관 / Account",input.institution,v=>update("institution",v),"예: 제주대학교")}
      {field("new-contact","고객 한글 이름",input.contact,v=>update("contact",v),"예: 이태백")}
     </div>
     <div className={styles.field}><label htmlFor="new-identity">Account/Contact 관리</label><select id="new-identity" value={input.identityMode} onChange={e=>update("identityMode",e.target.value)}><option value="KEEP">기존 Account/Contact 유지</option><option value="CHANGE">Account/Contact 변경</option></select><small>실제 001/003 관계는 로그인된 Salesforce에서 재검증해야 합니다.</small></div>
     <div className={styles.two}><div className={styles.field}><label htmlFor="new-service">서비스</label><select id="new-service" value={input.service} onChange={e=>update("service",e.target.value)}><option value="">서비스 선택</option>{Object.entries(PATTERNS).map(([id,p])=><option key={id} value={id}>{p.label}</option>)}</select></div>
      {field("new-samples","샘플 수",input.samples,v=>update("samples",v),"예: 48")}
     </div>
     <div className={styles.two}>
      {field("new-production","생산량",input.production,v=>update("production",v),"예: 6")}
      <div className={styles.field}><label htmlFor="new-unit">단위</label><select id="new-unit" value={input.unit} onChange={e=>update("unit",e.target.value)}>{UNITS.map(u=><option key={u} value={u}>{u}</option>)}</select></div>
     </div>
     <div className={styles.two}>
      <div className={styles.field}><label htmlFor="new-basis">생산량 기준</label><select id="new-basis" value={input.basis} onChange={e=>update("basis",e.target.value)}><option value="PER_SAMPLE">샘플당</option><option value="TOTAL">프로젝트 전체</option></select></div>
      <div className={styles.field}><label htmlFor="new-cloud">Alicloud</label><select id="new-cloud" value={input.cloud} onChange={e=>update("cloud",e.target.value)}><option value="UNKNOWN">미확인</option><option value="YES">필요</option><option value="NO">불필요</option></select></div>
     </div>
     <div className={styles.field}><label htmlFor="new-progress">현재 확인된 단계</label><select id="new-progress" value={input.status} onChange={e=>update("status",e.target.value)}><option value="SAMPLES_EXPECTED">샘플 접수 예정</option><option value="QUOTE_REQUESTED">견적 요청</option><option value="SAMPLES_RECEIVED_CONFIRMED">실제 샘플 접수 확인</option></select></div>
     {field("new-type","샘플 종류 / 전처리 (선택)",input.sampleType,v=>update("sampleType",v),"예: human RNA / 추출 필요")}
     {field("new-reference","참고 기존 Oppo/Quote 이름·번호 (선택)",input.referenceQuote,v=>update("referenceQuote",v),"원본 조회 전에는 참고 표시만")}
     {field("new-name","신규 Oppo/Quote 공통 이름 (선택)",input.desiredName,v=>update("desiredName",v),"비우면 임시 이름 제안")}
     <div className={styles.rule}><strong>신규 생성 원칙</strong><span>Oppo = Quote 이름, Close Date +1개월, No Save</span></div>
     <div className={styles.buttons}><button className={styles.primary} type="submit">검토용 요청서 확인</button><button type="button" className={styles.secondary} onClick={()=>{setInput({...DEFAULT_INPUT});setShow(false);setNotice("");}}>초기화</button></div>
     {notice&&<div className={styles.notice} role="status">{notice}</div>}
    </form>
   </section>
   <aside className={styles.right}>
    <section className={styles.panel}><div className={styles.panelHeader}><span className={styles.stepNo}>02</span><div><h2>입력 점검</h2><p>실제 SFDC 연결·가격은 별도 확인</p></div></div>
     <div className={styles.reviewState}><span className={styles.dot}/>{result.missing.length?"필수 입력 "+result.missing.length+"개 남음":"입력 완료 · CRM 검증 보류"}</div>
     {result.missing.length>0&&<div className={styles.footnote}>입력 필요: {result.missing.map(x=>labels[x]||x).join(", ")}</div>}
     <div className={styles.metrics} style={{marginTop:18}}><div><span>샘플</span><strong>{input.samples||"—"}</strong><small>samples</small></div><div><span>총 생산량</span><strong>{result.suggested.productionTotal?.value??"—"}</strong><small>{input.unit}</small></div><div><span>Alicloud</span><strong>{result.suggested.alicloudQuantity??"—"}</strong><small>Gb 기준 시만</small></div></div>
     <div className={styles.footnote}>샘플당 생산량과 전체 생산량을 구분합니다. Gb, M reads, Lane 단위를 임의 환산하지 않습니다.</div>
    </section>
    <section className={styles.panel}><div className={styles.panelHeader}><span className={styles.stepNo}>03</span><div><h2>과거 공통 공정</h2><p>공정 구조 참고 · 단가·수량 미확정</p></div></div>
     <div className={styles.footnote}><strong>{PATTERNS[input.service]?.label||"서비스 미선택"}</strong></div>
     {result.suggested.historicalProcesses.length?<ol className={styles.pipeline}>{result.suggested.historicalProcesses.map((p,i)=><li key={p}><span className={styles.pipelineNumber}>{i+1}</span><div><strong>{p}</strong></div><small>참고</small></li>)}</ol>:<div className={styles.footnote}>공정 자동 추천 보류 · 실제 Product 확인 필요</div>}
     <div className={styles.footnote}>{result.suggested.historicalNote}</div><div className={styles.reviewState}><span className={styles.dot}/>실제 Product/Process ID, Pack 및 가격 미검증</div>
    </section>
    <section className={styles.panel}><div className={styles.panelHeader}><span className={styles.stepNo}>04</span><div><h2>명령서 검토</h2><p>원천 상태: {result.status}</p></div></div>
     <div className={styles.footnote}>Oppo = Quote: {result.suggested.opportunityName||"미정"}</div>
     <div className={styles.footnote}>Close Date (KST): {result.suggested.closeDateKst}</div>
     <button type="button" className={styles.secondary} style={{width:"100%",marginTop:16}} onClick={copy} disabled={result.missing.length>0}>JSON 복사 (로컬)</button>
     <button type="button" className={styles.disabled} disabled>Salesforce 생성 · 연결 전</button>
    </section>
   </aside>
  </div>
  <div style={{marginTop:18}}><KrwPricePanel intake={result}/></div>
  {show&&<section className={styles.output}><div className={styles.outputTop}><div><h2>검토용 JSON</h2><p>고객 정보가 포함됩니다. 공개 저장소에 올리지 마세요.</p></div></div><pre>{JSON.stringify(result,null,2)}</pre></section>}
  <footer className={styles.footer}>SFDC 신규 생성 초안 · Salesforce write 0건 · 실제 가격 자동 설정 0건</footer>
 </div></main>;
}
