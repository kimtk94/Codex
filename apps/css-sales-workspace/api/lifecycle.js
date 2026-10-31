const {GoogleAuth}=require('google-auth-library');
const {projectPersonalLeads}=require('../lib/personal-leads');
const {projectAutomationConsole}=require('../lib/automation-console');
const {projectOperationalAcceptance}=require('../lib/operational-acceptance');
const {checkOwner,ownerSessionCookie}=require('../lib/lifecycle-owner-auth');
const SHEET='1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI';
const QQ_SHEET='1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY';
const ranges=["'BI Revenue Lifecycle Monthly'!A1:Q20","'BI Project Lifecycle Overview'!A1:X400","'Automation Health'!A1:D60","'Unanswered Emails'!A1:V700","'Lead My Sent Audit'!A1:T650","'Email Review Decisions'!A1:J700","'Automation Master Progress'!A5:K55","'Parallel Track Status'!A1:G5","'Automation Workflow Runs'!A1:J35","'CSS Mail Backfill Status'!A1:O2"];
module.exports=async function handler(req,res){
  res.setHeader('Cache-Control','private, no-store');
  res.setHeader('X-Content-Type-Options','nosniff');
  if(req.method!=='GET')return res.status(405).json({error:'METHOD_NOT_ALLOWED'});
  const token=process.env.CSS_WEB_ACCESS_TOKEN;
  if(!token)return res.status(503).json({error:'AUTH_NOT_CONFIGURED'});
  const owner=checkOwner(req,token,process.env.VERCEL_APP_CLIENT_SECRET);
  if(!owner.valid)return res.status(401).json({error:'AUTH_REQUIRED'});
  if(owner.bearerValid)res.setHeader('Set-Cookie',ownerSessionCookie(token));

  try{
    const raw=process.env.GOOGLE_SERVICE_ACCOUNT_JSON;
    if(!raw)return res.status(503).json({error:'SHEETS_CREDENTIALS_MISSING'});
    const auth=new GoogleAuth({credentials:JSON.parse(raw),scopes:['https://www.googleapis.com/auth/spreadsheets.readonly']});
    const client=await auth.getClient();
    const access=await client.getAccessToken();
    // Start independently so an optional operations status fetch cannot stall
    // or break business data. This source is exclusively read-only.
    const acceptanceRange="'CSS Operational Acceptance'!A1:H20";
    const acceptanceUrl='https://sheets.googleapis.com/v4/spreadsheets/'+SHEET+
      '/values/'+encodeURIComponent(acceptanceRange);
    // A temporary 429 or timeout must not become a permanent false source gap.
    // Return [] after bounded retries; the acceptance projector still fails closed.
    const acceptancePromise=(async()=>{
      for(let attempt=0;attempt<2;attempt++){
        try{
          const response=await fetch(acceptanceUrl,{
            headers:{Authorization:'Bearer '+access.token},
            signal:AbortSignal.timeout(6500)
          });
          if(response.ok)return (await response.json()).values||[];
          if(![429,500,502,503,504].includes(response.status))return [];
        }catch(_err){/* retry bounded transient read; never assume approval */}
      }
      return [];
    })();
    const url='https://sheets.googleapis.com/v4/spreadsheets/'+SHEET+'/values:batchGet?'+ranges.map(x=>'ranges='+encodeURIComponent(x)).join('&');
    const reply=await fetch(url,{headers:{Authorization:'Bearer '+access.token},signal:AbortSignal.timeout(15000)});
    if(!reply.ok)throw new Error('SHEETS_HTTP_'+reply.status);
    const data=await reply.json();
    const [monthly,projects,health,unanswered,lead,decisions,masterProgress,parallelTracks,workflowRuns,mailBackfillSource]=(data.valueRanges||[]).map(x=>x.values||[]);
    const expected=['Month','Project / Sub-project','Component'];
    if(!monthly[0]||!projects[0]||!health[0]||[monthly[0][0],projects[0][0],health[0][0]].some((v,i)=>v!==expected[i]))
      return res.status(503).json({error:'SOURCE_SCHEMA_MISMATCH'});
    const money=x=>Number(String(x||'0').replace(/[^0-9.-]/g,''))||0;
    const lifecycles=projects.slice(1).filter(x=>x[0]).map(x=>({
      project:x[0],amea:x[1]||'',institution:x[2]||'',customer:x[3]||'',service:x[4]||'',
      stage:x[6]||'',progress:money(x[7]),status:x[5]||'',expectedMonth:x[12]||'',
      invoiceCount:money(x[14]),actual:money(x[15]),billing:x[16]||'',
      forecast:money(x[17]),next:x[18]||'',pendingStatement:x[20]||'',noticeAt:x[21]||'',
      pendingVerified:money(x[22]),pendingEvidence:x[23]||''}));
    const months=monthly.slice(1).filter(x=>/^20\d\d-\d\d$/.test(x[0]||'')).map(x=>({
      month:x[0],actual:money(x[1]),pending:money(x[2]),forecast:money(x[3]),
      combined:money(x[4]),invoices:money(x[5]),openStatements:money(x[6]),
      unknownStatements:money(x[7]),forecastProjects:money(x[8]),quality:x[10]||'',
      verifiedBilling:money(x[12])||money(x[1])+money(x[2]),
      invoiceKUSD:money(x[13]),pendingKUSD:money(x[14]),
      verifiedBillingKUSD:money(x[15]),forecastKUSD:money(x[16]),
      refreshed:x[11]||''}));

    // VAT-excluded issued revenue is separately source-audited by GitHub
    // Actions. Missing/stale output NEVER falls back to gross as net revenue.
    let revenueNetStatus='NOT_VERIFIED';
    try {
      const netRange="'BI Revenue Net VAT Monthly'!A1:I24";
      const netUrl='https://sheets.googleapis.com/v4/spreadsheets/'+SHEET+
        '/values/'+encodeURIComponent(netRange);
      const netReply=await fetch(netUrl,{headers:{Authorization:'Bearer '+access.token},
        signal:AbortSignal.timeout(10000)});
      if(netReply.ok){
        const vat=(await netReply.json()).values||[];
        const expectedVat=['Month','Issued Invoice Gross KRW (VAT incl)',
          'Issued Net Revenue KRW (VAT excl)'];
        const headerOK=vat[0]?.slice(0,3).every((v,i)=>v===expectedVat[i]);
        if(headerOK){
          let matched=0;
          for(const row of vat.slice(1)){
            const item=months.find(m=>m.month===row[0]);
            if(!item)continue;
            const gross=money(row[1]),net=money(row[2]),count=money(row[4]);
            const updated=String(row[7]||'');
            const iso=updated.replace(' ','T').replace(/ KST$/,'+09:00');
            const age=Date.now()-Date.parse(iso);
            const current=Number.isFinite(age)&&age>=0&&age<=72*3600*1000;
            const valid=row[8]==='INVOICE_FILENAME_VERIFIED_NET;PENDING_VAT_UNVERIFIED' &&
              current&&gross===item.actual&&count===item.invoices&&net>=0&&net<=gross &&
              Math.abs(Number(row[3])-(net/1500000))<0.002;
            if(valid){
              item.netRevenue=net;item.netRevenueKUSD=Number(row[3]);
              matched++;
            }
          }
          if(matched===months.length)revenueNetStatus='VERIFIED';
        }
      }
    } catch (_err) { revenueNetStatus='NOT_VERIFIED'; }
    if(revenueNetStatus!=='VERIFIED'){
      for(const month of months){month.netRevenue=null;month.netRevenueKUSD=null;}
    }

    // Owner-authenticated, read-only source details. QQ is optional: never
    // pretend a project-level amount is an individual J amount if unavailable.
    let statementSource='QQ_VERIFIED', qqStatements=[], qqInvoices=[];
    try{
      const qqRanges=["'CSS Statement Amount Extract'!A1:K2000",
                      "'CSS Tax Invoice Extract'!A1:L1000"];
      const qqUrl='https://sheets.googleapis.com/v4/spreadsheets/'+QQ_SHEET+'/values:batchGet?'
        +qqRanges.map(x=>'ranges='+encodeURIComponent(x)).join('&');
      const qqReply=await fetch(qqUrl,{headers:{Authorization:'Bearer '+access.token},
                                     signal:AbortSignal.timeout(12000)});
      if(!qqReply.ok)throw new Error('QQ_SOURCE_HTTP_'+qqReply.status);
      const qq=await qqReply.json();
      [qqStatements,qqInvoices]=(qq.valueRanges||[]).map(x=>x.values||[]);
      if(qqStatements[0]?.[0]!=='statement_key'||qqInvoices[0]?.[0]!=='invoice_number')
        throw new Error('QQ_SOURCE_SCHEMA_MISMATCH');
    }catch(e){statementSource='LIFECYCLE_FALLBACK';}
    const statementKey=/^(J\d{3})-(X\d+SC\d+-Z\d+)$/i;
    const subjectKey=/(J\d{3}-X\d+SC\d+-Z\d+)/i;
    const projectByX=new Map(lifecycles.map(p=>[p.project.toUpperCase(),p]));
    const detailed=new Map();
    const itemFor=key=>{
      if(!detailed.has(key)){
        const x=key.split('-').slice(1).join('-');
        const p=projectByX.get(x)||{};
        detailed.set(key,{statementId:key,project:x,amea:p.amea||'',
          institution:p.institution||'',customer:p.customer||'',service:p.service||'',
          noticeAt:'',statementAmount:null,verified:false,invoiceAmount:0,
          invoiceIds:[],issuedAt:'',state:'REVIEW',evidence:''});
      }
      return detailed.get(key);
    };
    if(statementSource==='QQ_VERIFIED'){
      for(const r of qqStatements.slice(1)){
        const key=String(r[0]||'').toUpperCase();
        if(!statementKey.test(key)||r[8]!=='AMOUNT_VERIFIED'||r[4]!=='KRW')continue;
        const amount=Number(r[3]);
        if(!Number.isSafeInteger(amount)||amount<=0)continue;
        const item=itemFor(key);
        if(item.verified&&(item.statementAmount!==amount||item.noticeAt!==r[5]))
          throw new Error('CONFLICTING_VERIFIED_STATEMENT_'+key);
        item.statementAmount=amount;item.verified=true;
        item.noticeAt=r[5]||'';item.evidence='ORIGINAL_UID_'+(r[6]||'');
      }
      const invoiceById=new Map();
      const allowed=new Set(['FILENAME_PARSED','VERIFIED_LEGACY_FILENAME','EXISTS_IN_LEGACY']);
      for(const r of qqInvoices.slice(1)){
        const subject=String(r[6]||'').trim(),number=String(r[0]||'');
        if(!allowed.has(r[10])||!/^209126\d{6}$/.test(number)
           ||/^(?:re|fw|fwd|회신|답장|전달)\s*[:：]/i.test(subject)
           ||!/^\s*(?:❗️\s*)?Notice:\s*Invoice Issued\s*&\s*Statement Confirmed\b/i.test(subject))
          continue;
        const match=subject.match(subjectKey);
        if(!match)continue;
        const filename=String(r[5]||'').replace(/\s+/g,' ');
        const filenameNumber=filename.match(/TAX\s+INVOICE[-_ ]+(\d{8,15})-/i);
        const filenameAmount=filename.match(/-KRW\s*(\d+)(?:\.00)?\.pdf/i);
        const amount=Number(r[1]);
        if(!filenameNumber||filenameNumber[1]!==number||!filenameAmount
           ||Number(filenameAmount[1])!==amount||!Number.isSafeInteger(amount)||amount<=0)
          throw new Error('INVOICE_FILENAME_AMOUNT_CONFLICT_'+number);
        const key=match[1].toUpperCase(), prior=invoiceById.get(number);
        if(prior){if(prior.key!==key||prior.amount!==amount)throw new Error('DUPLICATE_INVOICE_CONFLICT_'+number);continue;}
        invoiceById.set(number,{key,amount});
        const item=itemFor(key);
        item.invoiceIds.push(number);item.invoiceAmount+=amount;
        const date=String(r[7]||'');
        if(date>item.issuedAt)item.issuedAt=date;
        if(!item.amea)item.amea=r[2]||'';
      }
    }else{
      for(const p of lifecycles){
        const js=(p.pendingStatement||'').split('|').map(v=>v.trim()).filter(Boolean);
        for(const j of js){
          const key=j.toUpperCase()+'-'+p.project.toUpperCase();
          if(!statementKey.test(key))continue;
          const item=itemFor(key);
          if(js.length===1&&p.pendingEvidence==='AMOUNT_VERIFIED 1/1'){
            item.statementAmount=p.pendingVerified;item.verified=true;
            item.evidence='LIFECYCLE_VERIFIED_AGGREGATE';
          }
          item.noticeAt=p.noticeAt||'';
        }
      }
    }
    for(const p of lifecycles){
      const js=(p.pendingStatement||'').split('|').map(v=>v.trim()).filter(Boolean);
      for(const j of js){
        const key=j.toUpperCase()+'-'+p.project.toUpperCase();
        if(statementKey.test(key))itemFor(key);
      }
    }
    for(const item of detailed.values()){
      const p=projectByX.get(item.project)||{};
      const open=(p.pendingStatement||'').split('|').map(v=>v.trim().toUpperCase());
      const j=item.statementId.split('-')[0];
      if(item.invoiceIds.length){
        item.state=!item.verified?'INVOICED_STATEMENT_UNVERIFIED'
          :item.invoiceAmount===item.statementAmount?'INVOICED_MATCHED':'INVOICE_ALLOCATION_REVIEW';
      }else if(open.includes(j)){
        item.state=item.verified?'PENDING_VERIFIED':'PENDING_UNVERIFIED';
      }else{item.state='SOURCE_LIFECYCLE_REVIEW';}
    }
    const statements=[...detailed.values()].sort((a,b)=>
      (b.noticeAt||b.issuedAt).localeCompare(a.noticeAt||a.issuedAt)||
      a.statementId.localeCompare(b.statementId));

    const backfillHeader=['Updated At KST','State','QQ Staged Headers','Web Cached UID','Body Ready','Body Empty MIME','Header Pending','Remaining Eligible','Batch Selected','Batch Body Fetched','Batch Empty MIME','Fetch Errors','Latest Source At','GitHub Run','Notes'];
    const backfillData=Array.isArray(mailBackfillSource)&&mailBackfillSource[0]?.join('|')===backfillHeader.join('|')
      ? mailBackfillSource[1]||[]:[];
    const mailBackfill=backfillData.length===15 ? {
      updated:backfillData[0],state:backfillData[1],
      qqStaged:money(backfillData[2]),webCached:money(backfillData[3]),
      bodyReady:money(backfillData[4]),mimeEmpty:money(backfillData[5]),
      headerPending:money(backfillData[6]),remaining:money(backfillData[7]),
      selected:money(backfillData[8]),batchFetched:money(backfillData[9]),
      batchMimeEmpty:money(backfillData[10]),errors:money(backfillData[11]),
      latestSourceAt:backfillData[12],runId:backfillData[13]
    }:{state:'NOT_VERIFIED'};
    const status=health.slice(1).filter(x=>['CSS Mail','Project Lifecycle','Revenue Lifecycle','Feishu'].includes(x[0]))
      .map(x=>({name:x[0],updated:x[1]||'',state:x[2]||'',details:x[3]||''}));
    // The inbox is intentionally metadata-only. Mail bodies are retrieved
    // by exact UID when the owner opens a message (no 999-row cache cutoff).
    const inbox=unanswered.slice(1).filter(r=>r[8]&&r[11]!=='TRUE')
      .map(r=>({uid:r[8],days:money(r[0]),priority:r[1]||'',sender:r[2]||'',
        subject:r[3]||'',received:r[4]||'',owner:r[5]||'',project:r[6]||'',
        class:r[10]||'',review:r[19]||'',body:'',bodyStatus:'FETCH_ON_DEMAND'}));
    const leads=projectPersonalLeads(lead);
    // This central console is a best-effort read-only projection. Missing
    // operational tabs must never leak data or disable the Sales workspace.
    let automation;
    try {
      automation=projectAutomationConsole(masterProgress||[],parallelTracks||[],health,workflowRuns||[]);
    } catch (_err) {
      automation={source:'SFDC_Automation_Followup_2026',readOnly:true,
        progress:{available:false},tracks:{available:false,items:[]},workflows:{available:false,items:[]},
        health:[],issues:['AUTOMATION_CONSOLE_SCHEMA_REVIEW_REQUIRED']};
    }
    // The official report can say READY, but this UI never authorizes a
    // Production promotion. Missing/stale/inconsistent evidence fails closed.
    automation.acceptance=projectOperationalAcceptance(await acceptancePromise);
    const reviews=decisions.slice(1).filter(r=>r[4]).map(r=>({uid:r[4],decision:r[0]||'NONE',sync:r[7]||'',sender:r[1]||'',subject:r[9]||''}));
    return res.status(200).json({months,revenueNetStatus,projects:lifecycles,statements,statementSource,status,inbox,leads,reviews,mailBackfill,automation,capabilities:{manualMailReview:process.env.CSS_WEB_DECISIONS_ENABLED==='true'},refreshed:months[0]?.refreshed||''});
  }catch(e){return res.status(503).json({error:'DATA_FETCH_FAILED'});}
};