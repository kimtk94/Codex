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
const METRIC_TABLES={
  monthly:'tblXLFQWiEK9REZL',
  weekly:'tblfSR10E2R06TDn'
};
async function readMetrics({appId,appSecret,fetcher=fetch}){
  if(!appId||!appSecret)throw Object.assign(new Error('FEISHU_CREDENTIALS_MISSING'),{status:503});
  const credentials=await jsonFetch('/open-apis/auth/v3/tenant_access_token/internal',{
    method:'POST',body:{app_id:appId,app_secret:appSecret},fetcher
  });
  const token=credentials.tenant_access_token;
  if(!token)throw Object.assign(new Error('FEISHU_TOKEN_NOT_RETURNED'),{status:502});
  async function getTable(id){
    const out=[],seen=new Set();let cursor='';
    for(let page=0;page<10;page++){
      const params=new URLSearchParams({page_size:'100'});
      if(cursor)params.set('page_token',cursor);
      const resp=await jsonFetch('/open-apis/bitable/v1/apps/'+BASE+'/tables/'+id+'/records?'+params,{
        token,fetcher
      });
      const data=resp.data||{};
      if(!Array.isArray(data.items))throw Object.assign(new Error('FEISHU_RECORD_SCHEMA_INVALID'),{status:502});
      for(const r of data.items){
        if(!r||!r.fields)continue;
        const key=r.record_id||JSON.stringify(r.fields);
        if(seen.has(key))throw Object.assign(new Error('FEISHU_DUPLICATE_METRIC_RECORD'),{status:502});
        seen.add(key);
        const flat={};
        for(const name of Object.keys(r.fields))flat[name]=cleanText(r.fields[name]).trim();
        out.push(flat);
      }
      if(!data.has_more)return out;
      if(!data.page_token||data.page_token===cursor)
        throw Object.assign(new Error('FEISHU_CURSOR_MISSING'),{status:502});
      cursor=data.page_token;
    }
    throw Object.assign(new Error('FEISHU_METRIC_PAGINATION_LIMIT'),{status:502});
  }
  const [monthly,weekly]=await Promise.all([
    getTable(METRIC_TABLES.monthly),getTable(METRIC_TABLES.weekly)
  ]);
  return {
    monthly:monthly.map(r=>({
      month:r.Month||'',
      invoiceCount:Number(r['Invoice Count'])||0,
      invoiceGross:Number(r['Tax Invoice KRW Incl VAT'])||0,
      revenueNet:Number(r['Net Revenue KRW Ex VAT'])||0,
      revenueKUSD:Number(r['Net Revenue K USD'])||0,
      coverage:r['Coverage Status']||''
    })).filter(r=>/^20\d\d-\d\d$/.test(r.month)).sort((a,b)=>a.month.localeCompare(b.month)),
    weekly:weekly.map(r=>({
      week:r['Week Start']||'',
      approved:Number(r['Approved Quote Count'])||0,
      quoteNetKRW:Number(r['Verified Quote Value KRW FX'])||0,
      quoteKUSD:Number(r['Verified Quote Value K USD'])||0,
      amountStatus:r['Amount Status']||''
    })).filter(r=>/^20\d\d-\d\d-\d\d$/.test(r.week)).sort((a,b)=>a.week.localeCompare(b.week)),
    source:'FEISHU_BASE',generatedAt:new Date().toISOString()
  };
}
module.exports={BASE,TABLE,FIELDS,METRIC_TABLES,cleanText,normalize,safeCursor,readProjects,readMetrics};
