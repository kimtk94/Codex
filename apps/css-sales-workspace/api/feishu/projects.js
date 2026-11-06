'use strict';
const {checkOwner,ownerSessionCookie}=require('../../lib/lifecycle-owner-auth');
const {readProjects}=require('../../lib/feishu-base');

module.exports=async function handler(req,res){
  res.setHeader('Cache-Control','private, no-store, max-age=0');
  res.setHeader('X-Content-Type-Options','nosniff');
  res.setHeader('Vary','Cookie, Authorization');
  if(req.method!=='GET')return res.status(405).json({error:'METHOD_NOT_ALLOWED'});
  const access=process.env.CSS_WEB_ACCESS_TOKEN;
  if(!access)return res.status(503).json({error:'OWNER_AUTH_NOT_CONFIGURED'});
  const identity=checkOwner(req,access,process.env.VERCEL_APP_CLIENT_SECRET);
  if(!identity.valid)return res.status(401).json({error:'OWNER_LOGIN_REQUIRED'});
  if(identity.bearerValid)res.setHeader('Set-Cookie',ownerSessionCookie(access));
  try{
    const results=await readProjects({
      appId:process.env.FEISHU_APP_ID,
      appSecret:process.env.FEISHU_APP_SECRET,
      cursor:req.query?.cursor||''
    });
    return res.status(200).json(results);
  }catch(err){
    const status=[400,503].includes(err.status)?err.status:502;
    // Never log or return secret values, access tokens, raw upstream messages,
    // private record payloads or the request cursor.
    const error=['BAD_CURSOR','FEISHU_CREDENTIALS_MISSING','FEISHU_TOKEN_NOT_RETURNED',
      'FEISHU_CURSOR_MISSING','FEISHU_RECORD_SCHEMA_INVALID'].includes(err.message)?
      err.message:'FEISHU_BASE_UNAVAILABLE';
    return res.status(status).json({error,source:'FEISHU_BASE'});
  }
};
