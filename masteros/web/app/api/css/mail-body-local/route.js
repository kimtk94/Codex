import {spawn} from "node:child_process";
import {join} from "node:path";
import {authorizeCssMailLocal} from "../../../../lib/css-mail-local.mjs";

export const runtime="nodejs";
export const dynamic="force-dynamic";
const headers={
  "Content-Type":"application/json; charset=utf-8",
  "Cache-Control":"private, no-store, max-age=0",
  "X-Content-Type-Options":"nosniff",
  "Vary":"Origin,Host,Sec-Fetch-Site"
};
const send=(data,status=200)=>new Response(JSON.stringify(data),{headers,status});
const UID=/^inbox:[0-9]{1,14}$/i;
const KEY=/^[A-Za-z0-9_./|:-]{3,150}$/;

async function readWorker(body) {
  return new Promise((resolve,reject)=>{
    const child=spawn(process.env.CSS_LOCAL_PYTHON||"python",[
      join(process.cwd(),"scripts","css_mail_local.py")
    ],{cwd:process.cwd(),windowsHide:true,shell:false,
      env:{...process.env,PYTHONIOENCODING:"utf-8",PYTHONDONTWRITEBYTECODE:"1"},
      stdio:["pipe","pipe","ignore"]});
    let output="",done=false;
    const timeout=setTimeout(()=>{child.kill();if(!done){done=true;reject(Error("TIMEOUT"))}},45000);
    child.stdout.setEncoding("utf8");
    child.stdout.on("data",part=>{output+=part;if(output.length>800000)child.kill()});
    child.on("error",()=>{clearTimeout(timeout);if(!done){done=true;reject(Error("WORKER"))}});
    child.on("close",()=>{
      clearTimeout(timeout);
      if(done)return;
      done=true;
      try {
        const parsed=JSON.parse(output);
        if(parsed.status!=="PASS"||parsed.uid!==body.uid||
           typeof parsed.body!=="string"||parsed.body.length>150000||
           typeof parsed.bodyStatus!=="string"||parsed.bodyStatus.length>80)
          throw Error("BODY_SOURCE_UNVERIFIED");
        resolve(parsed);
      }catch{reject(Error("BODY_INVALID"))}
    });
    child.stdin.on("error",()=>{});
    child.stdin.end(JSON.stringify(body));
  });
}
export async function GET(request){
  const gate=authorizeCssMailLocal({
    enabled:process.env.CSS_LOCAL_MAIL_ENABLED==="1",
    method:request.method,host:request.headers.get("host"),
    origin:request.headers.get("origin"),
    fetchSite:request.headers.get("sec-fetch-site"),
    header:request.headers.get("x-css-local-mail"),
  });
  if(!gate.ok)return send({status:"BLOCK",code:gate.code},gate.status);
  const url=new URL(request.url);
  const uid=url.searchParams.get("uid")||"";
  const key=url.searchParams.get("key")||"";
  if(url.searchParams.size!==2||!UID.test(uid)||!KEY.test(key))
    return send({status:"BLOCK",code:"MAIL_BODY_KEY_INVALID"},400);
  try{
    return send(await readWorker({mode:"body",uid,key}));
  }catch{
    return send({status:"BLOCK",code:"MAIL_BODY_SOURCE_UNAVAILABLE"},503);
  }
}
