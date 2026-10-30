'use strict';
// Fetch a single verified owner Inbox/Sent body on demand.
// The list endpoint intentionally does not fetch large MIME bodies.
const {GoogleAuth}=require('google-auth-library');
const {checkOwner,ownerSessionCookie}=require('../../lib/lifecycle-owner-auth');
const SHEET='1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI';
const UID=/^(?:inbox|sent):[0-9]{1,14}$/i;
const BASE='https://sheets.googleapis.com/v4/spreadsheets/'+SHEET+'/values/';
function rowByUid(uidRows,uid){
  if(uidRows?.[0]?.[0]!=='Mail UID')throw Error('UID_COLUMN_SCHEMA_MISMATCH');
  let found=null;
  for(let i=1;i<uidRows.length;i++){
    if(String(uidRows[i]?.[0]||'').toLowerCase()!==uid.toLowerCase())continue;
    if(found!==null)throw Error('DUPLICATE_MAIL_UID');
    found=i+1;
  }
  return found;
}
module.exports=async function handler(req,res){
  res.setHeader('Cache-Control','private, no-store');
  res.setHeader('X-Content-Type-Options','nosniff');
  if(req.method!=='GET')return res.status(405).json({error:'METHOD_NOT_ALLOWED'});
  const token=process.env.CSS_WEB_ACCESS_TOKEN;
  if(!token)return res.status(503).json({error:'AUTH_NOT_CONFIGURED'});
  const owner=checkOwner(req,token,process.env.VERCEL_APP_CLIENT_SECRET);
  if(!owner.valid)return res.status(401).json({error:'AUTH_REQUIRED'});
  const uid=typeof req.query?.uid==='string'?req.query.uid:'';
  if(!UID.test(uid))return res.status(400).json({error:'INVALID_MAIL_UID'});
  if(owner.bearerValid)res.setHeader('Set-Cookie',ownerSessionCookie(token));
  try{
    const raw=process.env.GOOGLE_SERVICE_ACCOUNT_JSON;
    if(!raw)return res.status(503).json({error:'SHEETS_CREDENTIALS_MISSING'});
    const auth=new GoogleAuth({credentials:JSON.parse(raw),
      scopes:['https://www.googleapis.com/auth/spreadsheets.readonly']});
    const access=await (await auth.getClient()).getAccessToken();
    const headers={Authorization:'Bearer '+access.token};
    async function read(range){
      const response=await fetch(BASE+encodeURIComponent(range),{
        headers,signal:AbortSignal.timeout(12000)});
      if(!response.ok)throw Error('SHEETS_HTTP_'+response.status);
      return (await response.json()).values||[];
    }
    // UID-only scan is bounded, body transfer is a single matching row.
    const ids=await read("'CSS Mail Inbox Raw'!A1:A10000");
    const at=rowByUid(ids,uid);
    if(at===null)return res.status(404).json({error:'UID_NOT_CACHED'});
    const found=await read("'CSS Mail Inbox Raw'!A"+at+":V"+at);
    const value=found[0]||[];
    if(String(value[0]||'').toLowerCase()!==uid.toLowerCase())
      return res.status(409).json({error:'SOURCE_ROW_CHANGED'});
    const body=String(value[9]||'');
    const classification=String(value[21]||'');
    if(!body)return res.status(404).json({error:'BODY_NOT_AVAILABLE',classification});
    return res.status(200).json({uid,body,classification});
  }catch(err){
    if(String(err.message)==='DUPLICATE_MAIL_UID')
      return res.status(409).json({error:'DUPLICATE_MAIL_UID'});
    return res.status(503).json({error:'MAIL_BODY_SOURCE_UNAVAILABLE'});
  }
};
