const YAHOO={
  KR:[
    {key:'KOSPI',label:'KOSPI',ticker:'^KS11',kind:'index'},
    {key:'KOSDAQ',label:'KOSDAQ',ticker:'^KQ11',kind:'index'},
    {key:'USDKRW',label:'USD/KRW',ticker:'KRW=X',kind:'fx'}
  ],
  US:[
    {key:'NASDAQ',label:'NASDAQ',ticker:'^IXIC',kind:'index'},
    {key:'SOXX',label:'SOXX',ticker:'SOXX',kind:'price'},
    {key:'VIX',label:'VIX',ticker:'^VIX',kind:'index'}
  ]
};

const finite=x=>Number.isFinite(Number(x))?Number(x):null;
const isoFromEpoch=x=>{const n=finite(x);if(n==null)return null;try{return new Date(n*1000).toISOString()}catch{return null}};
const ymd=d=>d.toISOString().slice(0,10);
const compactYmd=d=>ymd(d).replaceAll('-','');

async function yahooChart(item){
  const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),7000);
  try{
    const url='https://query1.finance.yahoo.com/v8/finance/chart/'+encodeURIComponent(item.ticker)+'?range=5d&interval=1d&includePrePost=false&events=div%2Csplits';
    const r=await fetch(url,{signal:ctrl.signal,headers:{accept:'application/json,text/plain,*/*','user-agent':'Mozilla/5.0 Kalman-Market-Pulse/2.0'}});
    if(!r.ok)throw new Error('HTTP_'+r.status);
    const body=await r.json(),result=body?.chart?.result?.[0];
    if(!result)throw new Error(body?.chart?.error?.description||'NO_RESULT');
    const meta=result.meta||{},closes=(result?.indicators?.quote?.[0]?.close||[]).map(finite).filter(x=>x!=null);
    let value=finite(meta.regularMarketPrice);if(value==null&&closes.length)value=closes.at(-1);
    let prev=finite(meta.chartPreviousClose);if(prev==null)prev=finite(meta.previousClose);if(prev==null&&closes.length>1)prev=closes.at(-2);
    const changeAbs=value!=null&&prev!=null?value-prev:null,changePct=value!=null&&prev?changeAbs/prev:null;
    return {...item,status:value==null?'DEGRADED':'READY',value,previous_close:prev,change_abs:changeAbs,change_pct:changePct,currency:meta.currency||null,exchange:meta.exchangeName||meta.fullExchangeName||null,as_of:isoFromEpoch(meta.regularMarketTime),source:'YAHOO_PUBLIC_CONTEXT'};
  }finally{clearTimeout(timer)}
}

function csvRows(text){
  const lines=String(text||'').trim().split(/\r?\n/);if(lines.length<2)return[];
  const head=lines[0].split(',').map(x=>x.trim());
  return lines.slice(1).map(line=>{const a=line.split(',');return Object.fromEntries(head.map((h,i)=>[h,(a[i]??'').trim()]))});
}

async function usRates(){
  const start=new Date(Date.now()-21*86400000);
  const url='https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2,DGS10&cosd='+ymd(start);
  const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),8000);
  try{
    const r=await fetch(url,{signal:ctrl.signal,headers:{accept:'text/csv','user-agent':'Mozilla/5.0 Kalman-Market-Pulse/2.0'}});
    if(!r.ok)throw new Error('FRED_HTTP_'+r.status);
    const rows=csvRows(await r.text()).map(x=>({date:x.DATE||x.observation_date,d2:finite(x.DGS2),d10:finite(x.DGS10)})).filter(x=>x.date&&(x.d2!=null||x.d10!=null));
    const complete=rows.filter(x=>x.d2!=null&&x.d10!=null);if(!complete.length)throw new Error('FRED_NO_COMPLETE_ROWS');
    const cur=complete.at(-1),prev=complete.length>1?complete.at(-2):null;
    const item=(key,label,value,previous)=>({key,label,kind:'yield_pct',status:value==null?'DEGRADED':'READY',value,previous_close:previous,change_abs:value!=null&&previous!=null?value-previous:null,change_pct:value!=null&&previous?((value-previous)/previous):null,currency:'PCT',as_of:cur.date,source:'FEDERAL_RESERVE_H15_VIA_FRED'});
    const spread=cur.d10-cur.d2,prevSpread=prev?prev.d10-prev.d2:null;
    return [
      item('US2Y','US 2Y',cur.d2,prev?.d2??null),
      item('US10Y','US 10Y',cur.d10,prev?.d10??null),
      {key:'US2S10S',label:'2s10s',kind:'spread_bps',status:'READY',value:spread*100,previous_close:prevSpread==null?null:prevSpread*100,change_abs:prevSpread==null?null:(spread-prevSpread)*100,change_pct:null,currency:'BP',as_of:cur.date,source:'FEDERAL_RESERVE_H15_VIA_FRED',components:['DGS2','DGS10']}
    ];
  }finally{clearTimeout(timer)}
}

