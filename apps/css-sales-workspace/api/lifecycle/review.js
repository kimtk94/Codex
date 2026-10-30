'use strict';
// Explicit, owner-approved manual actions only. Never sends mail or writes CRM.
const crypto=require('node:crypto');
const {GoogleAuth}=require('google-auth-library');
const {validateAction,locateTarget}=require('../../lib/mail-review-decision');
const BOOK='1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI';
const TAB="'Email Review Decisions'";
const SHEETS='https://sheets.googleapis.com/v4/spreadsheets/'+BOOK+'/values/';
const OWNER='xSqsomY4s3nWaElLeF9IE89Z';

function secureEqual(a,b){
  const x=Buffer.from(String(a||'')),y=Buffer.from(String(b||''));
  return x.length>0&&x.length===y.length&&crypto.timingSafeEqual(x,y);
}
function cookieValue(req,name){
  const entry=(req.headers.cookie||'').split(';').map(x=>x.trim())
    .find(x=>x.startsWith(name+'='));
  return entry?entry.slice(name.length+1):'';
}
function isOwner(req){
  const token=process.env.CSS_WEB_ACCESS_TOKEN;
  if(!token)return false;
  const bearer=/^Bearer (.+)$/i.exec(req.headers.authorization||'');
  if(bearer&&secureEqual(bearer[1],token))return true;
  const now=Math.floor(Date.now()/1000);
  const plain=/^(\d{10})\.([a-f0-9]{64})$/.exec(cookieValue(req,'css_owner_session'));
  if(plain){
    const deadline=Number(plain[1]);
    const sig=crypto.createHmac('sha256',token).update('css-owner:'+plain[1]).digest('hex');
    if(deadline>now&&deadline<=now+86400&&secureEqual(sig,plain[2]))return true;
  }
  const oauth=/^([A-Za-z0-9_-]+)\.(\d{10})\.([a-f0-9]{64})$/.exec(cookieValue(req,'css_oauth_session'));
  if(!oauth||oauth[1]!==OWNER||!process.env.VERCEL_APP_CLIENT_SECRET)return false;
  const expiry=Number(oauth[2]);
  const sig=crypto.createHmac('sha256',process.env.VERCEL_APP_CLIENT_SECRET)
    .update('oauth-session:'+OWNER+':'+oauth[2]).digest('hex');
  return expiry>now&&expiry<=now+86400&&secureEqual(sig,oauth[3]);
}

function sameOriginRequest(req){
  const host=String(req.headers.host||'').toLowerCase();
  const origin=String(req.headers.origin||'');
  if(!host||!origin)return false;
  try{
    const u=new URL(origin);
    if(u.protocol!=='https:'||u.host.toLowerCase()!==host||u.pathname!=='/')return false;
  }catch{return false;}
  const fetchSite=String(req.headers['sec-fetch-site']||'');
  if(fetchSite&&fetchSite!=='same-origin')return false;
  return req.headers['x-css-review-confirm']==='EXPLICIT_USER_APPROVAL';
}
function error(res,status,code){return res.status(status).json({error:code});}
function sheetUrl(range){return SHEETS+encodeURIComponent(range);}

module.exports=async function handler(req,res){
  res.setHeader('Cache-Control','no-store, private');
  res.setHeader('X-Content-Type-Options','nosniff');
  if(req.method!=='POST')return error(res,405,'METHOD_NOT_ALLOWED');
  if(!isOwner(req))return error(res,401,'OWNER_AUTH_REQUIRED');
  if(process.env.CSS_WEB_DECISIONS_ENABLED!=='true')return error(res,503,'MANUAL_DECISIONS_NOT_ENABLED');
  if(!sameOriginRequest(req))return error(res,403,'REVIEW_ORIGIN_OR_APPROVAL_REQUIRED');
  if(!/^application\/json(?:;|$)/i.test(req.headers['content-type']||''))
    return error(res,415,'JSON_REQUIRED');
  let request;
  try{
    if(JSON.stringify(req.body||{}).length>800)throw Error('INVALID_REVIEW_FIELDS');
    request=validateAction(req.body);
  }catch(e){return error(res,400,e.message);}
  try{
    const raw=process.env.GOOGLE_SERVICE_ACCOUNT_JSON;
    if(!raw)return error(res,503,'SHEETS_CREDENTIALS_MISSING');
    const auth=new GoogleAuth({credentials:JSON.parse(raw),
      scopes:['https://www.googleapis.com/auth/spreadsheets']});
    const client=await auth.getClient();
    const read=async range=>{
      const v=await client.request({url:sheetUrl(range)});
      return v.data.values||[];
    };
    const rows=await read(TAB+'!A1:J1300');
    let target;
    try{target=locateTarget(rows,request);}
    catch(e){return error(res,409,e.message);}
    if(target.action===request.action)return res.status(200).json({
      status:'ALREADY_SELECTED',uid:request.uid,decision:request.action,synced:target.status===('SYNCED:'+request.action)
    });
    // A (action) + H (sync) are the only write targets. All other columns,
    // including manual reviewer notes and original source records, are kept.
    const base=SHEETS.split('/values/')[0];
    const operations=[{
      range:TAB+'!A'+target.rowIndex,values:[[request.action]]
    },{
      range:TAB+'!H'+target.rowIndex,values:[['NOT_SUBMITTED']]
    }];
    await client.request({url:base+'/values:batchUpdate',method:'POST',
      data:{valueInputOption:'RAW',data:operations}});
    const checked=await read(TAB+'!A'+target.rowIndex+':H'+target.rowIndex);
    if(checked.length!==1||String(checked[0][0]||'').trim()!==request.action||
       String(checked[0][7]||'').trim()!=='NOT_SUBMITTED')
      return error(res,502,'REVIEW_WRITE_READBACK_FAILED');
    return res.status(200).json({
      status:'QUEUED_FOR_EXISTING_GITHUB_SYNC',uid:request.uid,
      decision:request.action,synced:false
    });
  }catch(_e){return error(res,502,'REVIEW_SHEET_UPDATE_FAILED');}
};
