import {spawn} from "node:child_process";
import {join} from "node:path";
import {authorizeCssMailLocal,parseLocalMailAction,validateLocalMailResult} from "../../../../lib/css-mail-local.mjs";

export const runtime="nodejs";
export const dynamic="force-dynamic";
const headers={
  "Content-Type":"application/json; charset=utf-8",
  "Cache-Control":"private, no-store, max-age=0",
  "X-Content-Type-Options":"nosniff",
  "Vary":"Origin,Host,Sec-Fetch-Site"
};
const send=(data,status=200)=>new Response(JSON.stringify(data),{status,headers});

function gate(request){
  return authorizeCssMailLocal({
    enabled:process.env.CSS_LOCAL_MAIL_ENABLED==="1",
    method:request.method,host:request.headers.get("host"),
    origin:request.headers.get("origin"),
    fetchSite:request.headers.get("sec-fetch-site"),
    header:request.headers.get("x-css-local-mail"),
    contentType:request.headers.get("content-type")
  });
}
function runWorker(body){
  return new Promise((resolve,reject)=>{
    const child=spawn(process.env.CSS_LOCAL_PYTHON||"python",[
      join(process.cwd(),"scripts","css_mail_local.py")
    ],{cwd:process.cwd(),shell:false,windowsHide:true,
       env:{...process.env,PYTHONIOENCODING:"utf-8",PYTHONDONTWRITEBYTECODE:"1"},
       stdio:["pipe","pipe","ignore"]});
    let output="",finished=false;
    const timer=setTimeout(()=>{
      child.kill();
      if(!finished){finished=true;reject(Error("WORKER_TIMEOUT"))}
    },65000);
    child.stdout.setEncoding("utf8");
    child.stdout.on("data",value=>{
      output+=value;
      if(output.length>8_000_000)child.kill();
    });
    child.on("error",()=>{
      clearTimeout(timer);
      if(!finished){finished=true;reject(Error("WORKER_UNAVAILABLE"))}
    });
    child.on("close",()=>{
      clearTimeout(timer);
      if(finished)return;
      finished=true;
      try{
        resolve(validateLocalMailResult(JSON.parse(output),body.mode));
      }catch{reject(Error("INVALID_WORKER_RESPONSE"))}
    });
    child.stdin.on("error",()=>{});
    child.stdin.end(JSON.stringify(body));
  });
}
let writing=false;
export async function GET(request){
  const auth=gate(request);
  if(!auth.ok)return send({status:"BLOCK",code:auth.code},auth.status);
  try{
    const result=await runWorker({mode:"snapshot"});
    return send(result,result.status==="BLOCK"?503:200);
  }catch{return send({status:"BLOCK",code:"MAIL_LEAD_SOURCE_UNAVAILABLE"},503)}
}
export async function POST(request){
  const auth=gate(request);
  if(!auth.ok)return send({status:"BLOCK",code:auth.code},auth.status);
  let body;
  try{
    const raw=await request.text();
    if(raw.length>1600)throw Error("TOO_LARGE");
    body=parseLocalMailAction(JSON.parse(raw));
  }catch{return send({status:"BLOCK",code:"INVALID_MAIL_REVIEW_ACTION"},400)}
  if(writing)return send({status:"BLOCK",code:"REVIEW_WRITE_BUSY"},409);
  writing=true;
  try{
    const result=await runWorker(body);
    return send(result,result.status==="PASS"?200:422);
  }catch{return send({status:"BLOCK",code:"LOCAL_REVIEW_ACTION_FAILED"},503)}
  finally{writing=false}
}
