'use strict';
// Credential-free, read-only runtime diagnostic for protected Vercel deployments.
// Reports configuration *presence* only. Never fetches customer data or sets auth cookies.
module.exports = function handler(req,res){
  res.setHeader('Cache-Control','no-store');
  res.setHeader('X-Content-Type-Options','nosniff');
  res.setHeader('Content-Type','application/json; charset=utf-8');
  if(req.method!=='GET' && req.method!=='HEAD'){
    res.setHeader('Allow','GET, HEAD');
    return res.status(405).json({state:'METHOD_NOT_ALLOWED'});
  }
  const configured={
    oauthClient:Boolean(process.env.VERCEL_APP_CLIENT_ID ||
                        process.env.NEXT_PUBLIC_VERCEL_APP_CLIENT_ID),
    oauthSecret:Boolean(process.env.VERCEL_APP_CLIENT_SECRET),
    sheetsServiceAccount:Boolean(process.env.GOOGLE_SERVICE_ACCOUNT_JSON),
    ownerToken:Boolean(process.env.CSS_WEB_ACCESS_TOKEN)
  };
  const ready=Object.values(configured).every(Boolean);
  const body={status:ready?'RUNTIME_CONFIG_PRESENT':'RUNTIME_CONFIG_INCOMPLETE',
    apiRoute:'CSS_HEALTH_PROBE_V1',readOnly:true,
    credentialsPresent:configured,
    ownerAuthenticated:false,liveSheetsVerified:false,
    dataAccessRequiresOwner:true,releaseApproved:false};
  if(req.method==='HEAD')return res.status(ready?200:503).end();
  return res.status(ready?200:503).json(body);
};
