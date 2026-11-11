import {spawn} from "node:child_process";
import {join} from "node:path";
import {authorizeCommand} from "../../../../lib/sfdc-commands.mjs";

export const runtime="nodejs";
export const dynamic="force-dynamic";
const headers={"Content-Type":"application/json; charset=utf-8",
  "Cache-Control":"private, no-store, max-age=0",
  "X-Content-Type-Options":"nosniff","Vary":"Origin,Host,Sec-Fetch-Site"};
const reply=(value,status=200)=>new Response(JSON.stringify(value),{status,headers});

function worker(input){
  return new Promise((resolve,reject)=>{
    const child=spawn(process.env.SFDC_LOCAL_PYTHON||"python",[
      join(process.cwd(),"scripts","sfdc_identity_local.py")
    ],{cwd:process.cwd(),shell:false,windowsHide:true,
      env:{...process.env,PYTHONIOENCODING:"utf-8",PYTHONDONTWRITEBYTECODE:"1"},
      stdio:["pipe","pipe","ignore"]});
    let output="",done=false;
    const timer=setTimeout(()=>{child.kill();if(!done){done=true;reject(Error("IDENTITY_TIMEOUT"))}},15000);
    child.stdout.setEncoding("utf8");
    child.stdout.on("data",chunk=>{output+=chunk;if(output.length>120000)child.kill()});
    child.on("error",()=>{clearTimeout(timer);if(!done){done=true;reject(Error("IDENTITY_WORKER"))}});
    child.on("close",()=>{
      clearTimeout(timer);
      if(done)return;done=true;
      try{
        const value=JSON.parse(output);
        if(value.status!=="PASS"||value.local_only!==true||
          value.salesforce_write!==false||!Array.isArray(value.rows)||
          value.rows.length>25||!["FRESH","STALE"].includes(value.freshness)||
          value.rows.some(x=>(input.accountId&&x.account_id!==input.accountId)||
            typeof x.account_name!=="string"||!x.account_name.trim()||
            typeof x.contact_name!=="string"||!x.contact_name.trim()))
          throw Error("IDENTITY_UNVERIFIED");
        resolve(value);
      }catch{reject(Error("IDENTITY_WORKER_INVALID"))}
    });
    child.stdin.on("error",()=>{});
    child.stdin.end(JSON.stringify(input));
  });
}

export async function POST(request){
  const check=authorizeCommand({
    enabled:process.env.SFDC_LOCAL_COMMAND_ENABLED==="1",method:request.method,
    host:request.headers.get("host"),origin:request.headers.get("origin"),
    fetchSite:request.headers.get("sec-fetch-site"),
    header:request.headers.get("x-sfdc-command"),
    contentType:request.headers.get("content-type")
  });
  if(!check.ok)return reply({status:"BLOCK",code:check.code},check.status);
  let input;
  try{
    const raw=await request.text();
    if(raw.length>300)throw Error("INVALID_LENGTH");
    input=JSON.parse(raw);
    if(!input||Array.isArray(input)||typeof input!=="object"||
       Object.keys(input).length<2||Object.keys(input).length>3||
       Object.keys(input).some(k=>!["query","limit","accountId"].includes(k))||
       (input.accountId!==undefined&&
         (typeof input.accountId!=="string"||
          (input.accountId&&!/^001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/.test(input.accountId))))||
       typeof input.query!=="string"||!input.query.trim()||input.query.length>80||
       !Number.isInteger(input.limit)||input.limit<1||input.limit>25)
      throw Error("INVALID_QUERY");
  }catch{return reply({status:"BLOCK",code:"IDENTITY_QUERY_INVALID"},400)}
  try{return reply(await worker(input))}
  catch{return reply({status:"BLOCK",code:"IDENTITY_SOURCE_UNAVAILABLE"},503)}
}
