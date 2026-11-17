"use client";
import {useMemo} from "react";
import {
 editLocalProcessLine,removeLocalProcessProduct,
 setLocalProductQuantityReviewed,reviewLocalProcessDraft,
 exportLocalOppoQuoteReview
} from "../lib/sfdc-local-process-draft.mjs";

const money=value=>{
 const raw=String(value??"");
 if(!/^\d+(?:\.\d{1,5})?$/.test(raw))return "확인 필요";
 const [whole,part]=raw.split(".");
 return whole.replace(/\B(?=(\d{3})+(?!\d))/g,",")+(part?"."+part:"")+" KRW";
};
const cell={padding:"8px",borderBottom:"1px solid #354c61",fontSize:12,verticalAlign:"middle"};
const input={width:"100%",minWidth:78,background:"#0b192a",border:"1px solid #527084",
 color:"#e4f2fd",borderRadius:6,padding:"7px 8px",fontSize:12};
export default function LocalProcessDraftEditor({products,onProductsChange,intake,customerSelection=null}){
 const summary=useMemo(()=>reviewLocalProcessDraft(products,intake,customerSelection),
  [products,intake,customerSelection]);
 if(!products.length)return null;
 const edit=(p,line,change)=>onProductsChange(
   editLocalProcessLine(products,p.source_qid,p.source_product_signature,line.process_id,change));
 const remove=p=>onProductsChange(
   removeLocalProcessProduct(products,p.source_qid,p.source_product_signature));
 const confirm=(p,checked)=>onProductsChange(
   setLocalProductQuantityReviewed(products,p.source_qid,p.source_product_signature,checked));
 const copy=async()=>{
  const exported=exportLocalOppoQuoteReview(products,intake,customerSelection);
  try{await navigator.clipboard.writeText(JSON.stringify(exported,null,2))}
  catch{window.alert("클립보드 접근 제한: 오른쪽의 검토용 JSON에서 확인하세요.")}
 };
 return <section aria-label="신규 Quote Product별 공정 초안" data-testid="local-process-product-editor"
  style={{border:"1px solid #527084",borderRadius:12,padding:16,marginTop:20}}>
   <h3 style={{fontSize:17,margin:"0 0 6px"}}>신규 Oppo–Quote · Product별 공정 초안 (No Save)</h3>
   <p style={{fontSize:12,lineHeight:1.6}}>
    기존 공정의 원본 수량·단가를 참고값으로 복사했습니다.
    <strong> 신규 수량과 제안 단가를 직접 수정</strong>하고 사용할 공정만 선택하세요.
    원본 Salesforce 수량·단가는 수정되지 않으며, 이 초안은 신규 고객 가격 승인이 아닙니다.
   </p>
   {products.map(p=>{
     const review=summary.products.find(x=>x.source_qid===p.source_qid&&
       x.source_product_signature===p.source_product_signature);
     return <div key={p.source_qid+"|"+p.source_product_signature}
       data-testid="local-quote-product"
       style={{padding:12,border:"1px solid #324c5f",borderRadius:9,marginTop:14}}>
       <div style={{display:"flex",justifyContent:"space-between",gap:12,flexWrap:"wrap"}}>
        <div><strong>{p.source_product_name}</strong>
         <div style={{fontSize:11,marginTop:5}}>참조: {p.source_qid} · {p.source_created_date}
          {" · "}{p.source_review_status==="HOLD"?"원본 HOLD":"과거 가격 비교 전용"}</div>
        </div>
        <button type="button" aria-label={p.source_qid+" Product 초안 삭제"}
         onClick={()=>remove(p)} style={{...input,width:"auto",cursor:"pointer"}}>
          이 Product 제거
        </button>
       </div>
       <div style={{overflowX:"auto",marginTop:12}}>
        <table style={{borderCollapse:"collapse",width:"100%",minWidth:1020}}>
         <thead><tr>{["사용","원본 Process","원본 수량","신규 수량","원본 Unit Price","제안 Unit Price","신규 공정 공급가액","단위·크기"].map((h,i)=>
           <th key={h} scope="col" style={{...cell,textAlign:i===1?"left":"right"}}>{h}</th>)}</tr></thead>
         <tbody>{p.lines.map(line=>{
           const assessed=review?.lines.find(x=>x.process_id===line.process_id);
           return <tr key={line.process_id}>
            <td style={cell}><input type="checkbox"
             aria-label={line.process_id+" 공정 포함"} checked={line.include}
             onChange={e=>edit(p,line,{include:e.target.checked})}/></td>
            <td style={{...cell,minWidth:200}}>
             <strong>{line.process_name}</strong>
             <div style={{fontSize:10,opacity:0.8}}>{line.process_id}</div>
             {line.is_data_release&&<span style={{fontSize:11}}>Data release · Pack 별도 확인</span>}
             {line.is_cloud&&<span style={{fontSize:11}}>AliCloud · 수량 별도 확인</span>}
            </td>
            <td style={cell}>{line.original_process_quantity}</td>
            <td style={cell}><input inputMode="numeric"
             aria-label={line.process_id+" 신규 공정 수량"} style={input}
             disabled={!line.include} value={line.new_process_quantity}
             onChange={e=>edit(p,line,{new_process_quantity:e.target.value})}/></td>
            <td style={cell}>{money(line.original_unit_price_krw)}</td>
            <td style={cell}><input inputMode="decimal"
             aria-label={line.process_id+" 제안 Unit Price KRW"} style={input}
             disabled={!line.include} value={line.proposed_unit_price_krw}
             onChange={e=>edit(p,line,{proposed_unit_price_krw:e.target.value})}/></td>
            <td style={cell}>
             {line.include?money(assessed?.proposed_process_net_krw):"제외"}
             {assessed?.edited_from_source&&<div style={{fontSize:11}}>원본 대비 수정</div>}
            </td>
            <td style={cell}>{line.data_size||"—"} {line.data_unit}</td>
           </tr>})}</tbody>
        </table>
       </div>
       <p style={{fontSize:12,margin:"12px 0 0"}}>
        이 Product 예상 공급가액: <strong>{money(review?.net_krw)}</strong>
        {" · "}Process {money(review?.process_net_krw)}
        {" · "}Cloud {money(review?.cloud_net_krw)}
       </p>
       <label style={{fontSize:12,display:"flex",gap:9,alignItems:"center",marginTop:12}}>
         <input type="checkbox" checked={p.quantity_depth_reviewed===true}
          onChange={e=>confirm(p,e.target.checked)}/>
         신규 샘플 수·생산량·각 Process 수량을 직접 확인함 (별도 가격 승인 아님)
       </label>
       {p.source_review_status==="HOLD"&&<p style={{fontSize:11}}>
         원본 HOLD: {p.source_hold_reason}. 원본 샘플당 가격을 추정하지 않고 공정별 참고값만 복사했습니다.
       </p>}
      </div>;
   })}
   <div role="status" style={{marginTop:14,borderTop:"1px solid #375368",paddingTop:12}}>
    <div style={{fontSize:13}}><strong>상태: {summary.status}</strong> ·
     선택 Product {summary.product_count}개 / Process {summary.selected_process_count}개
    </div>
    <p style={{fontSize:12}}>
     Process 공급가액 {money(summary.process_net_krw)}
     {" · "}Cloud {money(summary.cloud_net_krw)}
     {" · "}공급가액 합계 {money(summary.net_krw)}
    </p>
    <p style={{fontSize:12}}>VAT 10% {money(summary.vat_krw)}
     {" · "}VAT 포함 예상액 {money(summary.gross_krw)}
    </p>
    <p style={{fontSize:11,lineHeight:1.6}}>
     가격·Pack·AliCloud·고객 및 공정 구성은 신규 Quote 기준으로 재검증해야 합니다.
     배송·반송 Quotation Fee는 별도이며 여기서는 제외합니다.
     모든 금액은 검토용이고, SFDC 신규 저장은 수행하지 않습니다.
    </p>
   </div>
   <button type="button" data-testid="copy-local-process-draft"
    onClick={copy} style={{...input,width:"auto",cursor:"pointer"}}>
     신규 Product별 공정 초안 JSON 복사 (로컬 전용)
   </button>
 </section>;
}