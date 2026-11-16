import {validateKoreanNameQuery} from "./sfdc-contact-first-command.mjs";
const ID=/^001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;

/** Request is local-only. Every candidate still requires live Salesforce recheck. */
export function validKrwNativeContactQuery(data){
 if(!data||typeof data!=="object"||Array.isArray(data)||
    Object.keys(data).some(k=>!["query","limit","accountId"].includes(k)))
  return {ok:false,code:"QUERY_FIELDS_INVALID"};
 const checked=validateKoreanNameQuery(data.query);
 if(!checked.ok)return {ok:false,code:"KOREAN_NAME_REQUIRED"};
 if(!Number.isInteger(data.limit)||data.limit<1||data.limit>10)
  return {ok:false,code:"CONTACT_LIMIT_INVALID"};
 if(data.accountId!==undefined&&(!ID.test(data.accountId)))
  return {ok:false,code:"ACCOUNT_ID_INVALID"};
 return {ok:true,request:{
  query:checked.query,limit:data.limit,
  ...(data.accountId?{accountId:data.accountId}:{})
 }};
}

export function validateLiveKrwContactSearch(result,searchName){
 const checked=validateKoreanNameQuery(searchName);
 if(!checked.ok)return {ok:false,code:"KOREAN_NAME_REQUIRED"};
 if(!result||result.status!=="PASS"||result.local_only!==true||
    result.salesforce_write!==false||
    result.coverage!=="VERIFIED_2026_KRW_QUOTE_CONTACTS_ONLY"||
    !Array.isArray(result.candidates)||result.candidates.length>10||
    result.unresolved_matches!==0)
  return {ok:false,code:"LIVE_SOURCE_INCOMPLETE_OR_UNAVAILABLE"};
 const nativeAccount=/^001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;
 const nativeContact=/^003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;
 const nativeOppo=/^006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;
 const normalized=(x)=>String(x||"").normalize("NFKC").replace(/\s+/g,"").trim();
 const ids=new Set();
 const candidates=[];
 for(const row of result.candidates){
  if(!row||normalized(row.korean_name)!==normalized(checked.query)||
     !nativeAccount.test(row.account_id||"")||
     !nativeContact.test(row.contact_id||"")||
     !Array.isArray(row.linked_opportunity_ids)||
     row.linked_opportunity_ids.length!==1||
     !nativeOppo.test(row.linked_opportunity_ids[0])||
     typeof row.institution_name!=="string"||!row.institution_name.trim()||
     typeof row.email!=="string"||!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(row.email)||
     ids.has(row.contact_id))
    return {ok:false,code:"LIVE_CONTACT_ROW_UNVERIFIED"};
  ids.add(row.contact_id);
  candidates.push({
   korean_name:checked.query,
   institution_name:row.institution_name,
   account_id:row.account_id,
   contact_id:row.contact_id,
   email:row.email,
   linked_opportunity_ids:[...row.linked_opportunity_ids],
  });
 }
 return {ok:true,status:"LIVE_QUOTE_LINKS_RECHECKED",candidates,
  requires_institution_choice:candidates.length>1,
  exact_match_count:candidates.length,
  salesforce_save_allowed:false,
  coverage:result.coverage};
}
