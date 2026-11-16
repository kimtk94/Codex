import {spawn} from "node:child_process";
import {join} from "node:path";
import {authorizeCommand} from "../../../../lib/sfdc-commands.mjs";
import {validKrwNativeContactQuery} from "../../../../lib/sfdc-krw-native-contact-lookup.mjs";

export const runtime="nodejs";
export const dynamic="force-dynamic";
let inProgress=false;

const headers={
 "Content-Type":"application/json; charset=utf-8",
 "Cache-Control":"private, no-store, max-age=0",
 "X-Content-Type-Options":"nosniff",
 "Vary":"Origin,Host,Sec-Fetch-Site"
};
const send=(object,status=200)=>new Response(JSON.stringify(object),{status,headers});
const safeError=(code)=>({status:"BLOCK",code,salesforce_write:false,local_only:true});

function runReadOnlyWorker(input){
 return new Promise((resolve,reject)=>{
  const child=spawn(process.env.SFDC_LOCAL_PYTHON||"python",
   [join(process.cwd(),"scripts","sfdc_krw_native_contact_lookup.py")],
   {cwd:process.cwd(),shell:false,windowsHide:true,
    env:{...process.env,PYTHONIOENCODING:"utf-8",PYTHONDONTWRITEBYTECODE:"1"},
    stdio:["pipe","pipe","ignore"]});
  let out="",settled=false;
  const timer=setTimeout(()=>{child.kill();if(!settled){settled=true;reject(Error("SOURCE_TIMEOUT"));}},115000);
  child.stdout.setEncoding("utf8");
  child.stdout.on("data",fragment=>{out+=fragment;if(out.length>60000)child.kill()});
  child.on("error",()=>{clearTimeout(timer);if(!settled){settled=true;reject(Error("WORKER_ERROR"))}});
  child.on("close",()=>{
   clearTimeout(timer);
   if(settled)return;
   settled=true;
   try{
    const data=JSON.parse(out);
    if(!data||data.local_only!==true||data.salesforce_write!==false||
       !["PASS","BLOCK"].includes(data.status)||
       !Array.isArray(data.candidates)||data.candidates.length>10||
       !Number.isInteger(data.unresolved_matches)||
       data.unresolved_matches<0)
      throw Error("WORKER_RESULT_INVALID");
    resolve(data);
   }catch{reject(Error("SOURCE_RESPONSE_INVALID"))}
  });
  child.stdin.on("error",()=>{});
  child.stdin.end(JSON.stringify(input));
 });
}

export async function POST(request){
 const gate=authorizeCommand({
  enabled:process.env.SFDC_KRW_CONTACT_READONLY_ENABLED==="1",
  method:request.method,
  host:request.headers.get("host"),
  origin:request.headers.get("origin"),
  fetchSite:request.headers.get("sec-fetch-site"),
  header:request.headers.get("x-sfdc-command"),
  contentType:request.headers.get("content-type")
 });
 if(!gate.ok)return send(safeError(gate.code),gate.status);
 if(inProgress)return send(safeError("CONTACT_LOOKUP_BUSY"),409);
 if(Number(request.headers.get("content-length")||0)>400)
  return send(safeError("REQUEST_TOO_LARGE"),413);
 let parsed;
 try{
  const raw=await request.text();
  if(!raw||raw.length>400)throw Error("INVALID_SIZE");
  parsed=JSON.parse(raw);
 }catch{return send(safeError("INVALID_JSON"),400)}
 const verified=validKrwNativeContactQuery(parsed);
 if(!verified.ok)return send(safeError(verified.code),400);
 inProgress=true;
 try{
  const result=await runReadOnlyWorker(verified.request);
  return send(result,result.status==="PASS"?200:422);
 }catch{
  return send(safeError("SFDC_AUTHENTICATED_CONTACT_UNAVAILABLE"),503);
 }finally{inProgress=false;}
}
