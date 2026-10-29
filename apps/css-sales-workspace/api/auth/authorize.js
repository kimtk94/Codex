const {crypto,host,client,secret,cookie,sign}=require('./common');
module.exports=async(req,res)=>{
 if(req.method!=='GET')return res.status(405).end();
 if(!client()||!secret())return res.status(503).json({error:'OAUTH_UNCONFIGURED'});
 const state=crypto.randomBytes(24).toString('hex'),verifier=crypto.randomBytes(32).toString('base64url');
 const challenge=crypto.createHash('sha256').update(verifier).digest('base64url');
 const stamp=String(Math.floor(Date.now()/1000));
 const payload=[state,verifier,stamp].join('.');
 res.setHeader('Set-Cookie',cookie('css_oauth_pending',Buffer.from(payload).toString('base64url')+'.'+sign(payload),600,'/api/auth'));
 const u=new URL('https://vercel.com/oauth/authorize');
 for(const [k,v] of Object.entries({client_id:client(),redirect_uri:host+'/api/auth/callback',response_type:'code',scope:'openid email',state,code_challenge:challenge,code_challenge_method:'S256'}))u.searchParams.set(k,v);
 return res.redirect(302,u.toString());
};