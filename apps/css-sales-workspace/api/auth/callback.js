const {host,client,secret,cookies,cookie,sign,equal}=require('../../lib/auth-common');
const owner='xSqsomY4s3nWaElLeF9IE89Z';
module.exports=async(req,res)=>{
 res.setHeader('Cache-Control','no-store');
 if(req.method!=='GET')return res.status(405).end();
 const c=cookies(req),raw=c.css_oauth_pending||'',index=raw.lastIndexOf('.');
 res.setHeader('Set-Cookie',cookie('css_oauth_pending','',0,'/api/auth'));
 if(index<0||!req.query.code||!req.query.state)return res.redirect(302,host+'/?login=failed');
 let payload;try{payload=Buffer.from(raw.slice(0,index),'base64url').toString()}catch{return res.status(401).end()}
 const parts=payload.split('.');
 if(parts.length!==3||!equal(sign(payload),raw.slice(index+1))||!equal(parts[0],String(req.query.state))||Math.abs(Date.now()/1000-Number(parts[2]))>600)return res.status(401).end();
 try{
 const form=new URLSearchParams({grant_type:'authorization_code',client_id:client(),client_secret:secret(),code:String(req.query.code),code_verifier:parts[1],redirect_uri:host+'/api/auth/callback'});
 const tokenReply=await fetch('https://api.vercel.com/login/oauth/token',{method:'POST',body:form,signal:AbortSignal.timeout(12000)});
 if(!tokenReply.ok)throw Error('TOKEN_EXCHANGE');
 const tokens=await tokenReply.json();
 if(!tokens.access_token)throw Error('ACCESS_TOKEN_MISSING');
 const reply=await fetch('https://api.vercel.com/login/oauth/userinfo',{headers:{Authorization:'Bearer '+tokens.access_token},signal:AbortSignal.timeout(12000)});
 if(!reply.ok)throw Error('USERINFO_FAILED');
 const user=await reply.json();
 if(user.sub!==owner||user.email_verified!==true)return res.status(403).json({error:'OWNER_ONLY'});
 const expiry=String(Math.floor(Date.now()/1000)+86400);
 const signature=sign('oauth-session:'+owner+':'+expiry);
 res.setHeader('Set-Cookie',[cookie('css_oauth_pending','',0,'/api/auth'),cookie('css_oauth_session',owner+'.'+expiry+'.'+signature,86400,'/api/lifecycle')]);
 return res.redirect(302,host+'/');
 }catch(e){return res.redirect(302,host+'/?login=failed')}
};