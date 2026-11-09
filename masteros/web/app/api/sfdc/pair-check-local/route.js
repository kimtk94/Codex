import {spawn} from "node:child_process";
import {join} from "node:path";
import {authorizeCommand} from "../../../../../lib/sfdc-commands.mjs";

export const runtime="nodejs";
export const dynamic="force-dynamic";
let running=false;
const headers={
  "Content-Type":"application/json; charset=utf-8",
  "Cache-Control":"private, no-store, max-age=0",
  "X-Content-Type-Options":"nosniff",
  "Vary":"Origin, Host, Sec-Fetch-Site"
};
const respond=(x,status=200)=>new Response(JSON.stringify(x),{status,headers});

function execReadOnly(input){
  const script=join(process.cwd(),"scripts","sfdc_pair_web_preview.py");
  return new Promise((resolve,reject)=>{
    const p=spawn(process.env.SFDC_LOCAL_PYTHON||"python",[script],{
      cwd:process.cwd(),shell:false,windowsHide:true,
      env:{...process.env,PYTHONIOENCODING:"utf-8",PYTHONDONTWRITEBYTECODE:"1"},
      stdio:["pipe","pipe","ignore"]
    });
    let finished=false,output="";
    const timer=setTimeout(()=>{p.kill();if(!finished){finished=true;reject(Error("READ_ONLY_TIMEOUT"));}},145000);
    p.stdout.setEncoding("utf8");
    p.stdout.on("data",chunk=>{output+=chunk;if(output.length>45000)p.kill();});
    p.on("error",()=>{clearTimeout(timer);if(!finished){finished=true;reject(Error("WORKER_NOT_AVAILABLE"));}});
    p.on("close",()=>{
      clearTimeout(timer);if(finished)return;
      finished=true;
      try{
        const result=JSON.parse(output);
        if(!["BLOCK","HOLD","PREVIEW_READY","PREFLIGHT_PASS","PREFLIGHT_BLOCK","PASS"].includes(result?.status)||
           result.salesforce_write!==false||result.save_permitted!==false)
          throw Error("UNSAFE_WORKER_REPLY");
        resolve(result);
      }catch{reject(Error("WORKER_REPLY_INVALID"));}
    });
    p.stdin.end(JSON.stringify(input));
  });
}

export async function POST(request){
  const gate=authorizeCommand({
    enabled:process.env.SFDC_LOCAL_COMMAND_ENABLED==="1",
    method:request.method,host:request.headers.get("host"),
    origin:request.headers.get("origin"),
    fetchSite:request.headers.get("sec-fetch-site"),
    header:request.headers.get("x-sfdc-command"),
    contentType:request.headers.get("content-type")
  });
  if(!gate.ok)return respond({status:"BLOCK",code:gate.code},gate.status);
  if(running)return respond({status:"BLOCK",code:"PAIR_CHECK_BUSY"},409);
  if(Number(request.headers.get("content-length")||0)>5000)
    return respond({status:"BLOCK",code:"REQUEST_TOO_LARGE"},413);
  let input;
  try{
    const raw=await request.text();
    if(raw.length>5000)throw Error("REQUEST_TOO_LARGE");
    input=JSON.parse(raw);
    if(!input||typeof input!=="object"||Array.isArray(input)||
       !["CHECK_PRICE","CHECK_FORMS","CHECK_READBACK"].includes(input.mode)||
       (input.runMode && input.runMode!=="CHECK"))
      return respond({status:"BLOCK",code:"READ_ONLY_MODE_REQUIRED"},400);
  }catch{return respond({status:"BLOCK",code:"INVALID_JSON"},400);}
  running=true;
  try{
    const result=await execReadOnly(input);
    return respond(result,result.status==="BLOCK"||result.status==="PREFLIGHT_BLOCK"?422:200);
  }catch{
    return respond({status:"BLOCK",code:"LOCAL_READ_ONLY_SOURCE_UNAVAILABLE"},503);
  }finally{running=false;}
}
