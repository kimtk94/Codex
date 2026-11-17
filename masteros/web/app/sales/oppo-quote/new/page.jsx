"use client";
import {useMemo,useState} from "react";
import {exportLocalOppoQuoteReview} from "../../../../lib/sfdc-local-process-draft.mjs";
import KrwPricePanel from "./KrwPricePanel";
import {inspectLocalContactEvidence} from "../../../../lib/sfdc-local-contact-evidence.mjs";
import {selectExistingContact} from "../../../../lib/sfdc-contact-first-command.mjs";
import {validKrwNativeContactQuery,validateLiveKrwContactSearch}
 from "../../../../lib/sfdc-krw-native-contact-lookup.mjs";
import Link from "next/link";
import styles from "../page.module.css";
import {PATTERNS,UNITS,DEFAULT_INPUT,createIntake} from "../../../../lib/sfdc-new-oppo-quote.mjs";
const labels={institution:"기관",contact:"고객 한글 이름",service:"서비스",samples:"샘플 수",production:"생산량",unit:"단위"};
function kstDate(){const p=new Intl.DateTimeFormat("en-US",{timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(new Date());const v=x=>p.find(a=>a.type===x).value;return v("year")+"-"+v("month")+"-"+v("day");}
export default function NewQuote(){
 const [input,setInput]=useState({...DEFAULT_INPUT}),[notice,setNotice]=useState(""),[show,setShow]=useState(false);
 const [contactEvidence,setContactEvidence]=useState(null);
 const [contactSelection,setContactSelection]=useState(null);
 const [contactNotice,setContactNotice]=useState("");
 const [liveContactBusy,setLiveContactBusy]=useState(false);
 const [processDraftProducts,setProcessDraftProducts]=useState([]);
 const today=kstDate();const result=useMemo(()=>createIntake(input,today),[input,today]);
 const localProcessReview=useMemo(()=>processDraftProducts.length?
   exportLocalOppoQuoteReview(processDraftProducts,result,contactSelection):null,
   [processDraftProducts,result,contactSelection]);
 const reviewedRequest=useMemo(()=>localProcessReview?
   {...result,localOriginalProcessProductDraft:localProcessReview}:result,
   [result,localProcessReview]);
 const update=(k,v)=>{
  setInput(s=>({...s,[k]:v}));setShow(false);setNotice("");
  if(k==="contact"||k==="institution"||(k==="identityMode"&&v==="CHANGE")){
   setContactEvidence(null);setContactSelection(null);setContactNotice("");
  }
 };
 const searchLiveContact=async()=>{
  if(liveContactBusy)return;
  const checked=validKrwNativeContactQuery({query:input.contact,limit:10});
  setContactSelection(null);setContactEvidence(null);
  if(!checked.ok){setContactNotice("SFDC 조회 보류: "+checked.code);return;}
  setLiveContactBusy(true);setContactNotice("로그인된 Salesforce에서 고객·Account·Opportunity 연결 재확인 중...");
  try{
   const response=await fetch("/api/sfdc/krw-contact-local",{
    method:"POST",cache:"no-store",credentials:"omit",
    headers:{"Content-Type":"application/json","X-SFDC-Command":"1"},
    body:JSON.stringify(checked.request)
   });
   const data=await response.json();
   if(!response.ok||data.status!=="PASS")throw Error(data.code||"LIVE_SOURCE_UNAVAILABLE");
   const confirmed=validateLiveKrwContactSearch(data,input.contact);
   if(!confirmed.ok)throw Error(confirmed.code);
   setContactEvidence(confirmed);
   setContactNotice(confirmed.candidates.length?
    "2026 KRW 검증 Quote에 연결된 고객 "+confirmed.candidates.length+"개 확인 · 기관과 Contact를 선택하세요.":
    "검증된 2026 Quote 고객 색인에 일치하는 고객이 없습니다. Salesforce 전체 고객 조회 결과는 아닙니다.");
  }catch(error){
   setContactEvidence(null);setContactSelection(null);
   setContactNotice("실시간 SFDC 조회 보류: "+(error?.message||"SOURCE_UNAVAILABLE")+". 로컬 JSON 확인은 계속 사용할 수 있습니다.");
  }finally{setLiveContactBusy(false);}
 };
 const loadContactFile=async event=>{
  const f=event.currentTarget.files?.[0];event.currentTarget.value="";
  setContactSelection(null);setContactEvidence(null);setContactNotice("");
  if(!f)return;
  if(!f.name.toLowerCase().endsWith(".json")||f.size>256*1024){
   setContactNotice("로컬 Contact JSON 파일 256KB 이하만 허용합니다.");return;
  }
  try{
   const reviewed=inspectLocalContactEvidence(await f.text(),input.contact);
   if(!reviewed.ok){setContactNotice("Contact 원본 검토 보류: "+reviewed.status);return;}
   setContactEvidence(reviewed);
   setContactNotice("기존 Opportunity 연결 Contact "+reviewed.candidates.length+"개 · 기관과 Contact를 명시적으로 선택하세요. 실시간 SFDC 재검증은 별도 필요합니다.");
  }catch{setContactNotice("Contact 로컬 파일을 확인할 수 없습니다.");}
 };
 const chooseContact=id=>{
  const candidate=contactEvidence?.candidates?.find(x=>x.contact_id===id);
  const selected=candidate?selectExistingContact(input.contact,contactEvidence.candidates,
    candidate.contact_id,candidate.account_id):{ok:false,status:"CONTACT_NOT_SELECTED"};
  if(!selected.ok){setContactSelection(null);setContactNotice("선택 보류: "+selected.status);return;}
  setContactSelection(selected);
  setInput(prev=>({...prev,institution:selected.institution_name,
   contact:selected.korean_name,identityMode:"KEEP"}));
  setContactNotice(contactEvidence?.status==="LIVE_QUOTE_LINKS_RECHECKED"?
  "Salesforce에서 재확인한 고객을 KRW 가격 비교에 연결했습니다. 신규 가격 적용과 CRM 저장은 금지 상태입니다.":
  "로컬 파일의 기존 고객을 KRW 가격 비교에 연결했습니다. 신규 Quote 적용 전에는 Salesforce 재확인이 필요합니다.");
 };
 const field=(id,label,value,onChange,placeholder="")=><div className={styles.field}><label htmlFor={id}>{label}</label><input id={id} value={value} placeholder={placeholder} onChange={e=>onChange(e.target.value)}/></div>;
 const copy=async()=>{if(result.missing.length)return;try{await navigator.clipboard.writeText(JSON.stringify(reviewedRequest,null,2));setNotice("검토용 JSON을 복사했습니다. Salesforce에는 전송하지 않았습니다.");}catch{setShow(true);setNotice("복사 실패: 아래 JSON을 직접 확인하세요.");}};
 return <main className={styles.page}><div className={styles.container}>
  <header className={styles.header}><div className={styles.breadcrumb}><Link href="/sales/oppo-quote">기존 PMP 시범 화면</Link><span>/</span><strong>신규 Oppo·Quote 요청</strong></div>
   <div className={styles.headerBottom}><div><p className={styles.eyebrow}>SFDC · HISTORICAL REFERENCE</p><h1>신규 Oppo + Quote</h1><p className={styles.subhead}>과거 854개 Quote의 공통 공정 구조만 참고합니다. 가격·Product·Contact ID는 추정하지 않습니다.</p></div><div className={styles.statusPill}>No Save · 검토용</div></div>
  </header>
  <div className={styles.banner} role="status"><span className={styles.bannerIcon}>!</span><span>로그인된 Salesforce의 검증된 기존 Quote 고객을 읽기 전용으로 조회할 수 있습니다. Salesforce 저장은 미연결이며 입력한 요청 정보는 브라우저 내부에서만 처리합니다. 참고 Quote 번호를 적어도 실제 Quote를 자동 복제하지 않습니다.</span></div>
  <div className={styles.grid}>
   <section className={styles.panel}>
    <div className={styles.panelHeader}><span className={styles.stepNo}>01</span><div><h2>신규 견적 정보</h2><p>바뀐 사항만 입력 · 실제 고객 정보는 SFDC 확인 필요</p></div></div>
    <form onSubmit={e=>{e.preventDefault();setShow(true);setNotice(result.missing.length?"누락 입력이 있습니다.":"검토용 명세를 생성했습니다. 실제 저장은 하지 않았습니다.");}}>
     <div className={styles.two}>
      {field("new-account","기관 / Account",input.institution,v=>update("institution",v),"예: 제주대학교")}
      {field("new-contact","고객 한글 이름",input.contact,v=>update("contact",v),"예: 이태백")}
     </div>
     <div className={styles.field}>
      <label htmlFor="new-contact-live">검증된 기존 고객 · Salesforce 읽기 전용 조회</label>
      <button id="new-contact-live" className={styles.secondary} type="button"
        disabled={liveContactBusy} onClick={searchLiveContact}>
        {liveContactBusy?"기존 고객 관계 검증 중":"인증된 Salesforce 고객 직접 확인"}
      </button>
      <small>파일 업로드 없이 기존 검증된 2026 KRW Quote 고객만 검색합니다. 로그인된 Salesforce에서 Account(001)·Contact(003)·Opportunity(006) 관계를 다시 확인합니다. 전체 CRM 검색이 아니며, 결과가 없어도 고객 부재를 뜻하지 않습니다.</small>
     </div>
     <div className={styles.field}>
      <label htmlFor="new-contact-readback">기존 SFDC Contact 조회 결과 (로컬 JSON · 선택)</label>
      <input id="new-contact-readback" type="file" accept=".json,application/json" onChange={loadContactFile}/>
      <small>현재 입력한 한글 이름과 정확히 일치하는, 기존 Opportunity 연결 Contact만 선택합니다. 이 파일은 서버로 전송하지 않습니다.</small>
      {contactEvidence&&<select id="new-contact-select" value={contactSelection?.contact_id||""}
        onChange={e=>chooseContact(e.target.value)}>
        <option value="">기관·기존 Contact를 직접 선택</option>
        {contactEvidence.candidates.map(c=><option key={c.contact_id} value={c.contact_id}>
          {c.institution_name} · {c.korean_name} · {c.contact_id.slice(-6)}
        </option>)}
      </select>}
      {contactNotice&&<small role="status">{contactNotice}</small>}
      {contactSelection?.ok&&<small>선택된 Account 001 / Contact 003 · 동일 고객 단가 우선 조회 연결 · {contactEvidence?.status==="LIVE_QUOTE_LINKS_RECHECKED"?"원본 조회 완료, 신규 Quote 재승인 필요":"신규 Quote 적용 전 원본 재확인 필요"}</small>}
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
     <div className={styles.buttons}><button className={styles.primary} type="submit">검토용 요청서 확인</button><button type="button" className={styles.secondary} onClick={()=>{setInput({...DEFAULT_INPUT});setProcessDraftProducts([]);setShow(false);setNotice("");setContactEvidence(null);setContactSelection(null);setContactNotice("");}}>초기화</button></div>
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
  <div style={{marginTop:18}}><KrwPricePanel intake={result} customerSelection={contactSelection}
    onDraftChange={setProcessDraftProducts}/></div>
  {show&&<section className={styles.output}><div className={styles.outputTop}><div><h2>검토용 JSON</h2><p>고객 정보와 과거 단가 참고값이 포함됩니다. 공개 저장소에 올리지 마세요.</p></div></div>
   {localProcessReview&&<p className={styles.footnote}>원본 Process 기반 Product 초안 {localProcessReview.quote_products.length}개 포함 · 가격 승인/CRM 저장 없음</p>}
   <pre>{JSON.stringify(reviewedRequest,null,2)}</pre></section>}
  <footer className={styles.footer}>SFDC 신규 생성 초안 · Salesforce write 0건 · 실제 가격 자동 설정 0건</footer>
 </div></main>;
}
