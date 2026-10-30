'use strict';
// Local-only fixture host. Never serves env files or live API responses.
const http=require('node:http');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const allow=new Map([
  ['/mail-queue.html',['mail-queue.html','text/html; charset=utf-8']],
  ['/mail-queue.js',['mail-queue.js','text/javascript; charset=utf-8']],
  ['/index.html',['index.html','text/html; charset=utf-8']],
]);
const port=Number(process.env.CSS_E2E_PORT||4174);
if(!Number.isInteger(port)||port<1024||port>65535)throw Error('BAD_E2E_PORT');
const server=http.createServer((req,res)=>{
  const target=allow.get((req.url||'').split('?')[0]);
  res.setHeader('Cache-Control','no-store');
  res.setHeader('X-Content-Type-Options','nosniff');
  if(req.method!=='GET'||!target){
    res.writeHead(404,{'Content-Type':'text/plain'});res.end('NOT_FOUND');return;
  }
  const file=path.join(root,target[0]);
  const contents=fs.readFileSync(file);
  res.writeHead(200,{'Content-Type':target[1]});
  res.end(contents);
});
server.listen(port,'127.0.0.1',()=>console.log('LOCAL_MOCK_WEB_READY='+port));
