import {spawn} from "node:child_process";
import {join} from "node:path";
import {authorizeCommand} from "../../../../lib/sfdc-commands.mjs";
export const runtime="nodejs";
export const dynamic="force-dynamic";
const headers={"Content-Type":"application/json; charset=utf-8",
 "Cache-Control":"no-store,private,max-age=0","X-Content-Type-Options":"nosniff"};
const send=(x,s=200)=>new Response(JSON.stringify(x),{status:s,headers});
const deny=code=>send({status:"BLOCK",code,salesforceWrite:false},403);
let running=false;
function worker(input){
 return new Promise((resolve,reject)=>{
  const p=spawn(process.env.SFDC_LOCAL_PYTHON||"python",
    [join(process.cwd(),"scripts","sfdc_parallel_ui_check.py")],{
      cwd:process.cwd(),shell:false,windowsHide:true,
      env:{...process.env,PYTHONIOENCODING:"utf-8",PYTHONDONTWRITEBYTECODE:"1"},
      stdio:["pipe","pipe","ignore"]});
  let out="",done=false;
  const timer=setTimeout(()=>{p.kill();
    if(!done){done=true;reject(Error("PARALLEL_UI_TIMEOUT"))}},47000);
  p.stdout.setEncoding("utf8");
  p.stdout.on("data",v=>{out+=v;if(out.length>15000)p.kill()});
  p.on("error",()=>{clearTimeout(timer);
    if(!done){done=true;reject(Error("WORKER_ERROR"))}});
  p.on("close",()=>{
    clearTimeout(timer);if(done)return;done=true;
    try{const data=JSON.parse(out);
      if(!["PASS","HOLD"].includes(data.status)||
         data.salesforceWrite!==false||data.savePermitted!==false||
         !Array.isArray(data.results)||data.results.length>3)
        throw Error("UNSAFE_WORKER_RESPONSE");
      resolve(data);
    }catch{reject(Error("INVALID_PARALLEL_RESPONSE"))}
  });
  p.stdin.end(JSON.stringify(input));
 })
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
 if(!gate.ok)return deny(gate.code);
 if(running)return send({status:"HOLD",code:"PARALLEL_UI_BUSY",salesforceWrite:false},409);
 let input;
 try{
   const raw=await request.text();
   if(raw.length>700)throw Error("TOO_BIG");
   input=JSON.parse(raw);
   const ids=input.recordIds;
   if(input.mode!=="QUOTE_UI_BATCH"||!Array.isArray(ids)||
      ids.length<1||ids.length>3||new Set(ids).size!==ids.length||
      ids.some(x=>typeof x!=="string"||!/^a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/.test(x)))
      throw Error("INVALID");
 }catch{return send({status:"BLOCK",code:"BATCH_INPUT_INVALID",salesforceWrite:false},400)}
 running=true;
 try{return send(await worker(input))}
 catch{return send({status:"HOLD",code:"PARALLEL_SOURCE_UNAVAILABLE",salesforceWrite:false},503)}
 finally{running=false}
}