function ecosRows(body){
  const rows=body?.StatisticSearch?.row;
  if(!Array.isArray(rows))return[];
  return rows.map(x=>({date:String(x.TIME||''),value:finite(x.DATA_VALUE)})).filter(x=>x.date&&x.value!=null).sort((a,b)=>a.date.localeCompare(b.date));
}
async function ecosRate(itemCode){
  const end=new Date(),start=new Date(Date.now()-21*86400000);
  const key=process.env.BOK_ECOS_API_KEY||process.env.ECOS_API_KEY||'sample';
  const url='https://ecos.bok.or.kr/api/StatisticSearch/'+encodeURIComponent(key)+'/json/kr/1/10/817Y002/D/'+compactYmd(start)+'/'+compactYmd(end)+'/'+itemCode;
  const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),8000);
  try{
    const r=await fetch(url,{signal:ctrl.signal,headers:{accept:'application/json','user-agent':'Mozilla/5.0 Kalman-Market-Pulse/2.0'}});
    if(!r.ok)throw new Error('ECOS_HTTP_'+r.status);
    const body=await r.json(),rows=ecosRows(body);
    if(!rows.length)throw new Error(body?.RESULT?.MESSAGE||body?.StatisticSearch?.RESULT?.MESSAGE||'ECOS_NO_ROWS');
    return {rows,auth:key==='sample'?'SAMPLE_KEY':'ENV_KEY'};
  }finally{clearTimeout(timer)}
}
async function krRates(){
  const [a,b]=await Promise.all([ecosRate('010200000'),ecosRate('010210000')]);
  const common=new Map(a.rows.map(x=>[x.date,{date:x.date,y3:x.value}]));
  for(const x of b.rows){const v=common.get(x.date)||{date:x.date};v.y10=x.value;common.set(x.date,v)}
  const rows=[...common.values()].filter(x=>x.y3!=null&&x.y10!=null).sort((x,y)=>x.date.localeCompare(y.date));
  if(!rows.length)throw new Error('ECOS_NO_COMMON_ROWS');
  const cur=rows.at(-1),prev=rows.length>1?rows.at(-2):null,source='BOK_ECOS_817Y002';
  const item=(key,label,value,previous)=>({key,label,kind:'yield_pct',status:'READY',value,previous_close:previous??null,change_abs:prev?value-previous:null,change_pct:prev&&previous?((value-previous)/previous):null,currency:'PCT',as_of:cur.date,source});
  const spread=cur.y10-cur.y3,prevSpread=prev?prev.y10-prev.y3:null;
  return [
    item('KR3Y','KR 3Y',cur.y3,prev?.y3),
    item('KR10Y','KR 10Y',cur.y10,prev?.y10),
    {key:'KR3S10S',label:'3s10s',kind:'spread_bps',status:'READY',value:spread*100,previous_close:prevSpread==null?null:prevSpread*100,change_abs:prevSpread==null?null:(spread-prevSpread)*100,change_pct:null,currency:'BP',as_of:cur.date,source,components:['KTB3Y','KTB10Y'],ecos_auth:a.auth}
  ];
}

const failed=(specs,source,error)=>specs.map(x=>({...x,status:'FAIL',value:null,previous_close:null,change_abs:null,change_pct:null,as_of:null,source,error:String(error?.message||error||'FETCH_FAILED')}));
export default async function handler(req,res){
  if(req.method!=='GET'){res.setHeader('Allow','GET');return res.status(405).json({status:'METHOD_NOT_ALLOWED'})}
  const market=String(req.query?.market||'US').toUpperCase();
  if(!YAHOO[market])return res.status(400).json({status:'BAD_MARKET',allowed:Object.keys(YAHOO)});
  const marketSpecs=YAHOO[market],baseSettled=await Promise.allSettled(marketSpecs.map(yahooChart));
  const base=baseSettled.map((x,i)=>x.status==='fulfilled'?x.value:{...marketSpecs[i],status:'FAIL',value:null,previous_close:null,change_abs:null,change_pct:null,as_of:null,source:'YAHOO_PUBLIC_CONTEXT',error:String(x.reason?.message||x.reason||'FETCH_FAILED')});
  let rates=[];
  try{rates=market==='US'?await usRates():await krRates()}
  catch(error){
    const specs=market==='US'
      ?[{key:'US2Y',label:'US 2Y',kind:'yield_pct'},{key:'US10Y',label:'US 10Y',kind:'yield_pct'},{key:'US2S10S',label:'2s10s',kind:'spread_bps'}]
      :[{key:'KR3Y',label:'KR 3Y',kind:'yield_pct'},{key:'KR10Y',label:'KR 10Y',kind:'yield_pct'},{key:'KR3S10S',label:'3s10s',kind:'spread_bps'}];
    rates=failed(specs,market==='US'?'FEDERAL_RESERVE_H15_VIA_FRED':'BOK_ECOS_817Y002',error);
  }
  const items=[...base,...rates],ready=items.filter(x=>x.status==='READY').length;
  res.setHeader('Cache-Control','public, s-maxage=60, stale-while-revalidate=300');
  res.setHeader('Content-Type','application/json; charset=utf-8');
  return res.status(200).json({schema_version:'kalman-market-pulse-v2',status:ready===items.length?'READY':ready?'DEGRADED':'FAIL',market,generated_at:new Date().toISOString(),read_only:true,trade_signal_input:false,items});
}
