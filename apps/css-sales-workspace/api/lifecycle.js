const {GoogleAuth}=require('google-auth-library');
const SHEET='1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI';
const ranges=["'BI Revenue Lifecycle Monthly'!A1:L20","'BI Project Lifecycle Overview'!A1:X400","'Automation Health'!A1:D30"];
module.exports=async function handler(req,res){
  res.setHeader('Cache-Control','private, no-store');
  res.setHeader('X-Content-Type-Options','nosniff');
  if(req.method!=='GET')return res.status(405).json({error:'METHOD_NOT_ALLOWED'});
  const token=process.env.CSS_WEB_ACCESS_TOKEN;
  const supplied=(req.headers.authorization||'').replace(/^Bearer /i,'');
  if(!token||!supplied||supplied.length!==token.length){
    return res.status(401).json({error:'AUTH_REQUIRED'});
  }
  const crypto=require('crypto');
  if(!crypto.timingSafeEqual(Buffer.from(supplied),Buffer.from(token)))
    return res.status(401).json({error:'AUTH_REQUIRED'});
  try{
    const raw=process.env.GOOGLE_SERVICE_ACCOUNT_JSON;
    if(!raw)return res.status(503).json({error:'SHEETS_CREDENTIALS_MISSING'});
    const auth=new GoogleAuth({credentials:JSON.parse(raw),scopes:['https://www.googleapis.com/auth/spreadsheets.readonly']});
    const client=await auth.getClient();
    const access=await client.getAccessToken();
    const url='https://sheets.googleapis.com/v4/spreadsheets/'+SHEET+'/values:batchGet?'+ranges.map(x=>'ranges='+encodeURIComponent(x)).join('&');
    const reply=await fetch(url,{headers:{Authorization:'Bearer '+access.token},signal:AbortSignal.timeout(15000)});
    if(!reply.ok)throw new Error('SHEETS_HTTP_'+reply.status);
    const data=await reply.json();
    const [monthly,projects,health]=(data.valueRanges||[]).map(x=>x.values||[]);
    const expected=['Month','Project / Sub-project','Component'];
    if(!monthly[0]||!projects[0]||!health[0]||[monthly[0][0],projects[0][0],health[0][0]].some((v,i)=>v!==expected[i]))
      return res.status(503).json({error:'SOURCE_SCHEMA_MISMATCH'});
    const money=x=>Number(String(x||'0').replace(/[^0-9.-]/g,''))||0;
    const lifecycles=projects.slice(1).filter(x=>x[0]).map(x=>({
      project:x[0],amea:x[1]||'',institution:x[2]||'',customer:x[3]||'',service:x[4]||'',
      stage:x[6]||'',progress:money(x[7]),status:x[5]||'',expectedMonth:x[12]||'',
      invoiceCount:money(x[14]),actual:money(x[15]),billing:x[16]||'',
      forecast:money(x[17]),next:x[18]||'',pendingStatement:x[20]||'',
      pendingVerified:money(x[22]),pendingEvidence:x[23]||''}));
    const months=monthly.slice(1).filter(x=>/^20\d\d-\d\d$/.test(x[0]||'')).map(x=>({
      month:x[0],actual:money(x[1]),pending:money(x[2]),forecast:money(x[3]),
      combined:money(x[4]),invoices:money(x[5]),openStatements:money(x[6]),
      unknownStatements:money(x[7]),forecastProjects:money(x[8]),quality:x[10]||'',
      refreshed:x[11]||''}));
    const status=health.slice(1).filter(x=>['CSS Mail','Project Lifecycle','Revenue Lifecycle','Feishu'].includes(x[0]))
      .map(x=>({name:x[0],updated:x[1]||'',state:x[2]||'',details:x[3]||''}));
    return res.status(200).json({months,projects:lifecycles,status,refreshed:months[0]?.refreshed||''});
  }catch(e){return res.status(503).json({error:'DATA_FETCH_FAILED'});}
};