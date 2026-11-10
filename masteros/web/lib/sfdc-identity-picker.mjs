/** Identity pairs are tied to one institution. Never resolve homonyms by name alone. */
const id=(value,prefix)=>typeof value==="string"&&
  new RegExp("^"+prefix+"[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$").test(value);
const clean=x=>String(x||"").trim();

export function normalizeIdentityRows(rows){
  if(!Array.isArray(rows))return [];
  const seen=new Set(),out=[];
  for(const raw of rows.slice(0,25)){
    if(!raw||typeof raw!=="object")continue;
    const row={
      source_qid:clean(raw.source_qid),source_quote_id:clean(raw.source_quote_id),
      account_id:clean(raw.account_id),
      account_name:clean(raw.account_name),contact_id:clean(raw.contact_id),
      contact_external_id:clean(raw.contact_external_id),
      contact_name:clean(raw.contact_name),contact_email:clean(raw.contact_email),
      crm_account_verified:raw.crm_account_verified===true,
      crm_contact_verified:raw.crm_contact_verified===true
    };
    if(!row.account_name||!row.contact_name||row.account_name.length>180||
       row.contact_name.length>140||row.source_qid.length>120)continue;
    const unique=[row.account_id,row.account_name,row.contact_id,
      row.contact_name,row.contact_email].join("|");
    if(seen.has(unique))continue;
    seen.add(unique);out.push(row);
  }
  return out;
}
export function dedupeAccounts(rows){
  const results=[],keys=new Set();
  for(const r of rows||[]){
    const name=clean(r.account_name),aid=clean(r.account_id);
    if(!name)continue;
    // Different native IDs are not conflated even if names are identical.
    const key=aid||"name:"+name;
    if(keys.has(key))continue;
    keys.add(key);results.push(r);
  }
  return results;
}
export function selectIdentityPair(row){
  const accountName=clean(row?.account_name),contactName=clean(row?.contact_name);
  if(!accountName||!contactName)return {ok:false,code:"INSTITUTION_AND_CONTACT_REQUIRED"};
  return {ok:true,
    account:{id:clean(row.account_id),name:accountName},
    contact:{id:clean(row.contact_id),externalId:clean(row.contact_external_id),
      name:contactName,email:clean(row.contact_email)},
    sourceQid:clean(row.source_qid),sourceQuoteId:clean(row.source_quote_id),
    sourceVerifiedIds:id(row.account_id,"001")&&id(row.contact_id,"003")
  };
}
export function matchingIdentity(form,identity){
  if(!identity||!form)return {ok:false,code:"ACCOUNT_CONTACT_NOT_SELECTED"};
  if(!id(form.accountId,"001")||!id(form.contactId,"003"))
    return {ok:false,code:"ACCOUNT_CONTACT_IDS_NOT_VERIFIED"};
  if(form.accountId!==identity.account?.id||form.contactId!==identity.contact?.id||
     clean(form.accountName)!==identity.account?.name||
     clean(form.contactName)!==identity.contact?.name)
    return {ok:false,code:"ACCOUNT_CONTACT_SELECTION_CHANGED"};
  return {ok:true,source:identity.source||"REFERENCE_INDEX",
    selection:"EXACT_ACCOUNT_CONTACT_PAIR"};
}
