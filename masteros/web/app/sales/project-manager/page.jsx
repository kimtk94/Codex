"use client";

import {useCallback,useEffect,useMemo,useState} from "react";
import Link from "next/link";
import styles from "./page.module.css";

const labels={
  ALL:"전체",ACTIVE:"진행 중",PAYMENT:"완료 → Payment",REVIEW:"검토 필요"
};
const healthLabels={
  PASS_MIRROR_ONLY:"Google 미러 기준 조회 · 원본 미검증",
  PARTIAL_MIRROR:"메일 수집 일부 미완료 · 원본 미검증",
  STALE:"데이터 갱신 지연",SOURCE_UNAVAILABLE:"원천 접근 불가"
};
const feishu="https://ocnz4cb25scn.feishu.cn/base/IpMkbUD0vaFqtYs93a3csXtdn1b?table=tblTZe5tkRUeOHM8";
const when=value=>{
  if(!value)return "확인 불가";
  const t=new Date(value);
  if(Number.isNaN(t.getTime()))return value;
  return new Intl.DateTimeFormat("ko-KR",{
    timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit",
    hour:"2-digit",minute:"2-digit",hour12:false,
  }).format(t)+" KST";
};
function Progress({value}){
  if(typeof value!=="number")return <span className={styles.dim}>미확인</span>;
  return <div className={styles.progress} title="CSS 과거 미러 진행률 · Feishu 실시간값 아님">
    <span><i style={{width:Math.max(0,Math.min(100,value))+"%"}}/></span>
    <small>{value}% · CSS</small>
  </div>;
}
function MiniMetric({label,value,sub,onClick,active}){
  return <button type="button" className={styles.metric} data-active={active}
    onClick={onClick}><span>{label}</span><strong>{value??"—"}</strong><small>{sub}</small></button>;
}
export default function ProjectManager(){
  const [data,setData]=useState(null);
  const [fetching,setFetching]=useState(false);
  const [error,setError]=useState("");
  const [tab,setTab]=useState("ACTIVE");
  const [stage,setStage]=useState("ALL");
  const [search,setSearch]=useState("");
  const [selected,setSelected]=useState("");
  const [sort,setSort]=useState("ACTION");
  const load=useCallback(async()=>{
    setFetching(true);setError("");
    try{
      const response=await fetch("/api/css/project-manager",{
        headers:{"X-CSS-Local-Projects":"1"},credentials:"omit",cache:"no-store"
      });
      const body=await response.json();
      if(!response.ok)throw new Error(body.reason||"원천 접근 실패");
      if(!Array.isArray(body.project_rows))throw new Error("프로젝트 스키마 오류");
      setData(body);
    }catch(e){
      setData(null);setError(e.message||"원천 접근 실패");
    }finally{setFetching(false);}
  },[]);
  useEffect(()=>{load();},[load]);
  const rows=data?.project_rows||[];
  const filtered=useMemo(()=>{
    const needle=search.trim().toLocaleLowerCase();
    const result=rows.filter(r=>{
      const matchesTab=tab==="ALL"||(tab==="REVIEW"?r.needs_review:r.bucket===tab);
      if(!matchesTab||(stage!=="ALL"&&r.stage_group!==stage))return false;
      return !needle||[r.quote_name,r.amea,r.project_id,r.institution,r.contact,r.service]
        .some(v=>String(v||"").toLocaleLowerCase().includes(needle));
    });
    return result.sort((a,b)=>{
      if(sort==="NAME")return (a.quote_name||a.project_id).localeCompare(b.quote_name||b.project_id,"ko");
      if(sort==="STAGE")return a.stage_group.localeCompare(b.stage_group,"ko");
      if(sort==="ETA")return (a.expected_completion||"9999").localeCompare(b.expected_completion||"9999");
      const urgency=x=>(x.outstanding_state?.toUpperCase()==="YES"?0:
        x.needs_review?1:x.bucket==="PAYMENT"?2:3);
      return urgency(a)-urgency(b)||(a.quote_name||a.project_id).localeCompare(b.quote_name||b.project_id,"ko");
    });
  },[rows,tab,stage,search,sort]);
  const focus=rows.find(r=>r.project_id===selected);
  const stages=useMemo(()=>Object.entries(data?.stage_counts||{})
    .sort((a,b)=>b[1]-a[1]),[data]);
  const kpi=data?.counts||{};
  return <main className={styles.page}>
    <header className={styles.header}>
      <div><p className={styles.eyebrow}>NOVOGENE · LOCAL PROJECT OPERATIONS</p>
        <h1>프로젝트 관리</h1>
        <p>Quote Name 중심 · 공정 추적 · SIF/PO · 완료 후 Payment</p>
      </div>
      <nav className={styles.links}>
        <Link href="/sales/commands">영업 업무</Link>
        <Link href="/sales/oppo-quote">Oppo · Quote</Link>
        <Link href="/sales/projects">프로젝트 원본 비교</Link>
        <a href={feishu} target="_blank" rel="noreferrer">Feishu 원본</a>
        <button disabled={fetching} onClick={load} type="button">{fetching?"조회 중":"새로고침"}</button>
      </nav>
    </header>

    <section className={styles.source} aria-live="polite">
      <div className={styles.sourceMain}>
        <span className={styles.health} data-health={data?.status||"SOURCE_UNAVAILABLE"}>
          {healthLabels[data?.status]||"원천 미조회"}
        </span>
        <span>SFDC Save 없음 · 원본 수정 없음 · 결제 완료 자동 판단 없음</span>
      </div>
      <div className={styles.sourceTimes}>
        <span>Feishu 미러 수집 {when(data?.source_synced_at)}</span>
        <span>Quote 목록 {when(data?.quote_mirror_latest_at)}</span>
        <span>CSS SIF 기록 {when(data?.sif_mirror_latest_at)}</span>
        <span>Payment 미러 {when(data?.payment_mirror_latest_at)}</span>
        <span>조회 {when(data?.checked_at)}</span>
      </div>
      <p>{error?"조회 실패: "+error:
        "Google Sheets 미러 간 상태를 보여줍니다. QQ·Feishu·SFDC 원본 직접 검증은 별개이며, Quote 명칭이나 결제 증빙이 확인되지 않은 건은 확정하지 않습니다."}</p>
      <p className={styles.sourceWarning}>Quote·SIF 표기 시각은 각 자료의 <strong>마지막 기록 발생 시각</strong>이며, 원본 최신 동기화 증거가 아닙니다.
        신규 건이 없어서 기록이 오래된 경우와 수집이 중단된 경우는 별도 원본 확인 전까지 구분할 수 없습니다.</p>
    </section>

    <section className={styles.metrics} aria-label="프로젝트 관리 요약">
      <MiniMetric label="진행 중" value={kpi.active} sub="생산·납품 전" active={tab==="ACTIVE"}
        onClick={()=>setTab("ACTIVE")}/>
      <MiniMetric label="완료 → Payment" value={kpi.payment} sub="완료 근거 존재" active={tab==="PAYMENT"}
        onClick={()=>setTab("PAYMENT")}/>
      <MiniMetric label="확인 필요" value={kpi.review} sub="Quote/상태/원문" active={tab==="REVIEW"}
        onClick={()=>setTab("REVIEW")}/>
      <MiniMetric label="Quote 연결" value={kpi.quote_linked} sub={"전체 "+(kpi.total??"—")+"건 중"}
        active={tab==="ALL"} onClick={()=>setTab("ALL")}/>
    </section>

    <section className={styles.main}>
      <div className={styles.sectionHeader}>
        <div><h2>프로젝트 목록</h2>
          <p>서브프로젝트 X번호로 개별 추적 · 동일 AMEA에서 검증된 Quote Name 재사용</p></div>
        <b>{filtered.length} / {rows.length}건</b>
      </div>
      <div className={styles.tabs} role="group" aria-label="프로젝트 상태">
        {Object.entries(labels).map(([id,label])=>
          <button key={id} className={tab===id?styles.current:""} type="button"
            onClick={()=>{setTab(id);setSelected("");}}>{label}</button>
        )}
      </div>
      <div className={styles.filters}>
        <label>Quote · 기관 · 고객 · AMEA · X번호
          <input type="search" placeholder="Quote 이름 또는 기관/고객 검색"
            value={search} onChange={e=>setSearch(e.target.value)}/>
        </label>
        <label>공정
          <select value={stage} onChange={e=>setStage(e.target.value)}>
            <option value="ALL">전체 공정</option>
            {stages.map(([label,count])=>
              <option key={label} value={label}>{label} ({count})</option>
            )}
          </select>
        </label>
        <label>정렬
          <select value={sort} onChange={e=>setSort(e.target.value)}>
            <option value="ACTION">미수·검토 우선</option>
            <option value="ETA">예상 완료 순</option>
            <option value="NAME">Quote Name 순</option>
            <option value="STAGE">공정 순</option>
          </select>
        </label>
      </div>

      <div className={styles.tableScroll}>
        <table><thead><tr>
          <th>Quote Name / 프로젝트 ID</th><th>기관 · 고객</th>
          <th>공정</th><th>진행률</th><th>시료</th><th>SIF</th>
          <th>PO</th><th>예상 완료</th><th>다음 조치</th><th>상세</th>
        </tr></thead><tbody>
        {filtered.map(r=><tr key={r.project_id} data-bucket={r.bucket}>
          <td className={styles.quoteCell}>
            <strong>{r.quote_name||"Quote 이름 미연결"}</strong>
            <small>{r.project_id} · {r.amea||"AMEA 미확인"}</small>
            {r.quote_match_state!=="APPROVED_AMEA_MIRROR"&&
              <em>{r.quote_match_state==="MULTIPLE_QUOTE_REVIEW"?"다중 Quote 확인 필요":"원본 Quote 미연결"}</em>}
          </td>
          <td><span>{r.institution||"기관 미확인"}</span>
            <small>{r.contact||"Contact 미연결"}</small></td>
          <td><span className={styles.stage}>{r.stage_group}</span>
            <small>{r.stage}</small></td>
          <td><Progress value={r.progress_percent}/></td>
          <td>{r.sample_count||"—"}</td>
          <td><span className={r.sif_state==="제출 확인"?styles.confirmed:styles.dim}>
            {r.sif_state}</span></td>
          <td><small>{r.po_state}</small></td>
          <td>{r.expected_completion||"—"}</td>
          <td className={styles.actionCell}>{r.next_action}</td>
          <td><button className={styles.detailButton} type="button"
            onClick={()=>setSelected(r.project_id===selected?"":r.project_id)}>
            {r.project_id===selected?"닫기":"상세"}
          </button></td>
        </tr>)}
        </tbody></table>
        {!filtered.length&&<p className={styles.empty}>
          {fetching?"프로젝트 조회 중":error?"원천 연결 실패":"선택 조건의 프로젝트가 없습니다."}
        </p>}
      </div>
    </section>

    {focus&&<section className={styles.details} aria-label="선택 프로젝트 상세">
      <div className={styles.detailHeader}>
        <div><p className={styles.eyebrow}>PROJECT DETAIL · READ ONLY</p>
          <h2>{focus.quote_name||"Quote 미연결"}</h2>
          <p>{focus.project_id} · {focus.amea}</p></div>
        <button type="button" onClick={()=>setSelected("")}>닫기</button>
      </div>
      <div className={styles.detailGrid}>
        <div><span>현재 공정 / CSS 이전 기록</span><strong>{focus.stage}</strong>
          <p>{focus.legacy_stage||"이전 공정 미확인"}</p></div>
        <div><span>견적 연결 상태</span><strong>{focus.quote_match_state}</strong>
          <p>원문이 확인되지 않으면 Quote 이름을 대입하지 않습니다.</p></div>
        <div><span>시료 / SIF</span><strong>{focus.sample_count||"미확인"} · {focus.sif_state}</strong>
          <p>{focus.prepayment?"Prepayment: SIF 미제출만으로 팔로업 금지":"SIF 원문 제출 증거 기준"}</p></div>
        <div><span>PO / Invoice</span><strong>{focus.po_state}</strong>
          <p>Invoice 건수 {focus.invoice_count||"—"} · 금액은 검증 전 표시하지 않음</p></div>
        <div><span>Payment</span><strong>{focus.outstanding_state==="YES"?"미수금 표기 있음":"미수금 원문 확인 필요"}</strong>
          <p>{focus.receipt_state}; 미수금 NO ≠ 입금 증명</p></div>
        <div><span>권장 다음 조치</span><strong>{focus.next_action}</strong>
          <p>자동 발송·수정·SFDC Save를 수행하지 않습니다.</p></div>
      </div>
    </section>}
    <footer className={styles.footer}>
      <span>완료 프로젝트는 Payment 화면에서 관리합니다. 결제 완료 보관은 실제 입금 증빙이 확인된 이후에만 가능합니다.</span>
      <span>프로젝트 원본과 로컬 미러의 최신성은 별도 검증</span>
    </footer>
  </main>;
}
