const crypto=require('crypto');
const host='https://css-sales-workspace-git.vercel.app';
const client=()=>process.env.VERCEL_APP_CLIENT_ID||process.env.NEXT_PUBLIC_VERCEL_APP_CLIENT_ID;
const secret=()=>process.env.VERCEL_APP_CLIENT_SECRET;
function cookies(req){return Object.fromEntries((req.headers.cookie||'').split(';').map(s=>s.trim()).filter(s=>s.includes('=')).map(s=>{const i=s.indexOf('=');return [s.slice(0,i),s.slice(i+1)]}));}
const cookie=(name,value,maxAge,path='/')=>name+'='+value+'; Path='+path+'; HttpOnly; Secure; SameSite=Lax; Max-Age='+maxAge;
function sign(value){return crypto.createHmac('sha256',secret()).update(value).digest('hex')}
function equal(a,b){return !!a&&!!b&&Buffer.byteLength(a)===Buffer.byteLength(b)&&crypto.timingSafeEqual(Buffer.from(a),Buffer.from(b))}
module.exports={crypto,host,client,secret,cookies,cookie,sign,equal};
