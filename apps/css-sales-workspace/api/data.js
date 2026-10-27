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
  revenue_fact: ['BI Revenue Fact',1436422169],
  monthly_revenue: ['BI Revenue Actual Forecast',561608758],
  official_2025: ['BI 2025 Official Monthly',1173034481],
  issued_tax: ['BI Revenue Fact',1436422169],
  confirmation_pending: ['CSS Statement Backfill Review',467880897],
  online_list: ['BI Project Month Control',1856711491],
  confirmation_proof: ['Confirmation Evidence Ledger',1764102620]
};
const SEARCH_LIMIT = 5000;
const kstMonth = () => new Date(Date.now()+9*3600e3).toISOString().slice(0,7);
const present = row => row.some(v => String(v ?? '').trim());
async function batchRead(id, ranges, accessToken) {
  const url='https://sheets.googleapis.com/v4/spreadsheets/'+id+'/values:batchGet?valueRenderOption=FORMATTED_VALUE&'+ranges.map(r=>'ranges='+encodeURIComponent(r)).join('&');
  const response=await fetch(url,{headers:{Authorization:'Bearer '+accessToken}});
  if(!response.ok)throw Error('SHEET_READ_FAILED');
  return ((await response.json()).valueRanges||[]).map(v=>v.values||[]);
}
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
  if (key !== 'mail_detail' && !Object.prototype.hasOwnProperty.call(VIEWS,key)) return res.status(400).json({error:'UNKNOWN_VIEW'});
  const config = process.env.GOOGLE_SERVICE_ACCOUNT_JSON;
  if (!config) return res.status(503).json({error:'GOOGLE_CREDENTIALS_NOT_CONFIGURED'});
  try {
    const credentials = (() => {
      try { return JSON.parse(config); } catch (_) { return JSON.parse(Buffer.from(config,'base64').toString('utf8')); }
    })();
    const auth = new GoogleAuth({credentials,scopes:['https://www.googleapis.com/auth/spreadsheets.readonly']});
    const client = await auth.getClient();
    const tokenResponse = await client.getAccessToken();
    const accessToken = typeof tokenResponse === 'string' ? tokenResponse : tokenResponse.token;
    if(key === 'mail_detail'){
      const uid=String(req.query.uid||'').trim();
      if(!/^inbox:[0-9]{1,12}$/.test(uid)) return res.status(400).json({error:'INVALID_MAIL_UID'});
      const read=async range=>{
        const endpoint='https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(SHEET_ID)+'/values/'+encodeURIComponent(range)+'?valueRenderOption=FORMATTED_VALUE';
        const result=await fetch(endpoint,{headers:{Authorization:'Bearer '+accessToken}});
        if(!result.ok) throw Error('GOOGLE_READ_'+result.status);
        return (await result.json()).values||[];
      };
      const queue=await read("'Unanswered Emails'!I2:I1300");
      if(!queue.some(row=>String(row[0]||'').trim()===uid))return res.status(404).json({error:'NOT_IN_UNANSWERED_QUEUE'});
      const rowIndex=queue.findIndex(row=>String(row[0]||'').trim()===uid);
      const summary=(await read("'Unanswered Emails'!A"+(rowIndex+2)+":V"+(rowIndex+2)))[0]||[];
      const fallback={uid,receivedAt:summary[4]||'',from:summary[2]||'',fromName:'',to:'',cc:'',subject:summary[3]||'',body:'',bodyAvailable:false,source:'unanswered_summary',notice:'원본 메일 본문이 아직 동기화되지 않았습니다. CSS Mail Inbox Raw가 비어 있습니다.',readOnly:true};
      // The raw tab may not yet exist; still try the historical source.
      try {
        const ids=await read("'CSS Mail Inbox Raw'!A2:A10000");
        const match=ids.findIndex(row=>String(row[0]||'').trim()===uid);
        if(match>=0){
          const row=(await read("'CSS Mail Inbox Raw'!A"+(match+2)+":X"+(match+2)))[0]||[];
          if(row[9]) return res.status(200).json({uid,receivedAt:row[3]||fallback.receivedAt,from:row[4]||fallback.from,fromName:row[5]||'',to:row[6]||'',cc:row[7]||'',subject:row[8]||fallback.subject,body:row[9],bodyAvailable:true,source:'css_mail_raw',readOnly:true});
        }
      } catch (_) { /* Historical source remains available if raw is not ready. */ }
      try {
        const sourceId='1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY';
        const getSource=async range=>{
          const endpoint='https://sheets.googleapis.com/v4/spreadsheets/'+sourceId+'/values/'+encodeURIComponent(range)+'?valueRenderOption=FORMATTED_VALUE';
          const result=await fetch(endpoint,{headers:{Authorization:'Bearer '+accessToken}});
          if(!result.ok)throw Error('SOURCE_UNAVAILABLE');
          return (await result.json()).values||[];
        };
        // R is IMAP UID; A is an unrelated local sequence. Fetch identifiers only,
        // then retrieve the one matching message, including all split body cells.
        const index=await getSource("'All Emails'!R2:T100000");
        const matches=index.flatMap((r,i)=>String(r[0]||'').trim()===uid.slice(6)&&String(r[2]||'').trim().toLowerCase()==='inbox'?[i+2]:[]);
        if(matches.length===1){
          const found=(await getSource("'All Emails'!A"+matches[0]+":AG"+matches[0]))[0]||[];
          const body=[found[16]||'',...found.slice(21,33)].join('');
          if(body)return res.status(200).json({uid,receivedAt:found[2]||fallback.receivedAt,from:found[4]||fallback.from,fromName:found[3]||'',to:found[5]||'',cc:found[6]||'',subject:found[8]||fallback.subject,body,bodyAvailable:true,source:'qq_all_emails',readOnly:true});
        }
      } catch (_) { /* Return an explicit pending state instead of an empty reader. */ }
      return res.status(200).json({...fallback,notice:'본문 수집 대기 중입니다. QQ 본문 동기화 후 다시 시도해 주세요.'});
    }
    const meta = await fetch('https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(SHEET_ID)+'?fields=sheets(properties(sheetId,title))',{headers:{Authorization:'Bearer '+accessToken}});
    if (!meta.ok) return res.status(502).json({error:'SHEET_METADATA_FAILED',status:meta.status});
    const info=await meta.json();
    const tab=(info.sheets||[]).find(s=>s.properties.sheetId===VIEWS[key][1]);
    if(!tab) return res.status(404).json({error:'TAB_NOT_FOUND',view:key});
    const title=tab.properties.title;
    const page = Math.max(1,Math.min(100000,Number.parseInt(String(req.query.page || '1'),10)||1));
    const pageSize = Math.max(10,Math.min(200,Number.parseInt(String(req.query.pageSize || '50'),10)||50));
    const term=String(req.query.q||'').trim().toLowerCase().slice(0,100);
    const quoted="'"+title.replace(/'/g,"''")+"'";
    if(key==='revenue'){
      const [raw]=await batchRead(SHEET_ID,[quoted+'!A1:AZ105'],accessToken);
      const defs=[['Total Invoice KRW',5,1],['Total Revenue K USD',5,5],['Invoice Count',5,9],['Service Coverage',8,1],['AMEA Quote Link %',8,5],['Approved Active → Invoice',8,9]];
      const metrics=defs.map(([metric,r,c])=>({metric,value:raw[r-1]?.[c-1]??null}));
      const missing=metrics.filter(m=>m.value===null||m.value==='').map(m=>m.metric);
      return res.status(200).json({view:key,title,kind:'metrics',metrics,headers:['Metric','Value'],rows:metrics.map(m=>[m.metric,m.value]),page:1,pageSize:metrics.length,hasMore:false,readOnly:true,quality:missing.length?'확인 필요':'정상',note:missing.length?'값을 찾지 못한 KPI: '+missing.join(', '):null,updatedAt:new Date().toISOString()});
    }
    const first=2+(page-1)*pageSize;
    const [headerData,raw]=await batchRead(SHEET_ID,[quoted+'!A1:AZ1',term?quoted+'!A2:AZ'+(SEARCH_LIMIT+1):quoted+'!A'+first+':AZ'+(first+pageSize)],accessToken);
    const headers=(headerData[0]||[]).map((v,i)=>String(v||'Column '+(i+1)));
    const candidates=term?raw.filter(r=>present(r)&&r.some(v=>String(v).toLowerCase().includes(term))):raw;
    const pageRaw=term?candidates.slice((page-1)*pageSize,page*pageSize):candidates.slice(0,pageSize);
    const hasMore=term?page*pageSize<candidates.length:raw.length>pageSize;
    const queryInfo=term?{total:candidates.length,searchLimit:SEARCH_LIMIT,searchScope:'최대 '+SEARCH_LIMIT+'행 서버 검색'}:{};
    const rows=pageRaw.filter(present).map(r=>headers.map((_,i)=>r[i]??''));
    if(key==='monthly_revenue'){
      // Keep issued invoice amounts separate from provisional completion estimates.
      // This is descriptive metadata from Feishu TAT Monthly, never an extra revenue sum.
      const extraRange="'Feishu TAT Monthly'!A1:M100";
      const extraUrl='https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(SHEET_ID)+'/values/'+encodeURIComponent(extraRange)+'?valueRenderOption=UNFORMATTED_VALUE';
      const ext=await fetch(extraUrl,{headers:{Authorization:'Bearer '+accessToken}}).catch(()=>({ok:false}));
      const extraAvailable=ext.ok;
      const details=extraAvailable?(await ext.json()).values||[]:[];
      const byMonth=new Map(details.slice(1).filter(x=>x[0]).map(x=>[String(x[0]),x]));
      const h=[...headers,'Feishu Completed-status KRW (unreconciled)','Feishu Future Forecast KRW','Revenue Coverage / Reliability'];
      const enriched=rows.map(r=>{
        const m=String(r[0]||'');
        const e=byMonth.get(m);
        const completed=e?.[9]??'';
        const future=e?.[10]??'';
        const review=Number(r[10]||0);
        const currentMonth=kstMonth();
        const coverage=m.startsWith('2025')?'HISTORICAL_INVOICE_COVERAGE_PARTIAL':m===currentMonth?'MONTH_TO_DATE; FORECAST_NOT_REVENUE':m>currentMonth?'FUTURE_ESTIMATE_NOT_ISSUED':'ISSUED_INVOICE; FORECAST_SEPARATE';
        return [...r,completed,future,coverage+(review?'; MAPPING_REVIEW='+review:'')];
      });
      return res.status(200).json({view:key,title,kind:'table',headers:h,rows:enriched,shown:enriched.length,page,pageSize,hasMore,...queryInfo,readOnly:true,quality:extraAvailable?'정상':'확인 필요',note:(extraAvailable?'':'Feishu 보조 데이터 조회 실패 · 해당 값은 미확인입니다. ' )+'합계(Combined KRW)는 발행 인보이스 + 순예상액의 운영 전망이며 확정 매출이 아닙니다. Completed-status도 정산 증빙과 별도입니다. 중복 제거와 매칭 검토가 필요합니다.',updatedAt:new Date().toISOString()});
    }
    const basisNotes={
      issued_tax:'TAX INVOICE 발행 확인건만 표시합니다. 세금계산서 발행은 입금 확인과 다릅니다. Invoice Number 기준으로 중복을 검토하세요.',
      confirmation_pending:'Statement 메일 및 Confirmation 증빙 검토 목록입니다. Statement 발행 자체는 Confirmation 완료 또는 TAX INVOICE 발행을 의미하지 않습니다. 금액 검증 전에는 Revenue에 합산하지 않습니다.',
      confirmation_proof:'Confirmation 증빙 상태 원장입니다. AWAITING_CONFIRMATION_PROOF는 확인 완료가 아닌 미확인 상태입니다.',
      online_list:'Online 프로젝트 진행/예상 목록입니다. FORECAST, EXCLUDED, NO_INVOICE_MATCH 등 원본 상태를 유지하며 TAX INVOICE 매출과 합산하지 않습니다.'
    };
    const note=basisNotes[key]|| (key==='monthly_revenue'?'Issued Tax Invoice는 발행 기준이며 수금액이 아닙니다. Net Project Forecast=0이면 추정매출 미반영 가능성을 확인하세요. 2025 Official USD 정산과 직접 YoY 비교 금지.':key==='official_2025'?'2025 공식 정산 매출: USD 세전, KRW는 1500 고정 보고용 환산액. 2026 TAX INVOICE와 서로 다른 기준입니다.':null);
    return res.status(200).json({view:key,title,kind:'table',headers,rows,shown:rows.length,page,pageSize,hasMore,...queryInfo,readOnly:true,note,quality:rows.length?'정상':'비어 있음',updatedAt:new Date().toISOString()});
  } catch(e) {
    console.error('CSS_WEB_DATA_FAILURE',e?.message);
    return res.status(502).json({error:'DATA_SOURCE_UNAVAILABLE'});
  }
};
