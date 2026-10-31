'use strict';
/**
 * Read-only server-side integration smoke for CSS.
 *
 * This exercises the actual CSS route handlers with an ephemeral bearer token
 * and the already authorized Google Sheets service account from GitHub Actions.
 * It does NOT test Vercel SSO or a real owner browser session, and must never
 * be used as evidence for Production deployment approval.
 *
 * Only aggregate statuses appear in Actions logs: no UID, body, account,
 * access token, service account JSON, or customer information is emitted.
 */
const crypto=require('node:crypto');
const path=require('node:path');
const {GoogleAuth}=require('google-auth-library');

const ROOT=path.resolve(__dirname,'../..');
const SHEET='1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI';
const SCOPES=['https://www.googleapis.com/auth/spreadsheets.readonly'];
const VALID_UID=/^(?:inbox|sent):\d{1,14}$/i;

function assert(ok,code){if(!ok)throw Error(code)}
function fakeRes(){
  return {statusCode:200,headers:{},body:undefined,
    setHeader(k,v){this.headers[k.toLowerCase()]=v;return this;},
    status(v){this.statusCode=v;return this;},
    json(v){this.body=v;return this;},
    end(){return this;}
  };
}
async function call(handler,token,uid,valid=true){
  const req={method:'GET',headers:valid?{authorization:'Bearer '+token}:{},
    query:uid?{uid}:{}};
  const res=fakeRes();
  await handler(req,res);
  return res;
}
async function sheetsValues(client,range){
  const access=await (await client.getClient()).getAccessToken();
  assert(Boolean(access.token),'GOOGLE_READ_TOKEN_MISSING');
  const url='https://sheets.googleapis.com/v4/spreadsheets/'+SHEET+'/values/'+encodeURIComponent(range);
  const reply=await fetch(url,{
    headers:{Authorization:'Bearer '+access.token},signal:AbortSignal.timeout(20000)
  });
  assert(reply.ok,'GOOGLE_READ_HTTP_'+reply.status);
  const data=await reply.json();
  return data.values||[];
}
function pickVerifiedUid(ids,statuses){
  assert(ids.length&&ids[0]?.[0]==='Mail UID','CACHE_UID_SCHEMA');
  for(let i=1;i<ids.length;i++){
    const uid=String(ids[i]?.[0]||'');
    if(VALID_UID.test(uid)&&String(statuses[i]?.[0]||'')==='WEB_REVIEW_CACHE')return uid;
  }
  throw Error('NO_VERIFIED_BODY_CANDIDATE');
}
async function main(){
  const credential=process.env.GCP_SERVICE_ACCOUNT_JSON;
  assert(Boolean(credential),'SERVICE_ACCOUNT_ENV_MISSING');
  const parsed=JSON.parse(credential);
  assert(parsed&&parsed.client_email&&parsed.private_key,'SERVICE_ACCOUNT_JSON_INVALID');
  const client=new GoogleAuth({credentials:parsed,scopes:SCOPES});
  process.env.GOOGLE_SERVICE_ACCOUNT_JSON=credential;
  // The token is deliberately random and never equals any production secret.
  const ephemeral=crypto.randomBytes(32).toString('hex');
  process.env.CSS_WEB_ACCESS_TOKEN=ephemeral;
  process.env.VERCEL_APP_CLIENT_SECRET='ci-not-vercel-oauth-session';

  const lifecycle=require(path.join(ROOT,'apps/css-sales-workspace/api/lifecycle.js'));
  const bodyRoute=require(path.join(ROOT,'apps/css-sales-workspace/api/lifecycle/mail-body.js'));

  const unauth=await call(lifecycle,ephemeral,null,false);
  assert(unauth.statusCode===401,'UNAUTH_LIFECYCLE_MUST_BE_401');
  const unauthBody=await call(bodyRoute,ephemeral,'inbox:1',false);
  assert(unauthBody.statusCode===401,'UNAUTH_BODY_MUST_BE_401');
  const unsafe=await call(bodyRoute,ephemeral,'../invalid',true);
  assert(unsafe.statusCode===400,'INVALID_UID_MUST_BE_400');

  let dashboard;
  // Parallel Sheets readers can briefly return missing optional acceptance
  // data; retry the whole owner-authenticated local handler once, never
  // substitute approval or fabricate a successful source response.
  for(let attempt=0;attempt<2;attempt++){
    dashboard=await call(lifecycle,ephemeral);
    if(dashboard.statusCode===200 && dashboard.body?.automation?.acceptance?.available===true)break;
  }
  assert(dashboard.statusCode===200,'LIFECYCLE_NOT_200_'+dashboard.statusCode);
  assert(dashboard.headers['cache-control']==='private, no-store','LIFECYCLE_CACHE_NOT_PRIVATE');
  const data=dashboard.body||{};
  assert(Array.isArray(data.months)&&data.months.length>0,'LIFECYCLE_MONTHS_MISSING');
  assert(Array.isArray(data.inbox),'LIFECYCLE_MAIL_INBOX_SCHEMA');
  assert(Array.isArray(data.leads),'LIFECYCLE_LEAD_SCHEMA');
  const oct=data.months.find(m=>m.month==='2026-10');
  assert(oct&&oct.invoices>=1,'CURRENT_INVOICE_DATA_MISSING');
  assert(data.revenueNetStatus==='VERIFIED','REVENUE_NET_NOT_VERIFIED');
  assert(Number.isFinite(oct.netRevenue)&&oct.netRevenue>=0,'REVENUE_NET_UNAVAILABLE');
  assert(oct.actual>=oct.netRevenue,'REVENUE_GROSS_LT_NET');
  const gate=data.automation?.acceptance;
  assert(gate&&gate.available===true,'CENTRAL_ACCEPTANCE_SOURCE_NOT_VERIFIED');
  assert(gate.source==='CSS Operational Acceptance','ACCEPTANCE_SOURCE_ID_INVALID');
  assert(gate.releaseApproved===false,'UNAUTHORIZED_PRODUCTION_APPROVAL');
  assert(gate.rows?.some(x=>x.check==='Owner-authenticated Preview E2E'),
    'OWNER_BROWSER_E2E_EVIDENCE_MISSING');
  assert(gate.rows?.some(x=>x.check==='Production READY SHA parity'),
    'PRODUCTION_SHA_EVIDENCE_MISSING');
  assert(gate.rows?.some(x=>x.check==='Production acceptance'),
    'PRODUCTION_GATE_EVIDENCE_MISSING');
  assert(data.automation?.workflows?.available===true,'GITHUB_WORKFLOW_COUNT_SCHEMA_INVALID');
  assert(data.automation?.workflows?.items?.length===17,'EXPECTED_17_GITHUB_WORKFLOWS');

  // Minimal UID/status scans: NEVER read full body data for candidate search.
  const ids=await sheetsValues(client,"'CSS Mail Inbox Raw'!A1:A3000");
  const states=await sheetsValues(client,"'CSS Mail Inbox Raw'!V1:V3000");
  const uid=pickVerifiedUid(ids,states);
  const body=await call(bodyRoute,ephemeral,uid);
  assert(body.statusCode===200,'VERIFIED_MAIL_BODY_NOT_200_'+body.statusCode);
  assert(body.headers['cache-control']==='private, no-store','MAIL_BODY_CACHE_NOT_PRIVATE');
  assert(body.body?.classification==='WEB_REVIEW_CACHE','MAIL_BODY_CLASSIFICATION_MISMATCH');
  assert(typeof body.body?.body==='string'&&body.body.body.length>0,'MAIL_BODY_TEXT_MISSING');
  assert(body.body?.uid===uid,'MAIL_BODY_UID_NOT_IDENTICAL');

  console.log('CSS_SOURCE_CONTRACT=PASS');
  console.log('CSS_SOURCE_CONTRACT_CHECKS=lifecycle_owner_denial,body_owner_denial,invalid_uid,'+
    'real_monthly_net_vat,central_release_gate,17_workflow_statuses,real_lead_inbox_schema,original_body_exact_uid');
  console.log('CSS_SOURCE_CONTRACT_SCOPE=GITHUB_RUNNER_LOCAL_SERVERLESS_HANDLERS_WITH_LIVE_SHEETS');
  console.log('CSS_VERCEL_OWNER_BROWSER_E2E=NOT_TESTED');
  console.log('CSS_PRODUCTION_DEPLOYMENT_APPROVAL=NOT_GRANTED');
}
main().catch(err=>{
  // The failure code is internal/PII-free, never print the stack or requests.
  const code=String(err?.message||'UNKNOWN_ERROR');
  const safe=/^[A-Z_0-9]+$/.test(code)?code:'INTEGRATION_UNEXPECTED_FAILURE';
  console.error('CSS_SOURCE_CONTRACT=FAIL:'+safe);
  process.exitCode=1;
});
