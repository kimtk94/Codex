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
  PASS_MIRROR_ONLY:"Google Drive 운영 미러와 V4 일치",
  SINK_LAG:"원천 ↔ V4 불일치",
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
        <p>Google Drive → WEB_EXPORT_V4 · 읽기 전용</p>
      </div>
      <div className={styles.actions}>
        <Link href="/sales/oppo-quote">Oppo · Quote</Link>
        <Link href="/">홈</Link>
        <button type="button" onClick={refresh} disabled={loading}>
          {loading?"동기화 확인 중":"새로고침"}
        </button>
      </div>
    </header>

    <section className={styles.statusCard} aria-live="polite">
      <div className={styles.statusRow}>
        <span className={styles.status} data-status={status}>{descriptions[status]||status}</span>
        <span>Google Drive 운영 미러 기준 · 원본 시스템 검증 별도</span>
      </div>
      <div className={styles.timestamps}>
        <span>원천 미러: {timeKst(data?.source_synced_at)}</span>
        <span>V4 생성: {timeKst(data?.sink_generated_at)}</span>
        <span>재조회: {timeKst(data?.checked_at)}</span>
      </div>
      <p className={styles.caution}>
        {error?"조회 실패: "+error:
        status==="SINK_LAG"?"원천과 내보내기 결과가 일치하지 않습니다. 운영에 사용하기 전에 동기화가 필요합니다.":
        status==="STALE"?"원천이나 결과 갱신이 지연됐습니다. 최신화 후 확인하세요.":
        "미러→V4 정합성은 검증하지만, Feishu·QQ 원본 최신성 및 SFDC 저장 성공은 인증하지 않습니다."}
      </p>
    </section>

    <section className={styles.metrics}>
      <Metric name="프로젝트 / 서브프로젝트" value={data?.sink_count} detail="V4 표시 건수"/>
      <Metric name="운영 원천" value={data?.source_count} detail="Google Drive 운영 미러"/>
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
      <a href="https://docs.google.com/spreadsheets/d/1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY/edit#gid=1142461809" target="_blank" rel="noreferrer">Google Drive · WEB_EXPORT_V4</a>
      <span>로컬 전용 · 127.0.0.1 · CRM 저장 없음</span>
    </footer>
  </main>;
}
