const {oauthOrigin,matchesOriginHost,client,secret,cookies,cookie,sign,equal}=require('../../lib/auth-common');
const owner='xSqsomY4s3nWaElLeF9IE89Z';
module.exports=async(req,res)=>{
 res.setHeader('Cache-Control','no-store');
 if(req.method!=='GET')return res.status(405).end();
 const host=oauthOrigin();
 if(!host)return res.status(503).json({error:'PREVIEW_ORIGIN_UNAVAILABLE'});
 if(!matchesOriginHost(req,host))
   return res.status(409).json({error:'OAUTH_ORIGIN_MISMATCH'});
 const c=cookies(req),raw=c.css_oauth_pending||'',index=raw.lastIndexOf('.');
 res.setHeader('Set-Cookie',cookie('css_oauth_pending','',0,'/api/auth'));
 if(req.query.error){
   console.warn('CSS_OAUTH_PROVIDER_REJECTED');
   return res.redirect(302,host+'/?auth=provider_denied');
 }
 if(index<0||!req.query.code||!req.query.state){
   console.warn('CSS_OAUTH_STATE_MISSING');
   return res.redirect(302,host+'/?auth=state_missing');
 }
 let payload;try{payload=Buffer.from(raw.slice(0,index),'base64url').toString()}catch{console.warn('CSS_OAUTH_STATE_DECODE_FAILED');return res.redirect(302,host+'/?auth=state_invalid')}
 const parts=payload.split('.');
 if(parts.length!==3||!equal(sign(payload),raw.slice(index+1))||!equal(parts[0],String(req.query.state))||Math.abs(Date.now()/1000-Number(parts[2]))>600){console.warn('CSS_OAUTH_STATE_INVALID');return res.redirect(302,host+'/?auth=state_invalid')}
 try{
 const form=new URLSearchParams({grant_type:'authorization_code',client_id:client(),client_secret:secret(),code:String(req.query.code),code_verifier:parts[1],redirect_uri:host+'/api/auth/callback'});
 const tokenReply=await fetch('https://api.vercel.com/login/oauth/token',{method:'POST',body:form,signal:AbortSignal.timeout(12000)});
 if(!tokenReply.ok)throw Error('TOKEN_EXCHANGE');
 const tokens=await tokenReply.json();
 if(!tokens.access_token)throw Error('ACCESS_TOKEN_MISSING');
 const reply=await fetch('https://api.vercel.com/login/oauth/userinfo',{headers:{Authorization:'Bearer '+tokens.access_token},signal:AbortSignal.timeout(12000)});
 if(!reply.ok)throw Error('USERINFO_FAILED');
 const user=await reply.json();
 // The provider's authenticated subject is authoritative. Requiring an
 // optional email_verified claim incorrectly rejects valid owner sessions
 // when the app has no email scope/claim consent.
 if(user.sub!==owner){
   console.warn('CSS_OAUTH_OWNER_REJECTED');
   return res.redirect(302,host+'/?auth=owner_only');
 }
 const expiry=String(Math.floor(Date.now()/1000)+86400);
 const signature=sign('oauth-session:'+owner+':'+expiry);
 res.setHeader('Set-Cookie',[cookie('css_oauth_pending','',0,'/api/auth'),cookie('css_oauth_session',owner+'.'+expiry+'.'+signature,86400,'/api')]);
 return res.redirect(302,host+'/');
 }catch(e){
   // Enumerated error labels only; never write tokens, cookies, users or codes.
   const stage=['TOKEN_EXCHANGE','ACCESS_TOKEN_MISSING','USERINFO_FAILED'].includes(e.message)?e.message:'UNKNOWN';
   console.warn('CSS_OAUTH_CALLBACK_FAILED_'+stage);
   return res.redirect(302,host+'/?auth='+stage.toLowerCase());
 }
};