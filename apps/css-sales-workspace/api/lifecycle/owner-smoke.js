'use strict';
// User-initiated, Vercel-OAuth-only on-deployment diagnostic.
// No customer data or original message IDs are sent in the response.
// No source mutation, email sending, SFDC Save or deployment promotion.
const {GoogleAuth}=require('google-auth-library');
const {checkOwner}=require('../../lib/lifecycle-owner-auth');
const lifecycle=require('../lifecycle.js');
const bodyHandler=require('./mail-body.js');
const SHEET='1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI';
const UID=/^(?:inbox|sent):[0-9]{1,14}$/i;
const CACHE_STATE='WEB_REVIEW_CACHE';
function internalResponse(){
 return {statusCode:200,data:null,headers:{},
  setHeader(k,v){this.headers[k.toLowerCase()]=v;return this},
  status(code){this.statusCode=code;return this},
  json(obj){this.data=obj;return this},
  end(){return this}};
}
function findCachedUid(ids,classes){
 if(ids?.[0]?.[0]!=='Mail UID')throw Error('MAIL_UID_SCHEMA');
 if(classes?.[0]?.[0]!=='Body Status')throw Error('MAIL_STATUS_SCHEMA');
 for(let i=1;i<ids.length;i++){
   const uid=String(ids[i]?.[0]||'');
   if(UID.test(uid)&&String(classes[i]?.[0]||'')===CACHE_STATE)return uid;
 }
 throw Error('NO_VERIFIED_BODY');
}
module.exports=async function handler(req,res){
 res.setHeader('Cache-Control','private, no-store');
 res.setHeader('X-Content-Type-Options','nosniff');
 if(req.method!=='GET')return res.status(405).json({error:'METHOD_NOT_ALLOWED'});
 const token=process.env.CSS_WEB_ACCESS_TOKEN;
 const oauth=process.env.VERCEL_APP_CLIENT_SECRET;
 if(!token||!oauth)return res.status(503).json({error:'AUTH_NOT_CONFIGURED'});
 // Explicitly reject bearer-only sessions: this is an OAuth browser test,
 // not a second copy of the GitHub source-backed bearer contract.
 const owner=checkOwner(req,token,oauth);
 if(!owner.oauthValid)return res.status(401).json({error:'VERCEL_OWNER_OAUTH_REQUIRED'});
 try{
   const dashboard=internalResponse();
   await lifecycle({method:'GET',headers:{cookie:req.headers?.cookie||''}},dashboard);
   if(dashboard.statusCode!==200||dashboard.data?.revenueNetStatus!=='VERIFIED'
      ||!Array.isArray(dashboard.data?.months)
      ||!dashboard.data.months.some(x=>Number.isFinite(x.netRevenue)&&x.month))
     throw Error('LIFECYCLE_PARITY_NOT_VERIFIED');
   const raw=process.env.GOOGLE_SERVICE_ACCOUNT_JSON;
   if(!raw)throw Error('SOURCE_CREDENTIAL_MISSING');
   const auth=new GoogleAuth({credentials:JSON.parse(raw),
     scopes:['https://www.googleapis.com/auth/spreadsheets.readonly']});
   const access=await(await auth.getClient()).getAccessToken();
   if(!access.token)throw Error('SOURCE_TOKEN_MISSING');
   const ranges=["'CSS Mail Inbox Raw'!A1:A10000","'CSS Mail Inbox Raw'!V1:V10000"];
   const url='https://sheets.googleapis.com/v4/spreadsheets/'+SHEET+
     '/values:batchGet?'+ranges.map(x=>'ranges='+encodeURIComponent(x)).join('&');
   const response=await fetch(url,{headers:{Authorization:'Bearer '+access.token},
     signal:AbortSignal.timeout(12000)});
   if(!response.ok)throw Error('SOURCE_METADATA_UNAVAILABLE');
   const values=(await response.json()).valueRanges||[];
   const [ids,classes]=values.map(x=>x.values||[]);
   const uid=findCachedUid(ids,classes);
   const body=internalResponse();
   await bodyHandler({method:'GET',headers:{cookie:req.headers.cookie},
     query:{uid}},body);
   if(body.statusCode!==200||body.data?.uid!==uid
      ||body.data.classification!==CACHE_STATE
      ||typeof body.data.body!=='string'||!body.data.body.length)
     throw Error('BODY_ENDPOINT_PARITY_FAILED');
   return res.status(200).json({
     state:'PASS',
     auth:'VERCEL_OWNER_OAUTH',
     lifecycle:'LIVE_SHEETS_VERIFIED',
     revenue:'VAT_EXCLUDED_PARITY_VERIFIED',
     mailBody:'EXACT_UID_BODY_VERIFIED',
     dataDisclosure:'NO_CUSTOMER_DATA_IN_DIAGNOSTIC',
     productionPromotion:false
   });
 }catch(_err){
   // No stacks or user records: do not include UID/body/token/source URLs.
   return res.status(503).json({state:'BLOCK',error:'OWNER_LIVE_DIAGNOSTIC_FAILED',
     productionPromotion:false});
 }
};
module.exports.findCachedUid=findCachedUid;
