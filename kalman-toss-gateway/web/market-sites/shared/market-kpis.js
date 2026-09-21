const SETS={
  KR:[
    {key:'KOSPI',label:'KOSPI',ticker:'^KS11',kind:'index'},
    {key:'KOSDAQ',label:'KOSDAQ',ticker:'^KQ11',kind:'index'},
    {key:'USDKRW',label:'USD/KRW',ticker:'KRW=X',kind:'fx'},
    {key:'US10Y',label:'US 10Y',ticker:'^TNX',kind:'yield_pct'}
  ],
  US:[
    {key:'NASDAQ',label:'NASDAQ',ticker:'^IXIC',kind:'index'},
    {key:'SOXX',label:'SOXX',ticker:'SOXX',kind:'price'},
    {key:'VIX',label:'VIX',ticker:'^VIX',kind:'index'},
    {key:'US10Y',label:'US 10Y',ticker:'^TNX',kind:'yield_pct'}
  ]
};

const finite=x=>Number.isFinite(Number(x))?Number(x):null;
const isoFromEpoch=x=>{
  const n=finite(x);
  if(n==null)return null;
  try{return new Date(n*1000).toISOString()}catch{return null}
};

async function yahooChart(item){
  const ctrl=new AbortController();
  const timer=setTimeout(()=>ctrl.abort(),7000);
  try{
    const url='https://query1.finance.yahoo.com/v8/finance/chart/'+encodeURIComponent(item.ticker)+'?range=5d&interval=1d&includePrePost=false&events=div%2Csplits';
    const r=await fetch(url,{
      signal:ctrl.signal,
      headers:{
        'accept':'application/json,text/plain,*/*',
        'user-agent':'Mozilla/5.0 Kalman-Market-Pulse/1.0'
      }
    });
    if(!r.ok)throw new Error('HTTP_'+r.status);
    const body=await r.json();
    const result=body?.chart?.result?.[0];
    if(!result)throw new Error(body?.chart?.error?.description||'NO_RESULT');
    const meta=result.meta||{};
    const closes=(result?.indicators?.quote?.[0]?.close||[]).map(finite).filter(x=>x!=null);
    let value=finite(meta.regularMarketPrice);
    if(value==null&&closes.length)value=closes[closes.length-1];
    let prev=finite(meta.chartPreviousClose);
    if(prev==null)prev=finite(meta.previousClose);
    if(prev==null&&closes.length>1)prev=closes[closes.length-2];
    const changeAbs=value!=null&&prev!=null?value-prev:null;
    const changePct=value!=null&&prev?changeAbs/prev:null;
    return {
      ...item,
      status:value==null?'DEGRADED':'READY',
      value,
      previous_close:prev,
      change_abs:changeAbs,
      change_pct:changePct,
      currency:meta.currency||null,
      exchange:meta.exchangeName||meta.fullExchangeName||null,
      market_state:meta.marketState||null,
      as_of:isoFromEpoch(meta.regularMarketTime),
      source:'YAHOO_PUBLIC_CONTEXT'
    };
  }finally{
    clearTimeout(timer);
  }
}

export default async function handler(req,res){
  if(req.method!=='GET'){
    res.setHeader('Allow','GET');
    return res.status(405).json({status:'METHOD_NOT_ALLOWED'});
  }
  const market=String(req.query?.market||'US').toUpperCase();
  const specs=SETS[market];
  if(!specs)return res.status(400).json({status:'BAD_MARKET',allowed:Object.keys(SETS)});
  const settled=await Promise.allSettled(specs.map(yahooChart));
  const items=settled.map((x,i)=>x.status==='fulfilled'?x.value:{
    ...specs[i],
    status:'FAIL',
    value:null,
    previous_close:null,
    change_abs:null,
    change_pct:null,
    as_of:null,
    source:'YAHOO_PUBLIC_CONTEXT',
    error:String(x.reason?.message||x.reason||'FETCH_FAILED')
  });
  const ready=items.filter(x=>x.status==='READY').length;
  res.setHeader('Cache-Control','public, s-maxage=60, stale-while-revalidate=300');
  res.setHeader('Content-Type','application/json; charset=utf-8');
  return res.status(200).json({
    schema_version:'kalman-market-pulse-v1',
    status:ready===items.length?'READY':ready?'DEGRADED':'FAIL',
    market,
    generated_at:new Date().toISOString(),
    read_only:true,
    trade_signal_input:false,
    source:'YAHOO_PUBLIC_CONTEXT',
    items
  });
}
