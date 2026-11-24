/** Browser-local 2026 KRW original Process -> NEW Quote Product draft.
 * Explicit copy only. Source prices never become approved new-customer prices.
 * All original and edited amounts are calculated as exact decimal BigInt.
 * No fetch, server action, Salesforce mutation, or persisted storage.
 */
const SOURCE_ID=/^QID-[0-9-]{8,50}$/;
const PRODUCT_HASH=/^[a-f0-9]{64}$/i;
const PROCESS_ID=/^Process-[A-Za-z0-9-]{8,64}$/;
const MAX_PRODUCTS=8;
const MAX_ROWS=40;
const RATE=/^(?:0|[1-9]\d{0,11})(?:\.\d{1,4})?$/;
const QTY=/^[1-9]\d{0,5}$/;
const CLOUD=/ali\s*cloud|cloud storage|cloud service/i;
const RELEASE=/^data release$/i;

const scaled=(value)=>{
 if(typeof value!=="string"||!RATE.test(value))return null;
 const [whole,frac=""]=value.split(".");
 return BigInt(whole)*10000n+BigInt((frac+"0000").slice(0,4));
};
const format=(value,places=4)=>{
 const denom=10n**BigInt(places),major=value/denom;
 const fraction=(value%denom).toString().padStart(places,"0").replace(/0+$/,"");
 return major.toString()+(fraction?"."+fraction:"");
};
const isQuantity=value=>typeof value==="string"&&QTY.test(value)&&Number(value)<=100000;
const sameSource=(a,b)=>a.source_qid===b.source_qid&&
 a.source_product_signature===b.source_product_signature;

export function createLocalProcessProduct(group){
 if(!group||!SOURCE_ID.test(group.quote_id)||
   !PRODUCT_HASH.test(group.product_signature)||
   !["HOLD","COMPARISON_ONLY"].includes(group.review_status)||
   group.fee_included!==false||group.sample_rate_auto_applicable!==false||
   group.crm_writes!==0||!Array.isArray(group.lines)||
   group.lines.length<1||group.lines.length>MAX_ROWS)
  return {ok:false,code:"HOLD_VERIFIED_SOURCE_PRODUCT_REQUIRED"};
 const seen=new Set(),lines=[];
 for(const r of group.lines){
  const key=r?.process_id;
  if(!PROCESS_ID.test(key)||seen.has(key)||
    !isQuantity(String(r.process_quantity))||
    scaled(String(r.unit_price_krw))===null||
    !["Gb","M raw reads","NA","sample","K tags","Lane","Cell"].includes(r.data_unit))
   return {ok:false,code:"HOLD_PROCESS_SOURCE_LINE_AMBIGUOUS"};
  seen.add(key);
  lines.push({
   process_id:key,process_name:String(r.process_name||""),
   data_unit:r.data_unit,data_size:String(r.data_size??""),
   original_process_quantity:String(r.process_quantity),
   original_unit_price_krw:String(r.unit_price_krw),
   new_process_quantity:String(r.process_quantity),
   proposed_unit_price_krw:String(r.unit_price_krw),
   include:true,is_cloud:CLOUD.test(r.process_name),is_data_release:RELEASE.test(r.process_name)
  });
 }
 return {ok:true,code:"SOURCE_PRODUCT_COPIED_FOR_LOCAL_REVIEW_ONLY",
  product:{
   source_qid:group.quote_id,
   source_product_signature:group.product_signature,
   source_product_name:group.product_name||"Product",
   source_created_date:group.created_date||"",
   source_account_id:group.account_id,
   source_contact_id:group.contact_id,
   source_review_status:group.review_status,
   source_hold_reason:group.hold_reason,
   source_process_net_krw:group.process_net_krw,
   quantity_depth_reviewed:false,
   lines
  },crm_writes:0,new_price_approved:false};
}

export function addLocalProcessProduct(existing,group){
 if(!Array.isArray(existing)||existing.length>=MAX_PRODUCTS)
  return {ok:false,code:"HOLD_DRAFT_PRODUCT_LIMIT",products:existing||[]};
 const next=createLocalProcessProduct(group);
 if(!next.ok)return {...next,products:existing};
 if(existing.some(p=>sameSource(p,next.product)))
  return {ok:false,code:"HOLD_PRODUCT_ALREADY_IN_DRAFT",products:existing};
 return {ok:true,code:next.code,products:[...existing,next.product]};
}

