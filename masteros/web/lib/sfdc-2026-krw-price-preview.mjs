/**
 * Browser-local 2026 original-KRW SFDC process-price comparison.
 * JSON source is user-provided: schema validation is NOT proof of Salesforce
 * identity or rate approval. All candidates require authenticated readback.
 * Never sends network requests, persists data or auto-applies prices.
 */
const EVIDENCE_VERSION="sfdc-2026-krw-process-prices-v1";
const SOURCE="SFDC_AUTHENTICATED_READ_ONLY_KRW_PROCESS_LINES";
const REQUIRED_SOURCE="VERIFIED_SFDC_KRW_PROCESS_PRICE";
const A=/^001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;
const C=/^003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;
const Q=/^QID-[0-9-]{8,50}$/;
const P=/^Process-[A-Za-z0-9-]{8,64}$/;
const PRODUCT=/^[A-Za-z0-9:_-]{8,128}$/;
const UNITS=new Set(["Gb","M raw reads","Lane","K tags","Cell","K Reads","K Clean Reads","NA","sample"]);
const SAFE_DATE=/^2026-\d{2}-\d{2}$/;
const MONEY=/^\d{1,9}(?:\.\d{1,4})?$/;
const safeDate=v=>{
 if(typeof v!=="string"||!SAFE_DATE.test(v))return false;
 const date=new Date(v+"T00:00:00Z");
 return Number.isFinite(date.valueOf())&&date.toISOString().slice(0,10)===v;
};
const validId=(id,rx)=>typeof id==="string"&&rx.test(id)?id.slice(0,15):"";
const quantity=v=>Number.isInteger(v)&&v>0&&v<=1000000;
const decimal=v=>typeof v==="string"&&MONEY.test(v)&&Number.isFinite(Number(v))?Number(v):null;
export function canonicalPriceUnit(unit){
 if(unit==="G raw data"||unit==="Gb")return "Gb";
 return typeof unit==="string"?unit.trim():"";
}
export function verifyPriceLine(row){
 if(!row||typeof row!=="object"||Array.isArray(row))return "INVALID_RECORD";
 if(row.source_kind!==REQUIRED_SOURCE||row.source_verified!==true)return "UNVERIFIED_SOURCE";
 if(row.currency!=="KRW"||row.was_usd_converted!==false)return "NOT_NATIVE_KRW";
 if(row.vat_basis!=="VAT_EXCLUDED")return "VAT_BASIS_UNVERIFIED";
 if(!safeDate(row.created_date))return "OUTSIDE_2026";
 if(row.approval_status!=="APPROVED"||row.active!==true)return "NOT_APPROVED_ACTIVE";
 if(typeof row.quote_id!=="string"||!Q.test(row.quote_id))return "QUOTE_ID_UNVERIFIED";
 if(!validId(row.account_id,A))return "ACCOUNT_001_UNVERIFIED";
 if(!validId(row.contact_id,C))return "CONTACT_003_UNVERIFIED";
 if(typeof row.process_id!=="string"||!P.test(row.process_id))return "PROCESS_ID_UNVERIFIED";
 if(typeof row.product_signature!=="string"||!PRODUCT.test(row.product_signature))return "PRODUCT_SIGNATURE_UNVERIFIED";
 if(!UNITS.has(canonicalPriceUnit(row.data_unit)))return "UNIT_UNVERIFIED";
 if(decimal(row.unit_price_krw)===null)return "KRW_UNIT_PRICE_MISSING";
 if(canonicalPriceUnit(row.data_unit)!=="NA"&&decimal(String(row.data_size??""))===null)return "DATA_SIZE_MISSING";
 if(!quantity(row.sample_quantity))return "SAMPLE_QUANTITY_MISSING";
 return "PASS";
}
export function parseKrwEvidence(text,now=Date.now()){
 if(typeof text!=="string"||text.length>2*1024*1024)throw Error("FILE_TOO_LARGE");
 let root;
 try{root=JSON.parse(text);}catch{throw Error("INVALID_JSON");}
 if(!root||typeof root!=="object"||Array.isArray(root)||root.version!==EVIDENCE_VERSION||
    root.source!==SOURCE||root.salesforce_write_performed!==false||
    !Array.isArray(root.records)||root.records.length>5000||root.records.length===0)throw Error("INVALID_EVIDENCE_SCHEMA");
 const generated=Date.parse(root.generated_at);
 if(!Number.isFinite(generated)||generated>now+10*60*1000||generated<now-24*3600*1000)throw Error("STALE_OR_FUTURE_LOCAL_EVIDENCE");
 const rejected={};const records=[];
 for(const raw of root.records){
  const reason=verifyPriceLine(raw);
  if(reason!=="PASS"){rejected[reason]=(rejected[reason]||0)+1;continue;}
  const item={
   quote_id:raw.quote_id,created_date:raw.created_date,account_id:raw.account_id,contact_id:raw.contact_id,
   process_id:raw.process_id,product_signature:raw.product_signature,
   unit_price_krw:raw.unit_price_krw,data_unit:canonicalPriceUnit(raw.data_unit),
   data_size:String(raw.data_size),sample_quantity:raw.sample_quantity,
   process_name:typeof raw.process_name==="string"&&raw.process_name.length<=100?raw.process_name:"",
   product_name:typeof raw.product_name==="string"&&raw.product_name.length<=100?raw.product_name:""
  };
  records.push(item);
 }
 return {status:records.length?"LOCAL_FILE_SCHEMA_OK_AUTH_RECHECK_REQUIRED":"HOLD_NO_ELIGIBLE_KRW_LINES",
  source:SOURCE,generated_at:root.generated_at,records,rejected,
  excluded_count:root.records.length-records.length,
  source_authenticated_in_browser:false,prices_approved_for_new_quote:false,
  crm_writes:0};
}
export function rankKrwPrices(evidence,query,limit=15){
 if(!evidence?.records?.length)return {status:"HOLD_NO_KRW_PRICE_EVIDENCE",candidates:[],crm_writes:0,price_auto_apply:false};
 const product=String(query?.product_signature||"");
 const process=String(query?.process_id||"");
 const unit=canonicalPriceUnit(query?.data_unit);
 if(!PRODUCT.test(product)||!P.test(process))return {status:"HOLD_PRODUCT_PROCESS_SELECTION",candidates:[],crm_writes:0,price_auto_apply:false};
 if(!UNITS.has(unit))return {status:"HOLD_DATA_UNIT_SELECTION",candidates:[],crm_writes:0,price_auto_apply:false};
 const account=validId(query?.account_id,A),contact=validId(query?.contact_id,C);
 const qty=query?.sample_quantity;
 const size=decimal(String(query?.data_size??""));
 const exactBasis=query?.production_basis==="PER_SAMPLE";
 const chosen=[];
 for(const r of evidence.records){
  if(r.product_signature!==product||r.process_id!==process||r.data_unit!==unit)continue;
  const a=validId(r.account_id,A),c=validId(r.contact_id,C);
  const tier=account&&contact&&a===account&&c===contact?"SAME_ACCOUNT_CONTACT":
      account&&a===account?"SAME_ACCOUNT_OTHER_CONTACT":"OTHER_CUSTOMER_SAME_PRODUCT_PROCESS";
  const tierOrder=tier==="SAME_ACCOUNT_CONTACT"?0:tier==="SAME_ACCOUNT_OTHER_CONTACT"?1:2;
  const sizeMatch=exactBasis&&size!==null&&r.data_size!==""&&Number(r.data_size)===size;
  const quantityMatch=quantity(qty)&&qty===r.sample_quantity;
  chosen.push({...r,tier,size_match:sizeMatch,quantity_match:quantityMatch,
   comparison_only:true,source_recheck_required:true,price_auto_apply:false,
   _sort:[tierOrder,sizeMatch?0:1,quantityMatch?0:1,-Number(r.created_date.replaceAll("-",""))]});
 }
 chosen.sort((a,b)=>{for(let i=0;i<a._sort.length;i++){if(a._sort[i]!==b._sort[i])return a._sort[i]-b._sort[i];}return a.quote_id.localeCompare(b.quote_id)});
 return {status:chosen.length?"LOCAL_REFERENCE_CANDIDATES_UNVERIFIED":"NO_MATCHING_2026_KRW_LINES",
   candidates:chosen.slice(0,limit).map(({_sort,...r})=>r),count:chosen.length,
   source_recheck_required:true,price_auto_apply:false,crm_writes:0};
}
export function candidateSelection(intake,candidate){
 if(!candidate)return null;
 return {
  reference_quote_id:candidate.quote_id,
  reference_process_id:candidate.process_id,
  historical_unit_price_krw:candidate.unit_price_krw,
  historical_data_unit:candidate.data_unit,
  historical_data_size:candidate.data_size,
  historical_sample_quantity:candidate.sample_quantity,
  reference_tier:candidate.tier,
  created_date:candidate.created_date,
  state:"COMPARISON_ONLY_REQUIRES_AUTHENTICATED_PRICE_RECHECK",
  applied_to_new_quote:false,crm_writes:0,
  requested_service:intake?.input?.service||"UNVERIFIED"
 };
}


