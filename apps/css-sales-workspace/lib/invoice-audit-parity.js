'use strict';
// Legacy tax-invoice coverage audit vs the newer revenue lifecycle snapshot.
// This is a comparison of different reporting sources, NOT proof of payment,
// complete ownership, or invoice issuance outside verified source rows.
const targetMonth='2026-10';
const safeInt=v=>{
 const text=String(v??'').replace(/[₩,\s]/g,'');
 return /^(?:0|[1-9][0-9]*)$/.test(text)&&Number.isSafeInteger(Number(text))?Number(text):null;
};
function projectInvoiceAuditParity(months,legacyRows){
 const base={source:'Tax Invoice Completeness Audit',targetMonth,
   status:'SOURCE_UNAVAILABLE',certified:false};
 const canonical=(months||[]).find(m=>m.month===targetMonth);
 if(!canonical||!Number.isSafeInteger(canonical.invoices)||!Number.isSafeInteger(canonical.actual)||canonical.invoices<0||canonical.actual<0)
   return {...base,status:'CANONICAL_MONTH_UNAVAILABLE'};
 if(!Array.isArray(legacyRows)||legacyRows[0]?.[0]!=='TAX INVOICE COMPLETENESS AUDIT')
   return {...base,status:'LEGACY_AUDIT_UNAVAILABLE'};
 const fields=new Map();
 for(const row of legacyRows.slice(1)){
   const key=String(row?.[0]??'').trim();
   if(key&&!fields.has(key))fields.set(key,String(row?.[1]??'').trim());
 }
 const count=safeInt(fields.get('October invoice count'));
 const unique=safeInt(fields.get('October unique invoice numbers'));
 const amount=safeInt(fields.get('October invoice amount KRW'));
 const date=fields.get('Invoice source last date')||'';
 if(count===null||unique===null||amount===null||!/^20[0-9]{2}-[0-9]{2}-[0-9]{2}$/.test(date))
   return {...base,status:'LEGACY_AUDIT_SCHEMA_REVIEW'};
 const compare={
   ...base,canonicalCount:canonical.invoices,canonicalKRW:canonical.actual,
   canonicalRefreshed:canonical.refreshed||'',legacyCount:count,legacyUniqueCount:unique,
   legacyKRW:amount,legacySourceLastDate:date,
   countDelta:canonical.invoices-count,amountDeltaKRW:canonical.actual-amount
 };
 return {...compare,status:count!==unique||canonical.invoices!==count||
   canonical.actual!==amount?'MISMATCH_REVIEW':'MATCHED_NOT_CERTIFIED'};
}
module.exports={projectInvoiceAuditParity,safeInt,targetMonth};
