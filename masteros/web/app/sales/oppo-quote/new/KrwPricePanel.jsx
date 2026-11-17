"use client";
import {useEffect,useMemo,useState} from "react";
import styles from "../page.module.css";
import {parseKrwEvidence,rankKrwPrices,candidateSelection,summarizeKrwProductPrices} from "../../../../lib/sfdc-2026-krw-price-preview.mjs";
import {listKrwOriginalProcessGroups} from "../../../../lib/sfdc-pair-index-krw.mjs";
import {addLocalProcessProduct} from "../../../../lib/sfdc-local-process-draft.mjs";
import LocalProcessDraftEditor from "../../../../components/LocalProcessDraftEditor";
import HistoricalKrwProcessBreakdown from "../../../../components/HistoricalKrwProcessBreakdown";

const TIER_LABEL={
 SAME_ACCOUNT_CONTACT:"동일 Account + Contact",
 SAME_ACCOUNT_OTHER_CONTACT:"동일 Account · 다른 Contact",
 SAME_CONTACT_OTHER_ACCOUNT:"동일 Contact · 다른 Account (기관 재확인)",
 OTHER_CUSTOMER_SAME_PRODUCT_PROCESS:"다른 고객 · 동일 Product/Process"
};
const suffix=(x)=>x?.slice(-6)||"—";
const priceText=(s)=>Number(s).toLocaleString("ko-KR",{maximumFractionDigits:4});
const originalMoney=value=>{
 const raw=String(value??"");
 if(!/^\d+(?:\.\d{1,4})?$/.test(raw))return "금액 확인 필요";
 const [int,dec]=raw.split(".");
 return int.replace(/\B(?=(\d{3})+(?!\d))/g,",")+(dec?"."+dec:"");
};
export default function KrwPricePanel({intake,customerSelection=null,onDraftChange=null}){
 const [source,setSource]=useState(null);
 const [localLoading,setLocalLoading]=useState(false);
 const [historyPage,setHistoryPage]=useState(0);
 const [processPage,setProcessPage]=useState(0);
 const [processFilter,setProcessFilter]=useState("HOLD");
 const [processSearch,setProcessSearch]=useState("");
 const [openedProcessGroup,setOpenedProcessGroup]=useState("");
 const [draftProducts,setDraftProducts]=useState([]);
 const [sourceMode,setSourceMode]=useState("NONE");
 const [notice,setNotice]=useState("");
 const [accountId,setAccountId]=useState("");
 const [contactId,setContactId]=useState("");
 const [product,setProduct]=useState("");
 const [process,setProcess]=useState("");
 const [selectedUnit,setSelectedUnit]=useState("");
 const [choice,setChoice]=useState(null);
 const customerLinked=customerSelection?.ok===true&&customerSelection?.requires_server_identity_recheck===true;
 const effectiveAccountId=customerLinked?customerSelection.account_id:accountId;
 const effectiveContactId=customerLinked?customerSelection.contact_id:contactId;
 const products=useMemo(()=>{
  const map=new Map();
  for(const r of source?.records||[])if(!map.has(r.product_signature))map.set(r.product_signature,r.product_name||"Product process fingerprint");
  return Array.from(map.entries());
 },[source]);
 const processes=useMemo(()=>{
  const map=new Map();
  for(const r of source?.records||[])if(r.product_signature===product&&!map.has(r.process_id))map.set(r.process_id,r.process_name||"Process");
  return Array.from(map.entries());
 },[source,product]);
 const availableUnits=useMemo(()=>[...new Set((source?.records||[])
  .filter(r=>r.product_signature===product&&r.process_id===process)
  .map(r=>r.data_unit))],[source,product,process]);
 const effectiveUnit=availableUnits.length===1?availableUnits[0]:selectedUnit;
 const query=useMemo(()=>({
  account_id:effectiveAccountId,contact_id:effectiveContactId,product_signature:product,process_id:process,
  data_unit:effectiveUnit,requested_unit:intake.input.unit,
  data_size:effectiveUnit==="NA"?"":intake.input.production,
  sample_quantity:Number(intake.input.samples),
  production_basis:intake.input.basis
 }),[effectiveAccountId,effectiveContactId,product,process,effectiveUnit,intake.input.unit,intake.input.production,intake.input.samples,intake.input.basis]);
 const found=useMemo(()=>rankKrwPrices(source,query),[source,query]);
 // Stale historical prices must never survive a change of the customer, service,
 // process, depth, production basis or quantity that selected the reference.
 useEffect(()=>{
  setChoice(null);
 },[effectiveAccountId,effectiveContactId,product,process,effectiveUnit,intake.input]);
 const selected=choice?candidateSelection(intake,choice):null;
 const portfolio=useMemo(()=>summarizeKrwProductPrices(source),[source]);
 const originalProcessGroups=useMemo(()=>listKrwOriginalProcessGroups(source),[source]);
 useEffect(()=>{if(onDraftChange)onDraftChange(draftProducts)},[draftProducts,onDraftChange]);
 useEffect(()=>{
   setDraftProducts(prev=>prev.every(p=>p.quantity_depth_reviewed===false)?prev:
     prev.map(p=>({...p,quantity_depth_reviewed:false})));
 },[intake.input.samples,intake.input.production,intake.input.unit,
    intake.input.basis,customerSelection?.account_id,customerSelection?.contact_id]);
 const addDraftProduct=group=>{
   if(sourceMode!=="LOCAL_PRIVATE_VERIFIED"){
     setNotice("HOLD: 검증된 노트북 원본 가격 인덱스만 신규 공정 초안에 복제할 수 있습니다.");
     return;
   }
   const result=addLocalProcessProduct(draftProducts,group);
   if(result.ok){
     setDraftProducts(result.products);
     setNotice("원본 "+group.quote_id+"의 Product 공정을 로컬 초안에 복사했습니다. 신규 수량과 단가를 확인하세요.");
   }else setNotice("초안 추가 보류: "+result.code);
 };
 const displayProcessGroups=useMemo(()=>{
  const query=processSearch.trim().toLocaleLowerCase();
  return originalProcessGroups.groups.filter(g=>
    (processFilter==="ALL"||g.review_status===processFilter)&&
    (!query||(g.quote_id+" "+g.product_name+" "+g.lines.map(x=>x.process_name).join(" "))
      .toLocaleLowerCase().includes(query)));
 },[originalProcessGroups,processFilter,processSearch]);
 const processPages=Math.max(1,Math.ceil(displayProcessGroups.length/20));
 const visibleProcessPage=Math.min(processPage,processPages-1);
 const currentOpenedGroup=displayProcessGroups.find(g=>g.key===openedProcessGroup)||null;
 const historySize=100;
 const historyPages=Math.max(1,Math.ceil(portfolio.group_count/historySize));
 const currentHistoryPage=Math.min(historyPage,historyPages-1);
 const upload=async event=>{
  const file=event.currentTarget.files?.[0];
  event.currentTarget.value="";
  setSource(null);setSourceMode("NONE");setDraftProducts([]);
  setProduct("");setProcess("");setSelectedUnit("");setChoice(null);setHistoryPage(0);setProcessPage(0);setOpenedProcessGroup("");setNotice("");
  if(!file)return;
  if(file.size>2*1024*1024||!file.name.toLowerCase().endsWith(".json")){
   setNotice("JSON 형식, 2MB 이하 파일만 사용할 수 있습니다.");return;
  }
  try{
   const checked=parseKrwEvidence(await file.text());
   setSource(checked);setSourceMode("USER_UPLOADED_UNVERIFIED");setHistoryPage(0);
   setNotice(checked.records.length?
    "파일 형식 확인. 2026 KRW 후보 "+checked.records.length+"행 · 제외 "+checked.excluded_count+"행. 원본 SFDC 재확인 전에는 가격 적용 불가.":
    "2026년 승인된 원본 KRW 단가 행이 없어 가격 검색을 보류합니다.");
  }catch(err){setNotice("자료 검증 실패: "+(err instanceof Error?err.message:"INVALID_EVIDENCE")); }
 };
 const loadPrivatePriceIndex=async()=>{
  if(localLoading)return;
  setLocalLoading(true);
  setSource(null);setSourceMode("NONE");setDraftProducts([]);
  setProduct("");setProcess("");setSelectedUnit("");setChoice(null);setHistoryPage(0);setProcessPage(0);setOpenedProcessGroup("");
  setNotice("PC에 보관된 2026 KRW 가격 인덱스 확인 중...");
  try{
   const response=await fetch("/api/sfdc/krw-price-local",{
    method:"POST",cache:"no-store",credentials:"omit",
    headers:{"Content-Type":"application/json","X-SFDC-Command":"1"},
    body:JSON.stringify({mode:"READ_LOCAL_PRIVATE_2026_KRW"})
   });
   const data=await response.json();
   if(!response.ok||data?.status!=="PASS"||data.local_only!==true||
      data.salesforce_write!==false||!data.evidence)throw Error(data?.code||"LOCAL_PRICE_SOURCE_UNAVAILABLE");
   const checked=parseKrwEvidence(JSON.stringify(data.evidence));
   if(checked.excluded_count>0||checked.records.length!==data.verified_process_rows)
    throw Error("LOCAL_PRICE_SOURCE_RECHECK_FAILED");
   setSource(checked);setSourceMode("LOCAL_PRIVATE_VERIFIED");
   setNotice("PC 원본 가격 파일 "+data.verified_quote_count+"건 Quote / "+
    checked.records.length+"개 2026 KRW 공정 단가 검증 완료. 신규 견적에 자동 적용되지는 않습니다.");
  }catch(e){
   setSource(null);setSourceMode("NONE");setDraftProducts([]);
   setNotice("로컬 원본 가격 확인 보류: "+(e?.message||"SOURCE_UNAVAILABLE")+
      ". 기존 JSON 직접 불러오기는 사용할 수 있습니다.");
  }finally{setLocalLoading(false);}
 };
 // Local-only, read-only price evidence is loaded from the laptop automatically.
 // Guarded API failure is a visible HOLD; neither CRM nor GitHub receives data.
 useEffect(()=>{loadPrivatePriceIndex()},[]);
 const copy=async()=>{
  if(!selected)return;
  try{
   await navigator.clipboard.writeText(JSON.stringify(selected,null,2));
   setNotice("비교 견적 참조정보만 복사했습니다. 신규 가격 적용이나 SFDC 저장은 하지 않았습니다.");
  }catch{
   setNotice("클립보드 접근을 사용할 수 없습니다. 아래 선택한 비교 기준을 확인하세요.");
  }
 };
 return <section className={styles.panel} aria-label="2026 KRW 가격 비교">
  <div className={styles.panelHeader}><span className={styles.stepNo}>05</span><div>
   <h2>2026 KRW 공정별 가격 비교</h2>
   <p>동일 Account·Contact 우선 · 다른 고객 견적 비교 · USD 전면 제외</p>
  </div></div>
  <div className={styles.banner}><span className={styles.bannerIcon}>!</span><span>
   현재 QQ Report에는 원본 KRW 공정 단가가 없습니다. 인증된 2026년 KRW 가격 자료가 있을 때만 이 브라우저에서
   비교할 수 있습니다. 업로드한 자료는 서버로 전송하지 않으며, 파일 자체만으로 SFDC 인증이 증명되지는 않습니다.
  </span></div>
  <div className={styles.field}>
   <button type="button" id="krw-private-price-load" className={styles.secondary}
     disabled={localLoading} onClick={loadPrivatePriceIndex}>
    {localLoading?"로컬 KRW 원본 확인 중":"PC에 저장된 검증 KRW 가격 자동 불러오기"}
   </button>
   <small>이 PC의 승인된 2026년 KRW 공정 가격만 로컬 서버에서 읽습니다. 파일을 GitHub로 업로드하거나 Salesforce에 저장하지 않습니다. 원본이 오래됐거나 불일치하면 차단합니다.</small>
  </div>
  <div className={styles.field}>
   <label htmlFor="krw-local-file">2026 승인 KRW Quote Process 자료 (로컬 JSON)</label>
   <input id="krw-local-file" type="file" accept=".json,application/json" onChange={upload}/>
   <small>원본 공정 단가, VAT 제외 기준, 활성·승인 Quote, SFDC 001·003 ID가 포함된 규격 파일만 허용합니다. 2025년·USD·환산가격은 자동 제외합니다.</small>
  </div>
  <div className={styles.two}>
   <div className={styles.field}>
    <label htmlFor="krw-account-id">SFDC Account ID · 001</label>
    <input id="krw-account-id" value={effectiveAccountId} disabled={customerLinked} placeholder="인증 SFDC에서 확인한 001 ID" onChange={e=>{setAccountId(e.target.value.trim());setChoice(null);}}/>
   </div>
   <div className={styles.field}>
    <label htmlFor="krw-contact-id">SFDC Contact ID · 003</label>
    <input id="krw-contact-id" value={effectiveContactId} disabled={customerLinked} placeholder="인증 SFDC에서 확인한 003 ID" onChange={e=>{setContactId(e.target.value.trim());setChoice(null);}}/>
   </div>
  </div>
  {customerLinked&&<div className={styles.footnote}>입력한 한글 이름의 기존 Contact를 선택해 Account·Contact ID가 연결됐습니다. 현재 로컬 증거 기준이며 신규 Quote 적용 전 실시간 Salesforce 확인이 필요합니다.</div>}
  <div className={styles.two}>
   <div className={styles.field}>
    <label htmlFor="krw-product">Quote Product 공정 구조</label>
    <select id="krw-product" value={product} disabled={!products.length}
      onChange={e=>{setProduct(e.target.value);setProcess("");setSelectedUnit("");setChoice(null);}}>
     <option value="">확인된 구조 선택</option>
     {products.map(([id,label])=><option key={id} value={id}>{label} · {suffix(id)}</option>)}
    </select>
   </div>
   <div className={styles.field}>
    <label htmlFor="krw-process">비교할 Process</label>
    <select id="krw-process" value={process} disabled={!processes.length}
     onChange={e=>{setProcess(e.target.value);setSelectedUnit("");setChoice(null);}}>
     <option value="">공정 선택</option>
     {processes.map(([id,label])=><option key={id} value={id}>{label} · {suffix(id)}</option>)}
    </select>
   </div>
  </div>
  <div className={styles.field}>
   <label htmlFor="krw-process-unit">선택한 Process의 과거 Data Unit (별도 확인)</label>
   <select id="krw-process-unit" value={effectiveUnit} disabled={!availableUnits.length}
    onChange={e=>{setSelectedUnit(e.target.value);setChoice(null);}}>
    {availableUnits.length!==1&&<option value="">공정 단위를 선택하세요</option>}
    {availableUnits.map(u=><option key={u} value={u}>{u==="NA"?"원본 단위 미기재 (생산량 비교 불가)":u}</option>)}
   </select>
   <small>QC·Data release처럼 Data Unit이 빈 공정은 임의로 Gb를 채우지 않습니다. 각 Process 단위를 따로 선택해야 합니다.</small>
  </div>
  <div className={styles.footnote}>
   이번 요청: {intake.input.samples||"—"} samples / {intake.input.production||"—"} {intake.input.unit} ({intake.input.basis==="PER_SAMPLE"?"샘플당":"프로젝트 전체"}).
   생산량 단위가 다르면 비교하지 않습니다. 전체 생산량은 과거 샘플당 생산량과 같은 값으로 간주하지 않습니다.
  </div>
  {source&&portfolio.group_count>0&&<details style={{marginTop:15,padding:14,border:"1px solid #38576d",borderRadius:12,background:"#0b192a"}}>
   <summary style={{cursor:"pointer",fontWeight:700,fontSize:13,color:"#c9e7f8"}}>
    2026 KRW Product별 가격 이력 전체표 · {portfolio.product_count}개 Product / {portfolio.quote_count}개 Quote / {portfolio.group_count}개 조건
   </summary>
   <div style={{marginTop:12,maxHeight:400,overflow:"auto"}}>
    <table style={{borderCollapse:"collapse",width:"100%",minWidth:900,fontSize:11,textAlign:"left"}}>
     <thead><tr>{["Product","Process","Data Unit","Data Size","견적 수","고객 기관","샘플 수","최저 KRW","중앙 KRW","최고 KRW"].map(t=><th key={t} style={{position:"sticky",top:0,background:"#162c40",borderBottom:"1px solid #49667d",padding:8,color:"#d0e6f6"}}>{t}</th>)}</tr></thead>
     <tbody>{portfolio.groups.slice(currentHistoryPage*historySize,(currentHistoryPage+1)*historySize).map((g,i)=><tr key={g.product_signature+"-"+g.process_id+"-"+g.data_unit+"-"+g.data_size+"-"+i}>
      <td style={{padding:8,borderBottom:"1px solid #253b50"}}>{g.product_name}</td>
      <td style={{padding:8,borderBottom:"1px solid #253b50"}}>{g.process_name}</td>
      <td style={{padding:8,borderBottom:"1px solid #253b50"}}>{g.data_unit==="NA"?"미기재":g.data_unit}</td>
      <td style={{padding:8,borderBottom:"1px solid #253b50"}}>{g.data_size||"미기재"}</td>
      <td style={{padding:8,borderBottom:"1px solid #253b50"}}>{g.quote_count}</td>
      <td style={{padding:8,borderBottom:"1px solid #253b50"}}>{g.account_count}</td>
      <td style={{padding:8,borderBottom:"1px solid #253b50"}}>{g.sample_min===g.sample_max?g.sample_min:g.sample_min+"–"+g.sample_max}</td>
      <td style={{padding:8,borderBottom:"1px solid #253b50"}}>{priceText(g.unit_price_min_krw)}</td>
      <td style={{padding:8,borderBottom:"1px solid #253b50"}}>{priceText(g.unit_price_median_krw)}</td>
      <td style={{padding:8,borderBottom:"1px solid #253b50"}}>{priceText(g.unit_price_max_krw)}</td>
     </tr>)}</tbody>
    </table>
   </div>
   <div style={{display:"flex",gap:10,alignItems:"center",flexWrap:"wrap",marginTop:12}}>
    <button type="button" className={styles.secondary}
     disabled={currentHistoryPage===0}
     onClick={()=>setHistoryPage(n=>Math.max(0,n-1))}>이전 가격 조건</button>
    <span style={{fontSize:12}}>전체 {portfolio.group_count}개 조건 · {currentHistoryPage+1} / {historyPages} 페이지 (페이지당 {historySize}개)</span>
    <button type="button" className={styles.secondary}
     disabled={currentHistoryPage>=historyPages-1}
     onClick={()=>setHistoryPage(n=>Math.min(historyPages-1,n+1))}>다음 가격 조건</button>
   </div>
   <div className={styles.footnote}>원본 2026 KRW 견적의 공정별 관측 단가입니다. Product 공정 구성·생산량·샘플 수가 다르면 다른 가격일 수 있으며, 0원 공정은 패키지 포함 가능성이 있습니다. 신규 견적 적용은 건별 재승인 필수입니다.</div>
  </details>}
  {source&&originalProcessGroups.total>0&&<details open
    data-testid="original-process-groups" style={{marginTop:16,padding:14,border:"1px solid #38576d",borderRadius:12}}>
    <summary style={{cursor:"pointer",fontSize:13,fontWeight:700}}>
      원본 견적별 공정 내역 · {originalProcessGroups.total}개 Product /
      HOLD {originalProcessGroups.heldCount}개 · 자동 단가 입력 없음
    </summary>
    <p className={styles.footnote}>보류된 Product도 원본 Process 수량×Unit Price와 합계까지 열람합니다.
      샘플당 KRW 금액이 소수인 경우 반올림하지 않으며, 별도 배송·반송 Fee는 더하지 않습니다.</p>
    <div className={styles.two}>
     <div className={styles.field}>
      <label htmlFor="original-krw-process-filter">원본 공정 검증 상태</label>
      <select id="original-krw-process-filter" value={processFilter}
       onChange={e=>{setProcessFilter(e.target.value);setProcessPage(0);setOpenedProcessGroup("");}}>
       <option value="HOLD">자동 단가 산출 보류</option>
       <option value="COMPARISON_ONLY">과거 샘플당 단가 비교 가능</option>
       <option value="ALL">전체 원본 Product</option>
      </select>
     </div>
     <div className={styles.field}>
      <label htmlFor="original-krw-process-search">Quote 번호·Product·Process 검색</label>
      <input id="original-krw-process-search" value={processSearch}
        onChange={e=>{setProcessSearch(e.target.value);setProcessPage(0);setOpenedProcessGroup("");}}
        placeholder="QID / mRNA / Data release"/>
     </div>
    </div>
    <p className={styles.footnote} role="status">선택된 원본 Product {displayProcessGroups.length}개.
      실제 신규 견적 적용은 원본 단가 재확인 및 건별 승인 후에만 가능합니다.</p>
    <div style={{maxHeight:390,overflow:"auto"}}>
     <table style={{borderCollapse:"collapse",width:"100%",minWidth:720,fontSize:12}}>
      <thead><tr>{["원본 Quote","Product","원본 Process","공급가액 합계 (VAT 제외)","상태","열람","초안"].map(h=>
       <th key={h} scope="col" style={{padding:9,textAlign:"left",borderBottom:"1px solid #49667d"}}>{h}</th>)}</tr></thead>
      <tbody>{displayProcessGroups.slice(visibleProcessPage*20,(visibleProcessPage+1)*20).map(g=>
       <tr key={g.key}>
        <td style={{padding:9,borderBottom:"1px solid #253b50"}}>{g.quote_id}</td>
        <td style={{padding:9,borderBottom:"1px solid #253b50"}}>{g.product_name}</td>
        <td style={{padding:9,borderBottom:"1px solid #253b50"}}>{g.line_count}행</td>
        <td style={{padding:9,borderBottom:"1px solid #253b50"}}>{originalMoney(g.process_net_krw)} KRW</td>
        <td style={{padding:9,borderBottom:"1px solid #253b50"}}>
          {g.review_status==="HOLD"?"HOLD · 원본 공정 조회":"비교 전용"}
        </td>
        <td style={{padding:9,borderBottom:"1px solid #253b50"}}>
         <button type="button" className={styles.secondary}
          aria-label={g.quote_id+" 원본 공정 보기"}
          onClick={()=>setOpenedProcessGroup(old=>old===g.key?"":g.key)}>
          {openedProcessGroup===g.key?"닫기":"공정 보기"}
         </button>
        </td>
        <td style={{padding:9,borderBottom:"1px solid #253b50"}}>
         <button type="button" className={styles.secondary}
           aria-label={g.quote_id+" "+g.product_name+" 신규 Product 초안에 추가"}
           disabled={sourceMode!=="LOCAL_PRIVATE_VERIFIED"||
             draftProducts.some(p=>p.source_qid===g.quote_id&&p.source_product_signature===g.product_signature)}
           onClick={()=>addDraftProduct(g)}>신규 Product에 복사</button>
        </td>
       </tr>)}</tbody>
     </table>
    </div>
    <div style={{display:"flex",alignItems:"center",gap:10,flexWrap:"wrap",marginTop:12}}>
     <button className={styles.secondary} type="button" disabled={visibleProcessPage===0}
       onClick={()=>{setProcessPage(x=>Math.max(0,x-1));setOpenedProcessGroup("");}}>
       이전 원본 Product
     </button>
     <span style={{fontSize:12}}>{visibleProcessPage+1} / {processPages} 페이지 · 페이지당 20개</span>
     <button className={styles.secondary} type="button" disabled={visibleProcessPage>=processPages-1}
       onClick={()=>{setProcessPage(x=>Math.min(processPages-1,x+1));setOpenedProcessGroup("");}}>
       다음 원본 Product
     </button>
    </div>
    {currentOpenedGroup&&<HistoricalKrwProcessBreakdown group={currentOpenedGroup}/>}
   </details>}
  <LocalProcessDraftEditor products={draftProducts} onProductsChange={setDraftProducts}
   intake={intake} customerSelection={customerSelection}/>
  {sourceMode==="USER_UPLOADED_UNVERIFIED"&&<p className={styles.footnote}>
    업로드한 JSON 파일은 원본 인증을 보장하지 않습니다. 공정 상세 조회는 가능하지만
    신규 Product 초안 복사는 검증된 PC 원본 가격 인덱스에서만 허용됩니다.
  </p>}
  {notice&&<div className={styles.notice} role="status" aria-live="polite">{notice}</div>}
  <div className={styles.reviewState}><span className={styles.dot}/>
   {!source?"HOLD · 검증된 KRW 가격 파일 미연결":found.status==="LOCAL_REFERENCE_CANDIDATES_UNVERIFIED"?
    "동일 생산량 후보 "+found.exact_count+"건 / 비교 전체 "+found.count+"건 · 원본 재검증 필요 · 신규 가격 승인 아님":
    found.status==="LOCAL_CONDITION_MISMATCH_CANDIDATES_ONLY"?
    "동일 생산량 일치 없음 · 조건 다른 과거 견적 "+found.count+"건 참고만 가능":
    found.status==="HOLD_REQUESTED_SOURCE_UNIT_MISMATCH"?
    "조회 단위와 요청 생산량 단위가 다릅니다. 가격 비교 중단":
    found.status}
  </div>
  {found.candidates.length>0&&<div style={{display:"grid",gap:10,marginTop:15}}>
   {found.candidates.map((item,index)=><div key={item.quote_id+"-"+item.process_id+"-"+index}
      style={{background:"#0b192a",border:"1px solid #38576d",borderRadius:12,padding:13}}>
     <div style={{display:"flex",justifyContent:"space-between",flexWrap:"wrap",gap:7}}>
      <strong style={{fontSize:13}}>{TIER_LABEL[item.tier]}</strong>
      <span style={{fontSize:12,color:"#9bcce4"}}>{priceText(item.unit_price_krw)} KRW / 공정 단가</span>
     </div>
     <div className={styles.footnote} style={{marginTop:7}}>
      {item.quote_id} · {item.created_date} · 원본 생산량 {item.data_size||"원본 미기재"} {item.data_unit==="NA"?"(단위 미기재)":item.data_unit} · 공정 수량 {item.sample_quantity} (생물학적 샘플 수와 다를 수 있음)
     </div>
     <div className={styles.footnote} style={{marginTop:5}}>
      {item.exact_production_match?"동일 생산량·단위":"원본 생산량 또는 기준 불일치 · 참고만"} · 공정 수량 일치: {item.quantity_match?"예":"아니오"}
     </div>
     <button type="button" className={styles.secondary} onClick={()=>{setChoice(item);setNotice("참고 Quote를 선택했습니다. 단가 적용 전 원본·승인·고객 조건 재확인 필수입니다.");}}
      style={{marginTop:10}}>비교 견적으로 선택</button>
    </div>)}
   </div>}
  {selected&&<div className={styles.output} style={{marginTop:15,padding:14}}>
   <h3 style={{fontSize:14}}>선택한 가격 참고 견적 (적용 전 재검증)</h3>
   <pre>{JSON.stringify(selected,null,2)}</pre>
   <button type="button" className={styles.secondary} onClick={copy}>참고 견적 JSON 복사</button>
  </div>}
  <div className={styles.footnote}>0원 공정은 다른 공정에 가격이 묶여 있을 수 있습니다. 공정 단가만이 아닌 Product 전체 구성을 비교해야 합니다.</div>
  <div className={styles.footnote}>저장·가격 자동 적용·외부 전송: 모두 0건. 이 화면의 가격 선택은 CRM에 입력할 단가 확정이 아닌 검토 참고입니다.</div>
 </section>;
}
