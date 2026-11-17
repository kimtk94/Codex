"use client";

/** Local-only, display-only original 2026 KRW native Process line table.
 * The parent preview owns the verified source. This component never writes
 * to Salesforce, alters an Opportunity, or sets a sample unit price.
 */
const money=value=>{
 const text=String(value??"");
 if(!/^\d+(?:\.\d{1,4})?$/.test(text))return "원본 검증 필요";
 const [whole,fraction]=text.split(".");
 return whole.replace(/\B(?=(\d{3})+(?!\d))/g,",")+
   (fraction?"."+fraction:"")+" KRW";
};
const tableStyle={borderCollapse:"collapse",width:"100%",minWidth:720,textAlign:"right",
 fontSize:12};
const cellStyle={padding:"8px 9px",borderBottom:"1px solid #dbe5eb",
 whiteSpace:"nowrap",fontVariantNumeric:"tabular-nums"};
export default function HistoricalKrwProcessBreakdown({group}){
 if(!group||!Array.isArray(group.lines))return null;
 return <section aria-label="원본 KRW 공정 단가 상세" data-testid="historical-krw-process-breakdown"
   style={{marginTop:12,padding:13,border:"1px solid #b9cfdc",
    borderRadius:10,background:"transparent"}}>
   <h4 style={{fontSize:14,margin:"0 0 8px"}}>원본 견적 Product · 공정별 상세</h4>
   <p style={{fontSize:12,margin:"0 0 8px"}}>
    <strong>{group.quote_id}</strong> · {group.product_name} · {group.created_date}
    {" · "}{group.review_status==="HOLD"?"샘플당 단가 HOLD":"과거 단가 비교 가능"}
   </p>
   {group.review_status==="HOLD"&&<p role="status" style={{fontSize:12}}>
     보류 사유: {group.hold_reason||"원본 검증 필요"}.
     원본 공정별 금액을 참고할 수 있지만 신규 견적 단가로 자동 입력하지 않습니다.
   </p>}
   <div style={{overflowX:"auto"}}>
    <table style={tableStyle}>
     <thead><tr>{["원본 Process","Process 수량","Unit Price (KRW)","원본 Process 공급가액","원본 생산량"].map((label,i)=>
       <th key={label} scope="col" style={{...cellStyle,textAlign:i===0?"left":"right"}}>{label}</th>)}</tr></thead>
     <tbody>{group.lines.map((r,i)=><tr key={r.process_id+"-"+i}>
       <td style={{...cellStyle,textAlign:"left",whiteSpace:"normal"}}>
         {r.process_name||r.process_id}
         {r.data_release?" · Data release":r.cloud?" · 별도 Cloud 공정":""}
       </td>
       <td style={cellStyle}>{r.process_quantity}</td>
       <td style={cellStyle}>{money(r.unit_price_krw)}</td>
       <td style={cellStyle}>{money(r.process_net_krw)}</td>
       <td style={cellStyle}>{r.data_size||"—"} {r.data_unit==="NA"?"(단위 미기재)":r.data_unit}</td>
      </tr>)}</tbody>
     <tfoot><tr><th scope="row" colSpan={3} style={{...cellStyle,textAlign:"left"}}>
       원본 Process 합계 · VAT/별도 Quotation Fee 제외
      </th><td style={cellStyle}><strong>{money(group.process_net_krw)}</strong></td>
      <td style={cellStyle}>공정별 수량 적용</td>
     </tr></tfoot>
    </table>
   </div>
   <p style={{fontSize:11,lineHeight:1.6,margin:"10px 0 0"}}>
    원본 공정 수량은 생물학적 샘플 수와 다를 수 있습니다.
    Data release 및 AliCloud는 원본 Process 항목대로 표시하며,
    별도 Quotation Fee(배송·반송비)는 포함하지 않습니다.
    이는 과거 가격 근거 열람이며 새 고객 단가 승인이나 Salesforce 저장이 아닙니다.
   </p>
 </section>;
}
