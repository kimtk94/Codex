import {spawn} from "node:child_process";
import {join} from "node:path";
import {authorizeCommand} from "../../../../lib/sfdc-commands.mjs";

export const runtime="nodejs";
export const dynamic="force-dynamic";
const HEADERS={"Content-Type":"application/json; charset=utf-8",
  "Cache-Control":"private, no-store, max-age=0",
  "X-Content-Type-Options":"nosniff","Vary":"Origin,Host,Sec-Fetch-Site"};
let isImporting=false;
const reply=(v,status=200)=>new Response(JSON.stringify(v),{status,headers:HEADERS});

function isLocalGet(request){
 const host=request.headers.get("host")||"";
 const origin=request.headers.get("origin");
 return process.env.SFDC_LOCAL_COMMAND_ENABLED==="1" &&
   /^127\.0\.0\.1:\d{2,5}$/.test(host) &&
   request.headers.get("x-sfdc-command")==="1" &&
   (!origin||origin==="http://"+host) &&
   !["cross-site","same-site"].includes(request.headers.get("sec-fetch-site"));
}

function runReport(input,timeoutMs=15000){
 return new Promise((resolve,reject)=>{
  const worker=join(process.cwd(),"scripts","sfdc_quote_report_index.py");
  const child=spawn(process.env.SFDC_LOCAL_PYTHON||"python",[worker],{
   cwd:process.cwd(),shell:false,windowsHide:true,
   env:{...process.env,PYTHONIOENCODING:"utf-8",PYTHONDONTWRITEBYTECODE:"1"},
   stdio:["pipe","pipe","ignore"]
  });
  let output="",finished=false;
  const timer=setTimeout(()=>{child.kill();if(!finished){finished=true;reject(Error("REPORT_TIMEOUT"));}},timeoutMs);
  child.stdout.setEncoding("utf8");
  child.stdout.on("data",c=>{output+=c;if(output.length>120000)child.kill();});
  child.on("error",()=>{clearTimeout(timer);if(!finished){finished=true;reject(Error("REPORT_WORKER_NOT_FOUND"));}});
  child.on("close",()=>{
   clearTimeout(timer);if(finished)return;finished=true;
   try{
    const result=JSON.parse(output);
    if(!["PASS","BLOCK"].includes(result?.status)||
       result.salesforce_write!==false||result.local_only!==true)
       throw Error("UNTRUSTED_REPORT_REPLY");
    resolve(result);
   }catch{reject(Error("REPORT_INVALID_REPLY"));}
  });
  child.stdin.end(JSON.stringify(input));
 });
}

export async function GET(request){
 if(!isLocalGet(request))return reply({status:"BLOCK",code:"LOCAL_ONLY"},403);
 try{
  const result=await runReport({mode:"STATUS"},7000);
  return reply(result,result.status==="PASS"?200:503);
 }catch{return reply({status:"BLOCK",code:"REPORT_UNAVAILABLE"},503);}
}

export async function POST(request){
 const gate=authorizeCommand({
  enabled:process.env.SFDC_LOCAL_COMMAND_ENABLED==="1",
  method:request.method,host:request.headers.get("host"),
  origin:request.headers.get("origin"),fetchSite:request.headers.get("sec-fetch-site"),
  header:request.headers.get("x-sfdc-command"),
  contentType:request.headers.get("content-type")
 });
 if(!gate.ok)return reply({status:"BLOCK",code:gate.code},gate.status);
 let input;
 try{
  const raw=await request.text();
  if(raw.length>512)throw Error("REQUEST_TOO_LARGE");
  input=JSON.parse(raw);
  if(!input||typeof input!=="object"||Array.isArray(input)||
   !["IMPORT","SEARCH","DETAIL"].includes(input.mode))
   return reply({status:"BLOCK",code:"READ_ONLY_REPORT_MODE_REQUIRED"},400);
  if(input.mode==="SEARCH"&&(
   typeof input.query!=="string"||input.query.length>80||
   !Number.isInteger(input.limit)||input.limit<1||input.limit>30))
   return reply({status:"BLOCK",code:"REPORT_SEARCH_INVALID"},400);
  if(input.mode==="DETAIL"&&(
   typeof input.id!=="string"||
   !/^(QID-[0-9-]{8,40}|a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)$/.test(input.id)))
   return reply({status:"BLOCK",code:"REPORT_QUOTE_ID_INVALID"},400);
 }catch{return reply({status:"BLOCK",code:"INVALID_JSON"},400);}
 if(isImporting)return reply({status:"BLOCK",code:"REPORT_IMPORT_BUSY"},409);
 if(input.mode==="IMPORT")isImporting=true;
 try{
  const result=await runReport(input,input.mode==="IMPORT"?90000:12000);
  return reply(result,result.status==="PASS"?200:422);
 }catch{return reply({status:"BLOCK",code:"REPORT_SOURCE_UNAVAILABLE"},503);
 }finally{if(input.mode==="IMPORT")isImporting=false;}
}
