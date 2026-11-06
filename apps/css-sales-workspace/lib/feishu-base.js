'use strict';
// Server-only adapter for the dedicated Feishu Sales Base. Never expose tokens.
const BASE='IpMkbUD0vaFqtYs93a3csXtdn1b';
const TABLE='tblTZe5tkRUeOHM8';
const HOST='https://open.feishu.cn';
const FIELDS=['Source Key','AMEA','Quote Full Name','Quote Match State','Institution',
  'Customer','Service','Current Stage','Progress %','Prepayment',
  'Prepayment Evidence','SIF State','PO Evidence','Next Action','Evidence'];
const TIMEOUT=9500;
function cleanText(value,depth=0){
  if(depth>4||value===null||value===undefined)return '';
  if(typeof value==='string')return value;
  if(typeof value==='number'||typeof value==='boolean')return String(value);
  if(Array.isArray(value))return value.map(x=>cleanText(x,depth+1)).join('');
  if(typeof value==='object'){
    if('text' in value)return cleanText(value.text,depth+1);
    if('value' in value)return cleanText(value.value,depth+1);
    if('name' in value)return cleanText(value.name,depth+1);
  }
  return '';
}
function normalize(record){
  const fields=record&&record.fields||{};
  const item={};
  for(const name of FIELDS)item[name]=cleanText(fields[name]).trim();
  const p=Number(item['Progress %']);
  item.progress=item['Progress %']!==''&&Number.isFinite(p)&&p>=0&&p<=100?p:null;
  item.id=item['Source Key']||item.AMEA||'';
  return item;
}
function safeCursor(cursor){
  if(cursor===undefined||cursor===null||cursor==='')return '';
  if(typeof cursor!=='string'||cursor.length>512||/[\x00-\x1f\x7f]/.test(cursor))
    throw Object.assign(new Error('BAD_CURSOR'),{status:400});
  return cursor;
}
async function jsonFetch(path,{method='GET',body,token,timeout=TIMEOUT,fetcher=fetch}={}){
  const response=await fetcher(HOST+path,{
    method,
    headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},
    ...(body?{body:JSON.stringify(body)}:{}),
    signal:AbortSignal.timeout(timeout)
  });
  if(!response.ok)throw Object.assign(new Error('FEISHU_UPSTREAM_HTTP_'+response.status),{status:502});
  const data=await response.json();
  if(data.code!==0)throw Object.assign(new Error('FEISHU_UPSTREAM_CODE_'+String(data.code)),{status:502});
  return data;
}
async function readProjects({appId,appSecret,cursor='',fetcher=fetch}){
  if(!appId||!appSecret)throw Object.assign(new Error('FEISHU_CREDENTIALS_MISSING'),{status:503});
  const credentials=await jsonFetch('/open-apis/auth/v3/tenant_access_token/internal',{
    method:'POST',body:{app_id:appId,app_secret:appSecret},fetcher
  });
  const token=credentials.tenant_access_token;
  if(!token)throw Object.assign(new Error('FEISHU_TOKEN_NOT_RETURNED'),{status:502});
  const qs=new URLSearchParams({page_size:'100'});
  const next=safeCursor(cursor);
  if(next)qs.set('page_token',next);
  const result=await jsonFetch('/open-apis/bitable/v1/apps/'+BASE+'/tables/'+TABLE+'/records?'+qs,{
    token,fetcher
  });
  const data=result.data||{};
  if(!Array.isArray(data.items))throw Object.assign(new Error('FEISHU_RECORD_SCHEMA_INVALID'),{status:502});
  if(data.has_more&&!data.page_token)throw Object.assign(new Error('FEISHU_CURSOR_MISSING'),{status:502});
  const items=data.items.map(normalize).filter(x=>x.id);
  return {items,nextCursor:data.has_more?String(data.page_token):null,
    hasMore:!!data.has_more,source:'FEISHU_BASE',table:'Project Progress Board',
    generatedAt:new Date().toISOString()};
}
module.exports={BASE,TABLE,FIELDS,cleanText,normalize,safeCursor,readProjects};