export function editLocalProcessLine(products,sourceQid,signature,processId,changes){
 if(!Array.isArray(products)||!changes||typeof changes!=="object"||
   Object.keys(changes).some(k=>!["include","new_process_quantity","proposed_unit_price_krw"].includes(k)))
  return products;
 return products.map(product=>{
  if(product.source_qid!==sourceQid||product.source_product_signature!==signature)return product;
  return {...product,quantity_depth_reviewed:false,lines:product.lines.map(line=>{
   if(line.process_id!==processId)return line;
   const next={...line};
   if(typeof changes.include==="boolean")next.include=changes.include;
   if(typeof changes.new_process_quantity==="string")
    next.new_process_quantity=changes.new_process_quantity.slice(0,8);
   if(typeof changes.proposed_unit_price_krw==="string")
    next.proposed_unit_price_krw=changes.proposed_unit_price_krw.slice(0,24);
   return next;
  })};
 });
}

export function setLocalProductQuantityReviewed(products,sourceQid,signature,reviewed){
 if(!Array.isArray(products))return [];
 return products.map(p=>p.source_qid===sourceQid&&p.source_product_signature===signature?
  {...p,quantity_depth_reviewed:reviewed===true}:p);
}

export function removeLocalProcessProduct(products,sourceQid,signature){
 if(!Array.isArray(products))return [];
 return products.filter(p=>p.source_qid!==sourceQid||p.source_product_signature!==signature);
}

