"use client";

import {useCallback,useEffect,useMemo,useRef,useState} from "react";
import Link from "next/link";
import {leadOutboundGroup,leadOutboundSummary,leadGroupMatches} from "../../../lib/css-lead-outbound-groups.mjs";
import styles from "./page.module.css";

const MAIL_ACTIONS=[
  {id:"SKIP_MAIL",label:"이 메일만 넘기기"},
  {id:"SKIP_CC_TO",label:"특정 To 수신자 · 내가 CC인 메일 제외"},
  {id:"SKIP_CC_SENDER",label:"이 발신자 · 내가 CC인 메일만 제외"}
];
const EVIDENCE={
  SENT_AFTER_LEAD_CONFIRMED:"생성 후 발송 확인",
  SENT_BEFORE_LEAD_ONLY:"Lead 생성 전만 발송",
  NO_PERSONAL_OUTBOUND_EVIDENCE:"개인 발송 증거 없음",
  LEAD_EMAIL_MISSING:"이메일 없음",
  CREATED_DATE_UNVERIFIED:"생성일 미확인",
};
function time(value){
  if(!value)return "미확인";
  const d=new Date(value);
  if(Number.isNaN(d.getTime()))return value;
  return new Intl.DateTimeFormat("ko-KR",{
    timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit",
    hour:"2-digit",minute:"2-digit",hour12:false
  }).format(d);
}
function emails(value){
  return [...new Set((String(value||"").match(/[\w.+%-]+@[\w.-]+\.[a-zA-Z]{2,}/g)||[])
    .map(x=>x.toLowerCase()))];
}
function Tile({label,value,detail}){
  return <div className={styles.tile}><span>{label}</span><strong>{value??"—"}</strong><small>{detail}</small></div>;
}
export default function LocalMailConsole(){
  const [data,setData]=useState(null);
  const [tab,setTab]=useState("mail");
  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [q,setQ]=useState("");
  const [priority,setPriority]=useState("ALL");
  const [leadState,setLeadState]=useState("ALL");
  const [descriptionFilter,setDescriptionFilter]=useState("ALL");
  const [leadGroup,setLeadGroup]=useState("ALL");
  const [roleFilter,setRoleFilter]=useState("ALL");
  const [mailPage,setMailPage]=useState(0);
  const [leadPage,setLeadPage]=useState(0);
  const [selected,setSelected]=useState(null);
  const [action,setAction]=useState("SKIP_MAIL");
  const [target,setTarget]=useState("");
  const [note,setNote]=useState("");
  const [confirming,setConfirming]=useState(null);
  const [bodyInfo,setBodyInfo]=useState({status:"NOT_REQUESTED",text:""});
  const bodyCache=useRef(new Map());
  const dialogRef=useRef(null);
  const pageSize=40;

  const closeDialog=useCallback(()=>{
    if(busy)return;
    setSelected(null);
    setConfirming(null);
    setError("");
  },[busy]);
  useEffect(()=>{
    if(!selected&&!confirming)return;
    const previous=document.activeElement;
    const previousOverflow=document.body.style.overflow;
    document.body.style.overflow="hidden";
    const id=window.requestAnimationFrame(()=>{
      dialogRef.current?.querySelector("button,select,input")?.focus();
    });
    const onKeyDown=(event)=>{
      if(event.key==="Escape"){
        event.preventDefault();
        closeDialog();
      }
      if(event.key==="Tab"&&dialogRef.current){
        const elements=[...dialogRef.current.querySelectorAll(
          'button:not([disabled]),input:not([disabled]),select:not([disabled])'
        )].filter(el=>el.getClientRects().length);
        if(!elements.length)return;
        const first=elements[0],last=elements[elements.length-1];
        if(event.shiftKey&&document.activeElement===first){
          event.preventDefault();
          last.focus();
        }else if(!event.shiftKey&&document.activeElement===last){
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown",onKeyDown);
    return ()=>{
      document.removeEventListener("keydown",onKeyDown);
      window.cancelAnimationFrame(id);
      document.body.style.overflow=previousOverflow;
      if(previous?.isConnected&&typeof previous.focus==="function")previous.focus();
    };
  },[Boolean(selected),Boolean(confirming),closeDialog]);

  const refresh=useCallback(async()=>{
    setLoading(true);setError("");
    try{
      const r=await fetch("/api/css/mail-local",{
        cache:"no-store",credentials:"omit",
        headers:{"X-CSS-Local-Mail":"1"}
      });
      const body=await r.json();
      if(!r.ok||!["PASS","STALE"].includes(body.status))throw Error(body.code||"SOURCE_UNAVAILABLE");
      setData(body);
    }catch(err){setData(null);setError(err?.message||"SOURCE_UNAVAILABLE");}
    finally{setLoading(false)}
  },[]);
  useEffect(()=>{refresh()},[refresh]);

  const messages=useMemo(()=>{
    const needle=q.trim().toLowerCase();
    return (data?.mail||[]).filter(r=>
      (priority==="ALL"||r.priority===priority)&&
      (roleFilter==="ALL"||r.role===roleFilter)&&
      (!needle||[r.sender,r.subject,r.to,r.cc,r.project,r.key].some(x=>String(x||"").toLowerCase().includes(needle)))
    );
  },[data,q,priority,roleFilter]);
  const leadSummary=useMemo(()=>leadOutboundSummary(data?.leads||[]),[data]);
  const leads=useMemo(()=>{
    const needle=q.trim().toLowerCase();
    return (data?.leads||[]).filter(r=>
      leadGroupMatches(r,leadGroup,leadState)&&
      (descriptionFilter==="ALL"||r.descriptionClass===descriptionFilter)&&
      (!needle||[r.id,r.institution,r.name,r.email,r.owner].some(x=>String(x||"").toLowerCase().includes(needle)))
    );
  },[data,q,leadState,leadGroup,descriptionFilter]);
  function selectLeadGroup(next){
    setLeadGroup(next);setLeadState("ALL");setLeadPage(0);
  }
  function selectLeadDetail(next){
    setLeadState(next);setLeadPage(0);
    setLeadGroup(next==="ALL"?"ALL":
      next==="SENT_AFTER_LEAD_CONFIRMED"||next==="SENT_BEFORE_LEAD_ONLY"?"SENT":
      next==="NO_PERSONAL_OUTBOUND_EVIDENCE"?"NO_EVIDENCE":"REVIEW");
  }
  const shownMail=messages.slice(mailPage*pageSize,(mailPage+1)*pageSize);
  const shownLeads=leads.slice(leadPage*pageSize,(leadPage+1)*pageSize);
  const selectedIndex=selected?messages.findIndex(x=>x.key===selected.key):-1;
  const canPrevious=selectedIndex>0;
  const canNext=selectedIndex>=0&&selectedIndex<messages.length-1;
  const options=selected?emails(selected.to).filter(x=>!emails(selected.cc).includes(x)||selected.role==="CC_ONLY"):[];
  function selectMail(item){
    setSelected(item);
    setConfirming(null);
    setError("");
    setAction("SKIP_MAIL");
    setTarget(emails(item.to)[0]||"");
    setNote("");
  }
  function write(payload,caption){
    if(busy||loading)return;
    setError("");
    setConfirming({payload,caption});
  }
  useEffect(()=>{
    if(!selected?.key||!selected?.uid){
      setBodyInfo({status:"NOT_REQUESTED",text:""});
      return;
    }
    const cacheKey=selected.key+"|"+selected.uid;
    if(bodyCache.current.has(cacheKey)){
      setBodyInfo(bodyCache.current.get(cacheKey));
      return;
    }
    const controller=new AbortController();
    setBodyInfo({status:"LOADING",text:""});
    (async()=>{
      try{
        const query=new URLSearchParams({uid:selected.uid,key:selected.key});
        const response=await fetch("/api/css/mail-body-local?"+query,{
          credentials:"omit",cache:"no-store",signal:controller.signal,
          headers:{"X-CSS-Local-Mail":"1"}
        });
        const result=await response.json();
        if(!response.ok||result.status!=="PASS"||result.uid!==selected.uid)
          throw Error(result.code||"BODY_SOURCE_UNAVAILABLE");
        const info={status:result.bodyStatus||"BODY_UNAVAILABLE",text:result.body||""};
        bodyCache.current.set(cacheKey,info);
        if(bodyCache.current.size>15)bodyCache.current.delete(bodyCache.current.keys().next().value);
        if(!controller.signal.aborted)setBodyInfo(info);
      }catch(error){
        if(!controller.signal.aborted)setBodyInfo({status:"ERROR",text:error.message||"BODY_SOURCE_UNAVAILABLE"});
      }
    })();
    return ()=>controller.abort();
  },[selected?.key,selected?.uid]);

  function navigateMail(delta){
    if(busy||confirming||selectedIndex<0)return;
    const next=messages[selectedIndex+delta];
    if(next)selectMail(next);
  }
  function requestReview(kind){
    if(!selected||busy)return;
    if(kind!=="SKIP_MAIL"&&selected.role!=="CC_ONLY"){
      setError("CC 규칙은 내 주소가 CC에만 있는 메일에 적용할 수 있습니다.");
      return;
    }
    const which=MAIL_ACTIONS.find(x=>x.id===kind)?.label||kind;
    write({
      action:kind,key:selected.key,uid:selected.uid,sender:selected.sender,
      subject:selected.subject,to:selected.to,cc:selected.cc,
      target:kind==="SKIP_CC_TO"?target:"",note
    },which+"\\n"+selected.subject+(kind==="SKIP_CC_TO"?"\\n대상: "+target:""));
  }
  function nextAfterSaved(key){
    const index=messages.findIndex(x=>x.key===key);
    return index>=0?messages[index+1]||null:null;
  }
  async function confirmWrite(){
    if(busy||loading||!confirming)return;
    const {payload}=confirming;
    const nextMail=payload.key?nextAfterSaved(payload.key):null;
    if(data?.mailSourceStatus!=="FRESH"){
      setError("메일 원본 갱신이 지연되었습니다. 새로고침 후 다시 검토하세요.");
      return;
    }
    setBusy(true);setError("");setNotice("");
    try{
      const response=await fetch("/api/css/mail-local",{
        method:"POST",credentials:"omit",cache:"no-store",
        headers:{"Content-Type":"application/json","X-CSS-Local-Mail":"1"},
        body:JSON.stringify({mode:"decision",...payload})
      });
      const result=await response.json();
      if(!response.ok||result.status!=="PASS")throw Error(result.code||"SAVE_FAILED");
      setNotice("적용 완료: "+result.result+" · 기존 원본 메일과 SFDC는 변경하지 않았습니다.");
      setConfirming(null);
      if(nextMail)selectMail(nextMail);
      else{setSelected(null);setNote("");}
      await refresh();
    }catch(err){
      setError("규칙 적용 실패: "+(err?.message||"UNKNOWN"));
    }finally{setBusy(false)}
  }
  function submitSelected(){
    if(!selected)return;
    requestReview(action);
  }
  const statuses=data?.leadStates||{};
  const descriptionStates=data?.leadDescriptions||{};
  const descriptionReady=data?.leadDescriptionSourceStatus==="VERIFIED";
  const pageButtons=(current,count,set)=>(
    <div className={styles.pager}>
      <button type="button" onClick={()=>set(Math.max(0,current-1))} disabled={current===0}>이전</button>
      <span>{count?current*pageSize+1:0}–{Math.min(count,(current+1)*pageSize)} / {count}건</span>
      <button type="button" onClick={()=>set(current+1)}
        disabled={(current+1)*pageSize>=count}>다음</button>
    </div>
  );

  return <main className={styles.wrap}>
    <header className={styles.header}>
      <div>
        <p className={styles.eyebrow}>NOVOGENE · LOCAL CUSTOMER OPERATIONS</p>
        <h1>메일 · Lead 검토</h1>
        <p>미회신 검토와 CC 제외 규칙, 고객별 발송 이력을 한곳에서 관리합니다.</p>
      </div>
      <div className={styles.navigation}>
        <Link href="/sales/commands">업무 실행</Link>
        <Link href="/sales/projects">프로젝트</Link>
        <button type="button" onClick={refresh} disabled={loading||busy}>{loading?"확인 중":"새로고침"}</button>
      </div>
    </header>

    <section className={styles.health}>
      <div className={styles.healthTop}>
        <b data-state={data?.status||"SOURCE_UNAVAILABLE"}>
          {data?.status==="PASS"?"데이터 최신":data?.status==="STALE"?"갱신 지연":"원천 연결 확인 필요"}
        </b>
        <span>QQ 검토: {time(data?.mailCheckedAt)} · Lead 발송: {time(data?.leadCheckedAt)}</span>
      </div>
      <p>발송 증거 없음은 미발송 확정이 아닙니다. 본문·첨부·BCC·통화·방문 여부는 별도 확인이 필요합니다.</p>
      {error&&<p className={styles.error} role="alert">{error}</p>}
      {notice&&<p className={styles.success} role="status">{notice}</p>}
    </section>

    <section className={styles.tiles}>
      <Tile label="미회신 검토 후보" value={data?.mailCount}
        detail={"원본 "+(data?.mailTotal??"—")+"건 · 정확한 회신 확정 아님"}/>
      <Tile label="CC 자동 제외 규칙" value={data?.ruleCount} detail="발신자 / To 수신자별"/>
      <Tile label="내 메일 발송 이력 있음" value={data?leadSummary.sent:"—"}
        detail={data?("Lead 생성 후 "+leadSummary.sentAfter+" · 생성 전만 "+leadSummary.sentBeforeOnly):"조회 대기"}/>
      <Tile label="내 발송 증거 없는 Lead" value={data?leadSummary.noEvidence:"—"}
        detail={data?("검토 대상 · 전체 "+leadSummary.all+"건 중"):"조회 대기"}/>
    </section>

    <nav className={styles.tabs} aria-label="메일 검토 메뉴">
      <button type="button" aria-pressed={tab==="mail"} onClick={()=>{setTab("mail");setQ("");setSelected(null);setConfirming(null)}}>미회신 검토</button>
      <button type="button" aria-pressed={tab==="rules"} onClick={()=>{setTab("rules");setQ("");setSelected(null);setConfirming(null)}}>넘김 · CC 규칙</button>
      <button type="button" aria-pressed={tab==="leads"} onClick={()=>{setTab("leads");setQ("");setSelected(null);setConfirming(null)}}>Lead 발송 이력</button>
    </nav>

    {tab==="mail"&&<section className={styles.panel}>
      <div className={styles.panelHead}><div><h2>미회신 후보</h2>
        <p>최신 고객 메일 기준 · 회신 확정이 아닌 검토 목록 · 한 건씩 넘기거나 CC 규칙 등록</p></div>
        <strong>{messages.length}건</strong></div>
      <div className={styles.filters}>
        <label>발신자 · 제목 · 수신자 · 프로젝트
          <input type="search" value={q} placeholder="메일 또는 프로젝트 검색"
            onChange={e=>{setQ(e.target.value);setMailPage(0)}}/></label>
        <label>우선순위<select value={priority} onChange={e=>{setPriority(e.target.value);setMailPage(0)}}>
          <option value="ALL">전체</option>
          {["P0","P1","P2","WATCH","OLD_REVIEW"].map(x=><option key={x} value={x}>{x}</option>)}
        </select></label>
        <label>수신 유형<select value={roleFilter} onChange={e=>{setRoleFilter(e.target.value);setMailPage(0)}}>
          <option value="ALL">전체</option><option value="TO">내 To</option>
          <option value="CC_ONLY">내 CC만</option>
        </select></label>
      </div>
      <div className={styles.tableWrap}><table><thead><tr>
        <th>우선</th><th>경과</th><th>수신일</th><th>발신자 / 제목</th><th>수신 위치</th><th>회신 증거</th><th>관리</th>
      </tr></thead><tbody>{shownMail.map(r=><tr key={r.key} tabIndex={0} role="button"
        aria-label={"메일 내용 및 처리 열기: "+r.subject}
        className={styles.openableRow}
        onClick={()=>selectMail(r)}
        onKeyDown={e=>{if(e.target===e.currentTarget&&(e.key==="Enter"||e.key===" ")){e.preventDefault();selectMail(r)}}}>
        <td><span className={styles.chip} data-priority={r.priority}>{r.priority}</span></td>
        <td>{r.days}일</td><td className={styles.nowrap}>{r.received}</td>
        <td><b>{r.sender}</b><p className={styles.subject}>{r.subject}</p><small>{r.project||"프로젝트 미연결"}</small></td>
        <td><span className={styles.chip}>{r.role}</span><small className={styles.block}>To: {r.to||"—"} · Cc: {r.cc||"—"}</small></td>
        <td><small>{r.evidence}</small></td>
        <td><button type="button" onClick={e=>{e.stopPropagation();selectMail(r)}} disabled={busy}>본문 · 처리</button></td>
      </tr>)}</tbody></table>
      {!shownMail.length&&<p className={styles.empty}>{error?"원본 연결 실패":"조건에 맞는 메일이 없습니다."}</p>}</div>
      {pageButtons(mailPage,messages.length,setMailPage)}
    </section>}

    {(selected||confirming)&&<div className={styles.modalBackdrop}
      onMouseDown={event=>{if(event.target===event.currentTarget)closeDialog()}}>
      <section ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="mail-review-dialog-title"
        className={styles.modal} data-testid="mail-review-dialog">
        <header className={styles.modalHead}>
          <div><p className={styles.eyebrow}>MAIL REVIEW · LOCAL ONLY</p>
            <h2 id="mail-review-dialog-title">{confirming?"처리 내용 최종 확인":"선택한 메일 처리"}</h2>
          </div>
          <button type="button" onClick={closeDialog} disabled={busy} aria-label="메일 처리 창 닫기">✕</button>
        </header>
        {selected&&<div className={styles.mailSummary}>
          <b>{selected.subject}</b>
          <span>{selected.sender}</span>
          <small>To: {selected.to||"—"} · Cc: {selected.cc||"—"}</small>
          <small>수신 유형: {selected.role} · {selected.received}</small>
        </div>}
        {selected&&<div className={styles.viewerTools}>
          <button type="button" onClick={()=>navigateMail(-1)} disabled={!canPrevious||busy||!!confirming}>← 이전</button>
          <span>{selectedIndex>=0?selectedIndex+1:"—"} / {messages.length}</span>
          <button type="button" onClick={()=>requestReview("SKIP_MAIL")}
            disabled={busy||!!confirming||data?.mailSourceStatus!=="FRESH"}>이 메일 스킵</button>
          <button type="button" onClick={()=>navigateMail(1)} disabled={!canNext||busy||!!confirming}>다음 →</button>
        </div>}
        {selected&&<div className={styles.bodyViewer}>
          <div className={styles.bodyTitle}><b>원본 메일 본문</b>
            <small>{bodyInfo.status==="LOADING"?"불러오는 중":bodyInfo.status}</small></div>
          {bodyInfo.status==="LOADING"?<p className={styles.bodyMessage}>기존 QQ 메일 캐시에서 원본을 조회하고 있습니다.</p>:
           bodyInfo.status==="ERROR"?<p className={styles.modalError}>본문 조회 실패: {bodyInfo.text}</p>:
           bodyInfo.text?<pre data-testid="mail-body-text" className={styles.bodyText}>{bodyInfo.text}</pre>:
           <p className={styles.bodyMessage}>저장된 텍스트 본문이 없습니다. 원본 첨부파일 또는 메일을 확인하세요.</p>}
        </div>}
        {error&&<p role="alert" className={styles.modalError}>{error}</p>}
        {confirming?<div className={styles.modalContents}>
          <h3>{confirming.caption}</h3>
          <p>이메일을 보내거나 삭제하지 않으며, 검토 규칙표에만 기록합니다.</p>
          <div className={styles.modalButtons}>
            <button type="button" onClick={()=>{setConfirming(null);setError("")}} disabled={busy}>
              {selected?"이전으로":"취소"}
            </button>
            <button type="button" className={styles.primary} data-testid="confirm-review-action"
              disabled={busy||loading||data?.mailSourceStatus!=="FRESH"}
              onClick={confirmWrite}>{busy?"저장 중…":"확인하고 저장"}</button>
          </div>
        </div>:selected?<div className={styles.modalContents} data-testid="review-action-area">
          <label>처리 유형
            <select value={action} onChange={e=>setAction(e.target.value)}>
              {MAIL_ACTIONS.map(a=><option key={a.id} value={a.id}
                disabled={a.id!=="SKIP_MAIL"&&selected.role!=="CC_ONLY"}>{a.label}</option>)}
            </select>
          </label>
          {action==="SKIP_CC_TO"&&<label>제외할 To 주소
            <select value={target} onChange={e=>setTarget(e.target.value)}>
              {options.map(x=><option key={x} value={x}>{x}</option>)}
            </select>
          </label>}
          <label>검토 메모 (선택)
            <input value={note} maxLength={300} onChange={e=>setNote(e.target.value)}
              placeholder="넘기는 이유"/>
          </label>
          {selected.role!=="CC_ONLY"&&<p className={styles.modalHint}>
            직접 To로 받은 메일은 개별 넘기기만 가능합니다. CC 제외 규칙은 적용되지 않습니다.
          </p>}
          {data?.mailSourceStatus!=="FRESH"&&<p className={styles.modalError}>
            메일 검토 자료가 최신 상태가 아니어서 저장을 차단했습니다. 먼저 새로고침하세요.
          </p>}
          <div className={styles.modalButtons}>
            <button type="button" onClick={closeDialog}>닫기</button>
            <button className={styles.primary} type="button"
              disabled={busy||loading||data?.mailSourceStatus!=="FRESH"||(action==="SKIP_CC_TO"&&!target)}
              onClick={submitSelected}>다음 · 적용 내용 확인</button>
          </div>
        </div>:null}
      </section>
    </div>}

    {tab==="rules"&&<section className={styles.panel}>
      <div className={styles.panelHead}><div><h2>활성 CC 제외 규칙</h2>
        <p>언제든 규칙 해제 가능 · 해제 후 다음 검토에서 다시 표시</p></div>
        <strong>{data?.ruleCount??0}건</strong></div>
      <div className={styles.tableWrap}><table><thead><tr>
        <th>범위</th><th>정확한 이메일 주소</th><th>적용 조건</th><th>관리</th>
      </tr></thead><tbody>{(data?.rules||[]).map(r=><tr key={r.type+":"+r.address}>
        <td>{r.type==="TO_ADDRESS"?"To 수신자":"발신자"}</td><td>{r.address}</td>
        <td>내가 CC로 받은 메일만</td><td><button type="button" disabled={busy}
          onClick={()=>write({action:"RESTORE_RULE",target:r.type,sender:r.address},"CC 제외 규칙 해제: "+r.address)}>규칙 해제</button></td>
      </tr>)}</tbody></table>
      {!data?.rules?.length&&<p className={styles.empty}>등록된 CC 자동 제외 규칙이 없습니다.</p>}</div>
      <div className={styles.panelHead}><div><h2>개별 넘긴 메일</h2><p>한 건씩 복구 가능</p></div><strong>{data?.mailSkipCount??0}건</strong></div>
      <div className={styles.tableWrap}><table><thead><tr><th>발신자</th><th>제목</th><th>원본 UID</th><th>관리</th></tr></thead>
        <tbody>{(data?.skippedMails||[]).map(r=><tr key={r.key}>
          <td>{r.sender}</td><td>{r.subject}</td><td>{r.uid}</td>
          <td><button type="button" disabled={busy}
            onClick={()=>write({action:"RESTORE_MAIL",key:r.key},"개별 넘김 취소: "+r.subject)}>복구</button></td>
        </tr>)}</tbody></table>
        {!data?.skippedMails?.length&&<p className={styles.empty}>개별 넘기기 기록이 없습니다.</p>}
      </div>
    </section>}

    {tab==="leads"&&<section className={styles.panel}>
      <div className={styles.panelHead}><div><h2>Lead · 내 메일 발송 여부</h2>
        <p>Lead 이메일 주소와 본인 QQ 발신 이력을 대조합니다. 생성 전 발송도 별도로 구분합니다.</p></div>
        <strong>{leads.length} / {leadSummary.all}건</strong></div>
      <div className={styles.leadGroups} aria-label="Lead 발송 이력 그룹">
        {[
          {id:"ALL",label:"전체 Lead",count:leadSummary.all},
          {id:"SENT",label:"내 발송 이력 있음",count:leadSummary.sent},
          {id:"NO_EVIDENCE",label:"내 발송 증거 없음",count:leadSummary.noEvidence},
          {id:"REVIEW",label:"확인 필요",count:leadSummary.review}
        ].map(item=><button type="button" key={item.id}
          data-testid={"lead-group-"+item.id}
          aria-pressed={leadGroup===item.id}
          onClick={()=>selectLeadGroup(item.id)}>
          <span>{item.label}</span><strong>{data?item.count.toLocaleString("ko-KR"):"—"}</strong>
        </button>)}
      </div>
      <div className={styles.leadBreakdown}>
        <span>발송 이력 있음 {leadSummary.sent}건 중
          <b> 생성 후 발송 {leadSummary.sentAfter}건</b> ·
          <b> 생성 전만 발송 {leadSummary.sentBeforeOnly}건</b></span>
        <span>원본: {data?.leadSourceStatus||"미확인"} · 기준시각 {time(data?.leadCheckedAt)}</span>
      </div>
      <div className={styles.leadGroups} aria-label="Lead Description 구분">
        {[
          {id:"ALL",label:"Description 전체",count:data?.leadCount??0},
          {id:"DESCRIPTION_PRESENT",label:"Description 있음 · 내용 검토",count:descriptionStates.DESCRIPTION_PRESENT??0},
          {id:"DESCRIPTION_EMPTY",label:"Description 없음 · 공통 메일",count:descriptionStates.DESCRIPTION_EMPTY??0},
          {id:"DESCRIPTION_REVIEW_REQUIRED",label:"Description 확인 필요",count:
            (descriptionStates.DESCRIPTION_REVIEW_REQUIRED??0)+(descriptionReady?0:
              (data?.leadCount??0))}
        ].map(item=><button type="button" key={item.id}
          data-testid={"lead-description-"+item.id}
          aria-pressed={descriptionFilter===item.id}
          disabled={item.id!=="ALL"&&!descriptionReady}
          onClick={()=>{setDescriptionFilter(item.id);setLeadPage(0)}}>
          <span>{item.label}</span><strong>{data?item.count.toLocaleString("ko-KR"):"—"}</strong>
        </button>)}
      </div>
      {!descriptionReady&&<p className={styles.leadCaution}>원본 Lead Description을 검증하지 못했습니다. 확인 전에는 공통 메일 대상으로 분류하지 않습니다.</p>}
      <div className={styles.filters}>
        <label>이름 · 기관 · 이메일 · Lead ID
          <input type="search" value={q} placeholder="고객 또는 기관 검색"
            onChange={e=>{setQ(e.target.value);setLeadPage(0)}}/></label>
        <label>발송 세부 유형
          <select value={leadState} onChange={e=>selectLeadDetail(e.target.value)}>
            <option value="ALL">전체</option>
            {Object.keys(statuses).map(x=><option key={x} value={x}>{EVIDENCE[x]||x} ({statuses[x]})</option>)}
          </select></label>
      </div>
      <div className={styles.tableWrap}><table><thead><tr>
        <th>Lead / 기관</th><th>Lead 이메일</th><th>Lead 생성일</th><th>Description / 메일 방식</th><th>발송 판정</th>
        <th>생성 후 발송 횟수</th><th>첫 발송일</th><th>최근 발송일</th><th>To / CC</th>
      </tr></thead><tbody>{shownLeads.map(r=><tr key={r.id}>
        <td><b>{r.name||"이름 미확인"}</b><small className={styles.block}>{r.institution}</small>
          <small className={styles.block}>{r.id}</small></td>
        <td>{r.email||"—"}</td><td className={styles.nowrap}>{r.created||"생성일 미확인"}</td>
        <td>
          {r.descriptionClass==="DESCRIPTION_PRESENT"?<>
            <b>내용 검토 후 개별 메일</b>
            <details className={styles.leadDescription} data-testid="lead-description-text">
              <summary>Lead Description 열기</summary>
              <pre>{r.description}</pre>
            </details>
          </>:r.descriptionClass==="DESCRIPTION_EMPTY"?
            <span>공통 메일 후보 · Description 없음</span>:
            <span>내용 확인 필요 · 발송 방식 미결정</span>}
        </td>
        <td><span className={styles.chip}>{EVIDENCE[r.evidence]||r.evidence}</span>
          {leadOutboundGroup(r)==="NO_EVIDENCE"&&
            <small className={styles.block}>미발송 확정 아님 · 후속 확인 후보</small>}
          {leadOutboundGroup(r)==="REVIEW"&&
            <small className={styles.block}>증거 또는 날짜 검증 필요</small>}
        </td>
        <td>{r.afterCount||"0"}건</td><td className={styles.nowrap}>{time(r.firstEver)}</td>
        <td className={styles.nowrap}>{time(r.lastEver)}</td>
        <td>{r.toCount||0} / {r.ccCount||0}</td>
      </tr>)}</tbody></table>
      {!shownLeads.length&&<p className={styles.empty}>
        {data?"선택한 발송 분류에 해당하는 Lead가 없습니다.":"Lead 원본을 불러오지 못했습니다."}
      </p>}</div>
      <p className={styles.leadCaution}>‘내 발송 증거 없음’은 QQ 수집 범위에서 내 계정의 발신 메일이 확인되지 않았다는 뜻입니다.
        다른 계정·BCC·과거 미수집 메일이나 전화·방문 활동까지 포함한 미접촉 확정은 아닙니다.</p>
      {pageButtons(leadPage,leads.length,setLeadPage)}
    </section>}

    <footer className={styles.footer}>
      <span>로컬 전용 · 원본 QQ 메일 삭제 없음 · SFDC 저장 없음</span>
      <span>데이터 원본: 기존 Google Sheets 미회신 판정 및 Lead 발송 감사</span>
    </footer>
  </main>;
}
