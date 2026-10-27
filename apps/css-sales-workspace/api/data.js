const { GoogleAuth } = require('google-auth-library');
const SHEET_ID = '1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI';
const VIEWS = {
  actions: ['Action Dashboard',1946039816],
  email_priority: ['Email Action Priority',2036102603],
  nba: ['NBA Today Top10',1948251025],
  unanswered: ['Unanswered Emails',2036102601],
  email_decisions: ['Email Review Decisions',2036102602],
  lead_email: ['Lead Email Followup',2036102431],
  lead_priority: ['Lead Action Priority',2036102502],
  followup: ['Follow-up Priority',2136651387],
  quotes: ['Quote Portfolio Summary',865561618],
  revenue: ['BI Revenue Executive 2026',129540641],
  yoy: ['BI 2025 vs 2026 Overlay',1936002610],
  projects: ['BI Project Month Control',1856711491],
  billing: ['Billing Control Dashboard',246817115],
  health: ['Automation Health',898581637],
  owners: ['Owner Sheet Registry',2036102692],
  mail_source: ['CSS Mail Source Control',2036102691],
  opportunities: ['SFDC Import Opportunities',2036102426],
  quote_records: ['SFDC Import Quotation',2036102427],
  sales_master: ['Sales Master',667234836],
  timeline: ['CSS Project Timeline',1466322538],
  revenue_fact: ['BI Revenue Fact',1436422169]
};
module.exports = async (req, res) => {
  res.setHeader('Cache-Control','private, no-store, max-age=0');
  res.setHeader('X-Content-Type-Options','nosniff');
  if (req.method !== 'GET') return res.status(405).json({error:'METHOD_NOT_ALLOWED'});
  // Preview is gated by Vercel Deployment Protection (SSO).
  // Never permit anonymous requests on production, local development or unprotected deploys.
  const protectedPreview = process.env.VERCEL === '1' && process.env.VERCEL_ENV === 'preview';
  if (!protectedPreview) {
    const expected = process.env.CSS_WEB_ACCESS_TOKEN;
    if (!expected) return res.status(503).json({error:'WEB_ACCESS_NOT_CONFIGURED'});
    const supplied = String(req.headers.authorization || '').replace(/^Bearer\s+/i,'');
    const crypto = require('crypto');
    const a=Buffer.from(supplied), b=Buffer.from(expected);
    if (!supplied || a.length!==b.length || !crypto.timingSafeEqual(a,b)) return res.status(401).json({error:'UNAUTHORIZED'});
  }
  const key = String(req.query.view || 'actions');
  if (!Object.prototype.hasOwnProperty.call(VIEWS,key)) return res.status(400).json({error:'UNKNOWN_VIEW'});
  const config = process.env.GOOGLE_SERVICE_ACCOUNT_JSON || process.env.NBA_GOOGLE_SERVICE_ACCOUNT_JSON || process.env.CKD_GOOGLE_SERVICE_ACCOUNT_JSON;
  if (!config) return res.status(503).json({error:'GOOGLE_CREDENTIALS_NOT_CONFIGURED'});
  try {
    const credentials = (() => {
      try { return JSON.parse(config); } catch (_) { return JSON.parse(Buffer.from(config,'base64').toString('utf8')); }
    })();
    const auth = new GoogleAuth({credentials,scopes:['https://www.googleapis.com/auth/spreadsheets.readonly']});
    const client = await auth.getClient();
    const tokenResponse = await client.getAccessToken();
    const accessToken = typeof tokenResponse === 'string' ? tokenResponse : tokenResponse.token;
    const meta = await fetch('https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(SHEET_ID)+'?fields=sheets(properties(sheetId,title))',{headers:{Authorization:'Bearer '+accessToken}});
    if (!meta.ok) return res.status(502).json({error:'SHEET_METADATA_FAILED',status:meta.status});
    const info=await meta.json();
    const tab=(info.sheets||[]).find(s=>s.properties.sheetId===VIEWS[key][1]);
    if(!tab) return res.status(404).json({error:'TAB_NOT_FOUND',view:key});
    const title=tab.properties.title;
    const page = Math.max(1,Math.min(100000,Number.parseInt(String(req.query.page || '1'),10)||1));
    const pageSize = Math.max(10,Math.min(200,Number.parseInt(String(req.query.pageSize || '50'),10)||50));
    const report = key === 'revenue';
    const firstRow = report ? 1 : (page === 1 ? 1 : 2 + (page - 1) * pageSize);
    const lastRow = report ? 105 : (page === 1 ? firstRow + pageSize : firstRow + pageSize - 1);
    const range="'"+title.replace(/'/g,"''")+"'!A"+firstRow+":AZ"+lastRow;
    const url='https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(SHEET_ID)+'/values/'+encodeURIComponent(range)+'?valueRenderOption=FORMATTED_VALUE';
    const response=await fetch(url,{headers:{Authorization:'Bearer '+accessToken}});
    if(!response.ok) return res.status(502).json({error:'SHEET_READ_FAILED',status:response.status});
    const raw=(await response.json()).values||[];
    if(report){
      const metricRows=[{label:'Total Invoice KRW',row:5,col:1},{label:'Total Revenue K USD',row:5,col:5},{label:'Invoice Count',row:5,col:9},{label:'Service Coverage',row:8,col:1},{label:'AMEA Quote Link %',row:8,col:5},{label:'Approved Active → Invoice',row:8,col:9}];
      const metrics=metricRows.map(m=>({metric:m.label,value:raw[m.row-1]?.[m.col-1]??null}));
      return res.status(200).json({view:key,title,kind:'metrics',metrics,headers:['Metric','Value'],rows:metrics.map(m=>[m.metric,m.value]),page:1,pageSize:metrics.length,hasMore:false,readOnly:true,updatedAt:new Date().toISOString()});
    }
    const headersRange="'"+title.replace(/'/g,"''")+"'!A1:AZ1";
    const headerUrl='https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(SHEET_ID)+'/values/'+encodeURIComponent(headersRange)+'?valueRenderOption=FORMATTED_VALUE';
    const headerResponse=await fetch(headerUrl,{headers:{Authorization:'Bearer '+accessToken}});
    if(!headerResponse.ok)return res.status(502).json({error:'SHEET_HEADER_FAILED',status:headerResponse.status});
    const headers=((await headerResponse.json()).values?.[0]||[]).map((v,i)=>String(v||'Column '+(i+1)));
    const pageRaw=page===1?raw.slice(1):raw;
    const rows=pageRaw.filter(row=>row.some(x=>String(x).trim())).map(row=>headers.map((_,i)=>row[i]??''));
    return res.status(200).json({view:key,title,kind:'table',headers,rows,shown:rows.length,page,pageSize,hasMore:pageRaw.length>=pageSize,readOnly:true,updatedAt:new Date().toISOString()});
  } catch(e) {
    console.error('CSS_WEB_DATA_FAILURE',e?.message);
    return res.status(502).json({error:'DATA_SOURCE_UNAVAILABLE'});
  }
};
