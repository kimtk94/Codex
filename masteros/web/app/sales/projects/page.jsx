"use client";

import {useCallback,useEffect,useMemo,useState} from "react";
import Link from "next/link";
import styles from "./page.module.css";

const timeKst=value=>{
  if(!value)return "미확인";
  const date=new Date(value);
  if(Number.isNaN(date.getTime()))return "미확인";
  return new Intl.DateTimeFormat("ko-KR",{
    timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit",
    hour:"2-digit",minute:"2-digit",hour12:false,
  }).format(date)+" KST";
};
const descriptions={
  PASS_MIRROR_ONLY:"데이터 검증 PASS",
  SINK_LAG:"데이터 불일치",
  STALE:"동기화 지연",
  SOURCE_UNAVAILABLE:"원천 접근 불가",
};
function Metric({name,value,detail}){
  return <div className={styles.metric}><span>{name}</span>
    <strong>{value??"—"}</strong><small>{detail}</small></div>;
}

export default function CssProjectsLocal(){
  const [data,setData]=useState(null);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");
  const [query,setQuery]=useState("");
  const [stage,setStage]=useState("ALL");
  const refresh=useCallback(async()=>{
    setLoading(true);setError("");
    try{
      const response=await fetch("/api/css/projects-local",{
        cache:"no-store",credentials:"omit",headers:{"X-CSS-Local-Projects":"1"}
      });
      const result=await response.json();
      if(!response.ok)throw new Error(result.reason||result.status||"조회 실패");
      if(!Array.isArray(result.project_rows))throw new Error("자료 형식 검증 실패");
      setData(result);
    }catch(err){
      setError(err?.message||"연결 실패");
      setData(null);
    }finally{setLoading(false)}
  },[]);
  useEffect(()=>{refresh()},[refresh]);
  const projects=data?.project_rows||[];
  const stages=useMemo(()=>Object.entries(data?.stage_counts||{}).sort((a,b)=>b[1]-a[1]),[data]);
  const visible=useMemo(()=>{
    const needle=query.trim().toLocaleLowerCase();
    return projects.filter(row=>(stage==="ALL"||stage===row.stage)&&
      (!needle||[row.project_id,row.amea,row.institution,row.service]
        .some(field=>String(field||"").toLocaleLowerCase().includes(needle))));
  },[projects,stage,query]);
  const status=data?.status||"SOURCE_UNAVAILABLE";
  return <main className={styles.wrap}>
    <header className={styles.header}>
      <div>
        <p className={styles.eyebrow}>NOVOGENE · LOCAL OPERATIONS</p>
        <h1>CSS 프로젝트</h1>
        <p>프로젝트 현황 · 검색 · Health Check</p>
      </div>
      <div className={styles.actions}>
        <Link href="/sales/commands">업무 실행</Link>
        <button type="button" onClick={refresh} disabled={loading}>
          {loading?"동기화 확인 중":"새로고침"}
        </button>
      </div>
    </header>

    <section className={styles.statusCard} aria-live="polite">
      <div className={styles.statusRow}>
        <span className={styles.status} data-status={status}>{descriptions[status]||status}</span>
        <span>Health Check</span>
      </div>
      <div className={styles.timestamps}>
        <span>최종 수집: {timeKst(data?.source_synced_at)}</span>
        <span>최종 반영: {timeKst(data?.sink_generated_at)}</span>
        <span>재조회: {timeKst(data?.checked_at)}</span>
      </div>
      <p className={styles.caution}>
        {error?"조회 실패: "+error:
        status==="SINK_LAG"?"원천과 내보내기 결과가 일치하지 않습니다. 운영에 사용하기 전에 동기화가 필요합니다.":
        status==="STALE"?"원천이나 결과 갱신이 지연됐습니다. 최신화 후 확인하세요.":
        "프로젝트 상태는 최종 검증 시각을 기준으로 표시합니다."}
      </p>
    </section>

    <section className={styles.metrics}>
      <Metric name="프로젝트 / 서브프로젝트" value={data?.sink_count} detail="현황"/>
      <Metric name="수집 건수" value={data?.source_count} detail="최종 집계"/>
      <Metric name="필드 불일치" value={data?.source_sink_mismatch_count} detail="각 프로젝트 교차 대조"/>
      <Metric name="누락된 프로젝트" value={data?.missing_project_count} detail="고유 프로젝트 ID 기준"/>
    </section>

    <section className={styles.panel}>
      <div className={styles.panelHead}>
        <div><h2>프로젝트 목록</h2><p>프로젝트/서브프로젝트 ID를 기본키로 사용합니다. AMEA는 보조키입니다.</p></div>
        <span>{visible.length} / {projects.length}건</span>
      </div>
      <div className={styles.filters}>
        <label>기관 · 서비스 · AMEA · 프로젝트 검색
          <input type="search" value={query} onChange={e=>setQuery(e.target.value)}
            placeholder="기관명 또는 AMEA 입력"/>
        </label>
        <label>Feishu 공정
          <select value={stage} onChange={e=>setStage(e.target.value)}>
            <option value="ALL">전체 공정 ({projects.length})</option>
            {stages.map(([name,count])=><option key={name} value={name}>{name} ({count})</option>)}
          </select>
        </label>
      </div>
      <div className={styles.tableScroll}>
        <table>
          <thead><tr>
            <th>프로젝트 / 서브프로젝트</th><th>AMEA</th><th>기관</th><th>서비스</th>
            <th>Feishu 최신 상태</th><th>CSS 이전 상태</th><th>시료 수</th><th>예상 완료</th>
          </tr></thead>
          <tbody>{visible.map(r=><tr key={r.project_id}>
            <td className={styles.mono}>{r.project_id}</td>
            <td className={styles.mono}>{r.amea||"—"}</td>
            <td>{r.institution||"미연결"}</td>
            <td>{r.service||"미확인"}</td>
            <td><span className={styles.stage}>{r.stage||"미확인"}</span></td>
            <td className={styles.muted}>{r.css_legacy_stage||"미확인"}</td>
            <td>{r.sample_count||"—"}</td>
            <td>{r.expected_completion||"—"}</td>
          </tr>)}</tbody>
        </table>
        {visible.length===0&&<p className={styles.empty}>{loading?"조회 중":error?"데이터 조회 실패":"검색 결과가 없습니다."}</p>}
      </div>
    </section>
    <footer className={styles.footer}>
      <Link href="/sales/commands">Lead Convert · Oppo · Quote 실행</Link>
      <span>상태 확인 후 실행</span>
    </footer>
  </main>;
}
