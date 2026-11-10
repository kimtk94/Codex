import {spawn} from "node:child_process";
import {join} from "node:path";
import {authorizeCommand} from "../../../../lib/sfdc-commands.mjs";

export const runtime="nodejs";
export const dynamic="force-dynamic";
let warming=false;
const headers={
  "Content-Type":"application/json; charset=utf-8",
  "Cache-Control":"private, no-store, max-age=0",
  "X-Content-Type-Options":"nosniff",
  "Vary":"Origin, Host, Sec-Fetch-Site"
};
const reply=(payload,status=200)=>new Response(JSON.stringify(payload),{status,headers});

function execPython(scriptName,input,limitMs){
  return new Promise((resolve,reject)=>{
    const python=process.env.SFDC_LOCAL_PYTHON||"python";
    const child=spawn(python,[join(process.cwd(),"scripts",scriptName)],{
      cwd:process.cwd(),shell:false,windowsHide:true,
      env:{...process.env,PYTHONIOENCODING:"utf-8",PYTHONDONTWRITEBYTECODE:"1"},
      stdio:["pipe","pipe","ignore"]
    });
    let data="",settled=false;
    const timer=setTimeout(()=>{child.kill();if(!settled){settled=true;reject(Error("CACHE_TIMEOUT"));}},limitMs);
    child.stdout.setEncoding("utf8");
    child.stdout.on("data",chunk=>{data+=chunk;if(data.length>14000)child.kill();});
    child.on("error",()=>{clearTimeout(timer);if(!settled){settled=true;reject(Error("CACHE_PROCESS_FAILED"));}});
    child.on("close",()=>{
      clearTimeout(timer);
      if(settled)return;
      settled=true;
      try{
        const result=JSON.parse(data);
        if(!result||!["PASS","PARTIAL","BLOCK","SOURCE_UNAVAILABLE"].includes(result.status)
           ||result.salesforce_write!==false||result.crm_writes===undefined&&scriptName.endsWith("_warm.py"))
          throw Error("UNSAFE_CACHE_RESULT");
        resolve(result);
      }catch{reject(Error("CACHE_OUTPUT_UNAVAILABLE"));}
    });
    child.stdin.end(input===null?"":JSON.stringify(input));
  });
}

function getAllowed(req){
  const host=req.headers.get("host");
  return process.env.SFDC_LOCAL_COMMAND_ENABLED==="1" &&
    /^127\.0\.0\.1:[0-9]{2,5}$/.test(host||"") &&
    req.headers.get("x-sfdc-command")==="1" &&
    (!req.headers.get("origin") || req.headers.get("origin")==="http://"+host) &&
    !["cross-site","same-site"].includes(req.headers.get("sec-fetch-site"));
}

export async function GET(request){
  if(!getAllowed(request))return reply({status:"BLOCK",code:"LOCAL_ONLY"},403);
  try{
    const result=await execPython("sfdc_pair_cache.py",null,7000);
    return reply({...result,warming},result.status==="PASS"?200:503);
  }catch{return reply({status:"BLOCK",code:"CACHE_STATUS_UNAVAILABLE",warming},503);}
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
  if(!gate.ok)return reply({status:"BLOCK",code:gate.code},gate.status);
  if(warming)return reply({status:"BLOCK",code:"CACHE_WARM_BUSY"},409);
  if(Number(request.headers.get("content-length")||0)>700)
    return reply({status:"BLOCK",code:"CACHE_INPUT_TOO_LARGE"},413);
  let input;
  try{
    const raw=await request.text();
    if(raw.length>700)throw Error("TOO_LONG");
    input=JSON.parse(raw);
    if(!input||input.mode!=="WARM" ||
       !Number.isInteger(input.limit)||input.limit<1||input.limit>5 ||
       !Number.isInteger(input.offset)||input.offset<0||input.offset>29)
      return reply({status:"BLOCK",code:"CACHE_WARM_FIELDS_INVALID"},400);
  }catch{return reply({status:"BLOCK",code:"INVALID_JSON"},400);}
  warming=true;
  try{
    const result=await execPython("sfdc_pair_cache_warm.py",input,180000);
    return reply(result,result.status==="PASS"?200:result.status==="PARTIAL"?206:503);
  }catch{return reply({status:"SOURCE_UNAVAILABLE",code:"CACHE_WARM_SOURCE_UNAVAILABLE"},503);
  }finally{warming=false;}
}
