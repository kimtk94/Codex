'use strict';
const {checkOwner,ownerSessionCookie}=require('../../lib/lifecycle-owner-auth');
const {readMetrics}=require('../../lib/feishu-base');
module.exports=async function handler(req,res){
  res.setHeader('Cache-Control','private, no-store, max-age=0');
  res.setHeader('Vary','Cookie, Authorization');
  res.setHeader('X-Content-Type-Options','nosniff');
  if(req.method!=='GET')return res.status(405).json({error:'METHOD_NOT_ALLOWED'});
  const token=process.env.CSS_WEB_ACCESS_TOKEN;
  if(!token)return res.status(503).json({error:'OWNER_AUTH_NOT_CONFIGURED'});
  const owner=checkOwner(req,token,process.env.VERCEL_APP_CLIENT_SECRET);
  if(!owner.valid)return res.status(401).json({error:'OWNER_LOGIN_REQUIRED'});
  if(owner.bearerValid)res.setHeader('Set-Cookie',ownerSessionCookie(token));
  try{
    const data=await readMetrics({appId:process.env.FEISHU_APP_ID,appSecret:process.env.FEISHU_APP_SECRET});
    return res.status(200).json(data);
  }catch(e){
    const status=e.status===503?503:502;
    return res.status(status).json({error:status===503?'FEISHU_CREDENTIALS_MISSING':'FEISHU_BASE_UNAVAILABLE'});
  }
};
