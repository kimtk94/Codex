module.exports = async function handler(req,res){
  const base=String(process.env.TOSS_GATEWAY_URL||'').replace(/\/+$/,'');
  const secret=String(process.env.HUB_GATEWAY_SECRET||'');
  res.setHeader('Cache-Control','no-store');
  res.setHeader('Content-Type','application/json; charset=utf-8');
  if(!base||!secret){
    res.statusCode=503;
    res.end(JSON.stringify({error:'SHADOW_GATEWAY_NOT_CONFIGURED'}));
    return;
  }
  try{
    const upstream=await fetch(base+'/api/shadow-bakeoff',{
      headers:{'X-Gateway-Secret':secret,'Accept':'application/json'},
      cache:'no-store'
    });
    const text=await upstream.text();
    res.statusCode=upstream.status;
    res.end(text);
  }catch(e){
    res.statusCode=502;
    res.end(JSON.stringify({error:'SHADOW_GATEWAY_FETCH_FAILED'}));
  }
};
