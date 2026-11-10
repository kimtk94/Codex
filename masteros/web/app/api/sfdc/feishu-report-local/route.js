import {spawn} from "node:child_process";
import {join} from "node:path";
import {authorizeCommand} from "../../../../lib/sfdc-commands.mjs";

export const runtime="nodejs";
export const dynamic="force-dynamic";

const headers={
  "Content-Type":"application/json; charset=utf-8",
  "Cache-Control":"private, no-store, max-age=0",
  "X-Content-Type-Options":"nosniff",
  "Vary":"Origin,Host,Sec-Fetch-Site"
};
const reply=(data,status=200)=>new Response(JSON.stringify(data),{status,headers});
let refreshing=false;

function localGet(request){
  const host=request.headers.get("host")||"";
  const origin=request.headers.get("origin");
  return process.env.SFDC_LOCAL_COMMAND_ENABLED==="1" &&
    /^127\.0\.0\.1:\d{2,5}$/.test(host) &&
    request.headers.get("x-sfdc-command")==="1" &&
    (!origin||origin==="http://"+host) &&
    !["cross-site","same-site"].includes(request.headers.get("sec-fetch-site"));
}
function pythonCall(request,timeout=18000){
  return new Promise((resolve,reject)=>{
    const executable=process.env.SFDC_LOCAL_PYTHON||"python";
    const command=join(process.cwd(),"scripts","sfdc_feishu_report_local.py");
    const child=spawn(executable,[command],{
      cwd:process.cwd(),shell:false,windowsHide:true,
      env:{...process.env,PYTHONIOENCODING:"utf-8",PYTHONDONTWRITEBYTECODE:"1"},
      stdio:["pipe","pipe","ignore"]
    });
    let output="",finished=false;
    const timer=setTimeout(()=>{child.kill();if(!finished){finished=true;reject(Error("FEISHU_REPORT_TIMEOUT"));}},timeout);
    child.stdout.setEncoding("utf8");
    child.stdout.on("data",chunk=>{output+=chunk;if(output.length>110000)child.kill();});
    child.on("error",()=>{clearTimeout(timer);if(!finished){finished=true;reject(Error("FEISHU_REPORT_WORKER_FAILED"));}});
    child.on("close",()=>{
      clearTimeout(timer);
      if(finished)return;
      finished=true;
      try{
        const payload=JSON.parse(output);
        if(!["PASS","BLOCK"].includes(payload?.status) ||
           payload.salesforce_write!==false ||
           payload.feishu_writes!==0 ||
           payload.local_only!==true)
          throw Error("FEISHU_UNSAFE_RESPONSE");
        resolve(payload);
      }catch{reject(Error("FEISHU_REPORT_INVALID_RESPONSE"));}
    });
    child.stdin.end(JSON.stringify(request));
  });
}
export async function GET(request){
  if(!localGet(request))return reply({status:"BLOCK",code:"LOCAL_ONLY"},403);
  try{
    const value=await pythonCall({mode:"STATUS"},8000);
    return reply(value,value.status==="PASS"?200:503);
  }catch{return reply({status:"BLOCK",code:"FEISHU_STATUS_UNAVAILABLE"},503);}
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
  let body;
  try{
    const raw=await request.text();
    if(raw.length>500)throw Error("INVALID_LENGTH");
    body=JSON.parse(raw);
    if(!body||typeof body!=="object"||Array.isArray(body))throw Error("INVALID_BODY");
    if(!["REFRESH","REFRESH_REFERENCES","REFERENCE_STATUS","SEARCH","DETAIL","IDENTITY_SEARCH","OPPORTUNITY_SEARCH","OPPORTUNITY_QUOTES"].includes(body.mode))
      return reply({status:"BLOCK",code:"FEISHU_READ_ONLY_MODE_REQUIRED"},400);
    if(body.mode==="SEARCH"&&
       (typeof body.query!=="string"||body.query.length>80||
        !Number.isInteger(body.limit)||body.limit<1||body.limit>30))
      return reply({status:"BLOCK",code:"FEISHU_SEARCH_INVALID"},400);
    if(body.mode==="IDENTITY_SEARCH"&&
       (typeof body.query!=="string"||body.query.trim().length<1||
        body.query.length>80||!Number.isInteger(body.limit)||
        body.limit<1||body.limit>25))
      return reply({status:"BLOCK",code:"IDENTITY_QUERY_INVALID"},400);
    if(body.mode==="OPPORTUNITY_SEARCH"&&
       (typeof body.query!=="string"||body.query.length>80||
        !Number.isInteger(body.limit)||body.limit<1||body.limit>30))
      return reply({status:"BLOCK",code:"OPPORTUNITY_SEARCH_INVALID"},400);
    if(body.mode==="OPPORTUNITY_QUOTES"&&
       (typeof body.opportunityExternal!=="string"||
        !/^[A-Za-z0-9][A-Za-z0-9_-]{3,99}$/.test(body.opportunityExternal)))
      return reply({status:"BLOCK",code:"OPPORTUNITY_REFERENCE_INVALID"},400);
    if(body.mode==="DETAIL"&&
       (typeof body.id!=="string"||
        !/^(QID-[0-9-]{8,50}|a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)$/.test(body.id)))
      return reply({status:"BLOCK",code:"FEISHU_QUOTE_ID_INVALID"},400);
  }catch{return reply({status:"BLOCK",code:"FEISHU_INPUT_INVALID"},400);}
  if(refreshing)return reply({status:"BLOCK",code:"FEISHU_REFRESH_BUSY"},409);
  if(["REFRESH","REFRESH_REFERENCES"].includes(body.mode))refreshing=true;
  try{
    const value=await pythonCall(body,["REFRESH","REFRESH_REFERENCES"].includes(body.mode)?180000:18000);
    return reply(value,value.status==="PASS"?200:422);
  }catch{return reply({status:"BLOCK",code:"FEISHU_READ_SOURCE_UNAVAILABLE"},503);
  }finally{if(["REFRESH","REFRESH_REFERENCES"].includes(body.mode))refreshing=false;}
}
