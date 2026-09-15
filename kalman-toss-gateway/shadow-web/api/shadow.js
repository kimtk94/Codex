module.exports = async function handler(req,res){
  const base=String(process.env.TOSS_GATEWAY_URL||'').replace(/\/+$/,'');
  const secret=String(process.env.HUB_GATEWAY_SECRET||'');
  const hub=String(process.env.KALMAN_HUB_FALLBACK_URL||'https://kalman-investment-hub-v2.vercel.app').replace(/\/+$/,'');
  res.setHeader('Cache-Control','no-store');
  res.setHeader('Content-Type','application/json; charset=utf-8');

  async function directGateway(){
    if(!base||!secret) throw Object.assign(new Error('gateway env missing'),{code:'GATEWAY_ENV_MISSING'});
    const upstream=await fetch(base+'/api/shadow-bakeoff',{
      headers:{'X-Gateway-Secret':secret,'Accept':'application/json'},
      cache:'no-store'
    });
    const text=await upstream.text();
    if(!upstream.ok){
      const err=new Error('gateway upstream HTTP '+upstream.status);
      err.code='GATEWAY_HTTP_'+upstream.status;
      err.status=upstream.status;
      err.body=text;
      throw err;
    }
    return {status:upstream.status,text,source:'gateway'};
  }

  async function mainHubFallback(){
    const upstream=await fetch(hub+'/api/dashboard?market=SHADOW',{
      headers:{'Accept':'application/json'},
      cache:'no-store'
    });
    const text=await upstream.text();
    if(!upstream.ok){
      const err=new Error('hub fallback HTTP '+upstream.status);
      err.code='HUB_HTTP_'+upstream.status;
      err.status=upstream.status;
      err.body=text;
      throw err;
    }
    return {status:upstream.status,text,source:'main-hub'};
  }

  try{
    const out=await directGateway();
    res.setHeader('X-Kalman-Shadow-Source',out.source);
    res.statusCode=out.status;
    res.end(out.text);
    return;
  }catch(e){
    const directCode=String(e?.cause?.code||e?.code||e?.name||'DIRECT_FETCH_ERROR');
    console.error('shadow direct gateway failed',directCode);
    try{
      const out=await mainHubFallback();
      res.setHeader('X-Kalman-Shadow-Source',out.source);
      res.setHeader('X-Kalman-Direct-Failure',directCode);
      res.statusCode=out.status;
      res.end(out.text);
      return;
    }catch(fallbackErr){
      const fallbackCode=String(fallbackErr?.cause?.code||fallbackErr?.code||fallbackErr?.name||'HUB_FETCH_ERROR');
      console.error('shadow main hub fallback failed',fallbackCode);
      res.statusCode=502;
      res.end(JSON.stringify({
        error:'SHADOW_GATEWAY_FETCH_FAILED',
        direct_code:directCode,
        fallback_code:fallbackCode
      }));
    }
  }
};