/** Group locally reviewed 2026 KRW prices by exact Product, Process, Unit and Data Size.
 * These are historical ranges, never a default or an approval for the new Quote.
 * Include 0-unit-price bundled steps without calling them free.
 */
export function summarizeKrwProductPrices(evidence) {
 const rows=Array.isArray(evidence?.records)?evidence.records:[];
 const groups=new Map(),quotes=new Set(),products=new Set();
 for(const r of rows) {
  const price=Number(r.unit_price_krw);
  if(!Number.isFinite(price)||price<0)continue;
  const key=JSON.stringify([r.product_signature,r.process_id,r.data_unit,r.data_size]);
  let group=groups.get(key);
  if(!group){
   group={product_signature:r.product_signature,product_name:r.product_name||"Product",
    process_id:r.process_id,process_name:r.process_name||"Process",
    data_unit:r.data_unit,data_size:r.data_size,prices:[],quotes:new Set(),
    accounts:new Set(),sample_quantities:[]};
   groups.set(key,group);
  }
  group.prices.push(price);
  group.quotes.add(r.quote_id);
  group.accounts.add(r.account_id);
  group.sample_quantities.push(r.sample_quantity);
  quotes.add(r.quote_id);
  products.add(r.product_signature);
 }
 const summary=[...groups.values()].map(g=>{
  const p=g.prices.sort((a,b)=>a-b);
  const n=p.length,mid=Math.floor(n/2);
  return {
   product_signature:g.product_signature,product_name:g.product_name,
   process_id:g.process_id,process_name:g.process_name,
   data_unit:g.data_unit,data_size:g.data_size,
   quote_count:g.quotes.size,account_count:g.accounts.size,
   unit_price_min_krw:p[0],unit_price_median_krw:n%2?p[mid]:(p[mid-1]+p[mid])/2,
   unit_price_max_krw:p[n-1],sample_min:Math.min(...g.sample_quantities),
   sample_max:Math.max(...g.sample_quantities),historical_reference_only:true
  };
 });
 summary.sort((a,b)=>a.product_name.localeCompare(b.product_name)
  ||a.process_name.localeCompare(b.process_name)
  ||a.data_unit.localeCompare(b.data_unit)
  ||String(a.data_size).localeCompare(String(b.data_size))
  ||a.product_signature.localeCompare(b.product_signature));
 return {product_count:products.size,quote_count:quotes.size,process_line_count:rows.length,
  group_count:summary.length,groups:summary,price_auto_apply:false,crm_writes:0};
}
