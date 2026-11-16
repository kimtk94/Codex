"use client";
import {useMemo,useState} from "react";
import styles from "../page.module.css";
import {parseKrwEvidence,rankKrwPrices,candidateSelection} from "../../../../lib/sfdc-2026-krw-price-preview.mjs";

const TIER_LABEL={
 SAME_ACCOUNT_CONTACT:"동일 Account + Contact",
 SAME_ACCOUNT_OTHER_CONTACT:"동일 Account · 다른 Contact",
 OTHER_CUSTOMER_SAME_PRODUCT_PROCESS:"다른 고객 · 동일 Product/Process"
};
const suffix=(x)=>x?.slice(-6)||"—";
const priceText=(s)=>Number(s).toLocaleString("ko-KR",{maximumFractionDigits:4});
export default function KrwPricePanel({intake}){
 const [source,setSource]=useState(null);
 const [notice,setNotice]=useState("");
 const [accountId,setAccountId]=useState("");
 const [contactId,setContactId]=useState("");
 const [product,setProduct]=useState("");
 const [process,setProcess]=useState("");
 const [choice,setChoice]=useState(null);
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
 const query=useMemo(()=>({
  account_id:accountId,contact_id:contactId,product_signature:product,process_id:process,
  data_unit:intake.input.unit,
  data_size:intake.input.production,
  sample_quantity:Number(intake.input.samples),
  production_basis:intake.input.basis
 }),[accountId,contactId,product,process,intake.input.unit,intake.input.production,intake.input.samples,intake.input.basis]);
 const found=useMemo(()=>rankKrwPrices(source,query),[source,query]);
 const selected=choice?candidateSelection(intake,choice):null;
 const upload=async event=>{
  const file=event.currentTarget.files?.[0];
  event.currentTarget.value="";
  setSource(null);setProduct("");setProcess("");setChoice(null);setNotice("");
  if(!file)return;
  if(file.size>2*1024*1024||!file.name.toLowerCase().endsWith(".json")){
   setNotice("JSON 형식, 2MB 이하 파일만 사용할 수 있습니다.");return;
  }
  try{
   const checked=parseKrwEvidence(await file.text());
   setSource(checked);
   setNotice(checked.records.length?
    "파일 형식 확인. 2026 KRW 후보 "+checked.records.length+"행 · 제외 "+checked.excluded_count+"행. 원본 SFDC 재확인 전에는 가격 적용 불가.":
    "2026년 승인된 원본 KRW 단가 행이 없어 가격 검색을 보류합니다.");
  }catch(err){setNotice("자료 검증 실패: "+(err instanceof Error?err.message:"INVALID_EVIDENCE")); }
 };
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
   <label htmlFor="krw-local-file">2026 승인 KRW Quote Process 자료 (로컬 JSON)</label>
   <input id="krw-local-file" type="file" accept=".json,application/json" onChange={upload}/>
   <small>원본 공정 단가, VAT 제외 기준, 활성·승인 Quote, SFDC 001·003 ID가 포함된 규격 파일만 허용합니다. 2025년·USD·환산가격은 자동 제외합니다.</small>
  </div>
  <div className={styles.two}>
   <div className={styles.field}>
    <label htmlFor="krw-account-id">SFDC Account ID · 001</label>
    <input id="krw-account-id" value={accountId} placeholder="인증 SFDC에서 확인한 001 ID" onChange={e=>{setAccountId(e.target.value.trim());setChoice(null);}}/>
   </div>
   <div className={styles.field}>
    <label htmlFor="krw-contact-id">SFDC Contact ID · 003</label>
    <input id="krw-contact-id" value={contactId} placeholder="인증 SFDC에서 확인한 003 ID" onChange={e=>{setContactId(e.target.value.trim());setChoice(null);}}/>
   </div>
  </div>
  <div className={styles.two}>
   <div className={styles.field}>
    <label htmlFor="krw-product">Quote Product 공정 구조</label>
    <select id="krw-product" value={product} disabled={!products.length}
      onChange={e=>{setProduct(e.target.value);setProcess("");setChoice(null);}}>
     <option value="">확인된 구조 선택</option>
     {products.map(([id,label])=><option key={id} value={id}>{label} · {suffix(id)}</option>)}
    </select>
   </div>
   <div className={styles.field}>
    <label htmlFor="krw-process">비교할 Process</label>
    <select id="krw-process" value={process} disabled={!processes.length}
     onChange={e=>{setProcess(e.target.value);setChoice(null);}}>
     <option value="">공정 선택</option>
     {processes.map(([id,label])=><option key={id} value={id}>{label} · {suffix(id)}</option>)}
    </select>
   </div>
  </div>
  <div className={styles.footnote}>
   이번 요청: {intake.input.samples||"—"} samples / {intake.input.production||"—"} {intake.input.unit} ({intake.input.basis==="PER_SAMPLE"?"샘플당":"프로젝트 전체"}).
   생산량 단위가 다르면 비교하지 않습니다. 전체 생산량은 과거 샘플당 생산량과 같은 값으로 간주하지 않습니다.
  </div>
  {notice&&<div className={styles.notice} role="status" aria-live="polite">{notice}</div>}
  <div className={styles.reviewState}><span className={styles.dot}/>
   {!source?"HOLD · 검증된 KRW 가격 파일 미연결":found.status==="LOCAL_REFERENCE_CANDIDATES_UNVERIFIED"?
    "비교 후보 "+found.count+"건 · 모두 재검증 필요":found.status}
  </div>
  {found.candidates.length>0&&<div style={{display:"grid",gap:10,marginTop:15}}>
   {found.candidates.map((item,index)=><div key={item.quote_id+"-"+item.process_id+"-"+index}
      style={{background:"#0b192a",border:"1px solid #38576d",borderRadius:12,padding:13}}>
     <div style={{display:"flex",justifyContent:"space-between",flexWrap:"wrap",gap:7}}>
      <strong style={{fontSize:13}}>{TIER_LABEL[item.tier]}</strong>
      <span style={{fontSize:12,color:"#9bcce4"}}>{priceText(item.unit_price_krw)} KRW / 공정 단가</span>
     </div>
     <div className={styles.footnote} style={{marginTop:7}}>
      {item.quote_id} · {item.created_date} · 생산량 {item.data_size} {item.data_unit} · 샘플 {item.sample_quantity}개
     </div>
     <div className={styles.footnote} style={{marginTop:5}}>
      생산량 일치: {item.size_match?"예":"아니오/확인 필요"} · 샘플 수 일치: {item.quantity_match?"예":"아니오"}
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
  <div className={styles.footnote}>저장·가격 자동 적용·외부 전송: 모두 0건. 이 화면의 가격 선택은 CRM에 입력할 단가 확정이 아닌 검토 참고입니다.</div>
 </section>;
}