export function reviewLocalProcessDraft(products,intake,customerSelection=null){
 const invalid=(code)=>({status:code,products:[],product_count:0,
   process_count:0,selected_process_count:0,
   process_net_krw:null,cloud_net_krw:null,net_krw:null,
   vat_krw:null,gross_krw:null,
   price_approved:false,salesforce_save_allowed:false,crm_writes:0});
 if(!Array.isArray(products)||!products.length||products.length>MAX_PRODUCTS)
  return invalid("HOLD_NO_LOCAL_PRODUCT_DRAFT");
 const input=intake?.input||{};
 const account=customerSelection?.ok?customerSelection.account_id:null;
 const contact=customerSelection?.ok?customerSelection.contact_id:null;
 const results=[];
 let processNet=0n,cloudNet=0n,count=0,invalidLine=false,
  sourceMismatch=false,quantityMismatch=false,unreviewed=false,mixedSources=false;
 const signatures=new Set();
 for(const product of products){
  const groupKey=product.source_qid+"|"+product.source_product_signature;
  if(signatures.has(groupKey)||!SOURCE_ID.test(product.source_qid)||
     !PRODUCT_HASH.test(product.source_product_signature)||
     !Array.isArray(product.lines)||product.lines.length>MAX_ROWS)
    return invalid("HOLD_SOURCE_PRODUCT_CHANGED");
  signatures.add(groupKey);
  if(!product.quantity_depth_reviewed)unreviewed=true;
  if(account&&contact&&
    (product.source_account_id!==account||product.source_contact_id!==contact))
    mixedSources=true;
  let localProcess=0n,localCloud=0n;
  let selectedCount=0;
  const lines=[];
  for(const line of product.lines){
   if(line.include!==true){
    lines.push({...line,proposed_process_net_krw:null,excluded_from_new_quote:true});
    continue;
   }
   count++;selectedCount++;
   const qty=String(line.new_process_quantity??"");
   const price=String(line.proposed_unit_price_krw??"");
   const rate=scaled(price);
   const ok=isQuantity(qty)&&rate!==null;
   if(!ok)invalidLine=true;
   const rowTotal=ok?rate*BigInt(qty):null;
   if(rowTotal!==null){
    if(line.is_cloud)localCloud+=rowTotal;
    else localProcess+=rowTotal;
   }
   const originalChanged=qty!==line.original_process_quantity||
     price!==line.original_unit_price_krw;
   if(!line.is_cloud&&!line.is_data_release){
    const sourceUnit=line.data_unit;
    if(sourceUnit!=="NA"&&sourceUnit!=="sample"&&
       (input.basis!=="PER_SAMPLE"||input.unit!==sourceUnit||
        !input.production||Number(input.production)!==Number(line.data_size)))
      sourceMismatch=true;
    if(input.samples&&isQuantity(String(input.samples))&&qty!==String(input.samples))
      quantityMismatch=true;
   }
   lines.push({...line,proposed_process_net_krw:rowTotal===null?null:format(rowTotal),
    edited_from_source:originalChanged,excluded_from_new_quote:false,
    valid_new_quantity_price:ok});
  }
  if(selectedCount===0)invalidLine=true;
  processNet+=localProcess;cloudNet+=localCloud;
  results.push({
   source_qid:product.source_qid,
   source_product_signature:product.source_product_signature,
   source_product_name:product.source_product_name,
   source_review_status:product.source_review_status,
   source_hold_reason:product.source_hold_reason,
   source_process_net_krw:product.source_process_net_krw,
   source_account_id:product.source_account_id,source_contact_id:product.source_contact_id,
   compared_to_selected_customer:account&&contact?
     (product.source_account_id===account&&product.source_contact_id===contact?
       "SAME_ACCOUNT_CONTACT":"OTHER_SOURCE_CUSTOMER_RECHECK_REQUIRED"):
     "CUSTOMER_ID_NOT_RECHECKED",
   quantity_depth_reviewed:product.quantity_depth_reviewed===true,
   selected_process_count:selectedCount,
   process_net_krw:format(localProcess),cloud_net_krw:format(localCloud),
   net_krw:format(localProcess+localCloud),lines
  });
 }
 if(!count)return invalid("HOLD_NO_SELECTED_PROCESS");
 const net=processNet+cloudNet;
 const vat5=net; // net_scaled_4 / 10 -> VAT scaled_5
 const gross5=net*11n;
 const fractional=net%10000n!==0n||vat5%100000n!==0n||gross5%100000n!==0n;
 const status=invalidLine?"HOLD_INVALID_PROCESS_QTY_OR_RATE":
   sourceMismatch?"HOLD_PRODUCTION_UNIT_DEPTH_RECHECK":
   quantityMismatch?"HOLD_PROCESS_QTY_DIFFERS_FROM_NEW_SAMPLES":
   unreviewed?"HOLD_NEW_PROCESS_QUANTITY_CONFIRMATION":
   mixedSources?"HOLD_SOURCE_CUSTOMER_DIFFERENT":
   fractional?"HOLD_FRACTIONAL_KRW_TOTAL":
   "LOCAL_QUOTE_DRAFT_REVIEW_REQUIRED";
 return {status,products:results,product_count:results.length,
   process_count:products.reduce((n,p)=>n+p.lines.length,0),
   selected_process_count:count,
   process_net_krw:format(processNet),cloud_net_krw:format(cloudNet),
   net_krw:format(net),vat_krw:format(vat5,5),
   gross_krw:format(gross5,5),
   vat_rate:"10%",fee_mode:"EXCLUDE",
   source_product_reference_only:true,
   source_customer_mismatch:mixedSources,
   original_source_recheck_required:true,
   actual_sf_product_ids_verified:false,
   pack_verified:false,
   cloud_allocation_verified:false,
   price_approved:false,salesforce_save_allowed:false,
   crm_writes:0};
}

export function exportLocalOppoQuoteReview(draft,intake,customerSelection){
 const checked=reviewLocalProcessDraft(draft,intake,customerSelection);
 return {version:"sfdc-local-original-process-product-draft-v1",
  source:"BROWSER_LOCAL_USER_SELECTED_2026_KRW_REFERENCES",
  status:checked.status,
  opportunity_name:intake?.suggested?.opportunityName||null,
  quotation_name:intake?.suggested?.quotationName||null,
  close_date_kst:intake?.suggested?.closeDateKst||null,
  customer_reference:{
   account_id:customerSelection?.ok?customerSelection.account_id:null,
   contact_id:customerSelection?.ok?customerSelection.contact_id:null,
   live_write_identity_verified:false},
  quote_products:checked.products,
  quote_amounts:{process_net_krw:checked.process_net_krw,
    cloud_net_krw:checked.cloud_net_krw,net_krw:checked.net_krw,
    vat_krw:checked.vat_krw,gross_krw:checked.gross_krw},
  quote_fee_included:false,sfdc_quote_saved:false,
  price_approved:false,salesforce_save_allowed:false,crm_writes:0,
  operator_review_required:true};
}
