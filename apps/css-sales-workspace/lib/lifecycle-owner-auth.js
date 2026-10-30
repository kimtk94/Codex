'use strict';
const crypto=require('crypto');
const OWNER='xSqsomY4s3nWaElLeF9IE89Z';

function equal(a,b){
  if(typeof a!=='string'||typeof b!=='string'||!a||!b)return false;
  const aa=Buffer.from(a),bb=Buffer.from(b);
  return aa.length===bb.length&&crypto.timingSafeEqual(aa,bb);
}
function getCookie(req,name){
  const parts=String(req.headers?.cookie||'').split(';');
  const match=parts.map(s=>s.trim()).find(s=>s.startsWith(name+'='));
  return match?match.slice(name.length+1):'';
}
function checkOwner(req,token,oauthSecret,now=Math.floor(Date.now()/1000)){
  if(!token)return {valid:false,bearerValid:false};
  const supplied=String(req.headers?.authorization||'').replace(/^Bearer /i,'');
  const bearerValid=!!supplied&&equal(supplied,token);
  const ownerSession=getCookie(req,'css_owner_session');
  const parts=/^(\d{10})\.([a-f0-9]{64})$/.exec(ownerSession);
  let sessionValid=false;
  if(parts){
    const expiry=Number(parts[1]);
    const signature=crypto.createHmac('sha256',token)
      .update('css-owner:'+parts[1]).digest('hex');
    sessionValid=expiry>now&&expiry<=now+86400&&equal(parts[2],signature);
  }
  const oauth=getCookie(req,'css_oauth_session');
  const om=/^(xSqsomY4s3nWaElLeF9IE89Z)\.(\d{10})\.([a-f0-9]{64})$/.exec(oauth);
  let oauthValid=false;
  if(om&&oauthSecret){
    const expiry=Number(om[2]);
    const signature=crypto.createHmac('sha256',oauthSecret)
      .update('oauth-session:'+OWNER+':'+om[2]).digest('hex');
    oauthValid=expiry>now&&expiry<=now+86400&&equal(om[3],signature);
  }
  return {valid:bearerValid||sessionValid||oauthValid,bearerValid,oauthValid};
}
function ownerSessionCookie(token,now=Math.floor(Date.now()/1000)){
  const expiry=String(now+86400);
  const signature=crypto.createHmac('sha256',token).update('css-owner:'+expiry).digest('hex');
  return 'css_owner_session='+expiry+'.'+signature+
    '; HttpOnly; Secure; SameSite=Strict; Path=/api/lifecycle; Max-Age=86400';
}
module.exports={checkOwner,ownerSessionCookie};
