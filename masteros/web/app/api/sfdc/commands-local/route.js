import {spawn,execFile} from "node:child_process";
import {promisify} from "node:util";
import {join} from "node:path";
import {homedir} from "node:os";
import {stat} from "node:fs/promises";
import {validateRequest,authorizeCommand} from "../../../../lib/sfdc-commands.mjs";

export const runtime="nodejs";
export const dynamic="force-dynamic";
let inProgress=false;
const headers={"Content-Type":"application/json; charset=utf-8",
               "Cache-Control":"private, no-store, max-age=0",
               "X-Content-Type-Options":"nosniff",
               "Vary":"Origin, Host, Sec-Fetch-Site"};
const reply=(payload,status=200)=>new Response(JSON.stringify(payload),{status,headers});
function gate(request) {
  return authorizeCommand({
    enabled:process.env.SFDC_LOCAL_COMMAND_ENABLED==="1",
    method:request.method,host:request.headers.get("host"),
    origin:request.headers.get("origin"),
    fetchSite:request.headers.get("sec-fetch-site"),
    header:request.headers.get("x-sfdc-command"),
    contentType:request.headers.get("content-type"),
  });
}
async function executePython(input) {
  const bin=process.env.SFDC_LOCAL_PYTHON||"python";
  const script=join(process.cwd(),"scripts","sfdc_action_executor.py");
  return new Promise((resolve,reject)=>{
    const child=spawn(bin,[script],{
      cwd:process.cwd(),shell:false,windowsHide:true,
      env:{...process.env,PYTHONIOENCODING:"utf-8",PYTHONDONTWRITEBYTECODE:"1"},
      stdio:["pipe","pipe","ignore"]
    });
    let data="",settled=false;
    const timer=setTimeout(()=>{child.kill(); if(!settled){settled=true;reject(Error("UI_TIMEOUT"));}},100000);
    child.stdout.setEncoding("utf8");
    child.stdout.on("data",chunk=>{
      data+=chunk;
      if(data.length>20000)child.kill();
    });
    child.on("error",()=>{clearTimeout(timer);if(!settled){settled=true;reject(Error("EXEC_FAILED"));}});
    child.on("close",()=>{
      clearTimeout(timer);
      if(settled)return;
      settled=true;
      try{
        const result=JSON.parse(data);
        if(!result||typeof result.status!=="string")throw Error("INVALID_RESULT");
        resolve(result);
      }catch{reject(Error("INVALID_SCRIPT_OUTPUT"));}
    });
    child.stdin.end(JSON.stringify(input));
  });
}
export async function POST(request){
  const allowed=gate(request);
  if(!allowed.ok)return reply({status:"BLOCK",code:allowed.code},allowed.status);
  if(inProgress)return reply({status:"BLOCK",code:"ANOTHER_SFDC_OPERATION_RUNNING"},409);
  if(Number(request.headers.get("content-length")||0)>12000)
    return reply({status:"BLOCK",code:"REQUEST_TOO_LARGE"},413);
  let input;
  try{
    const body=await request.text();
    if(body.length>12000)throw Error("TOO_LONG");
    input=JSON.parse(body);
  }catch{return reply({status:"BLOCK",code:"INVALID_JSON"},400);}
  const valid=validateRequest(input);
  if(!valid.ok)return reply({status:"BLOCK",code:valid.code},400);
  inProgress=true;
  try{
    const result=await executePython(input);
    return reply(result,result.status.startsWith("BLOCK")?422:200);
  }catch{
    return reply({status:"BLOCK",code:"LOCAL_EXECUTION_FAILED"},503);
  }finally{inProgress=false;}
}
async function fileExists(p) {
  try{const s=await stat(p);return s.isFile()&&s.size>20;}catch{return false;}
}
export async function GET(request){
  // Health is also local-only, with explicit header. No customer data is returned.
  const ok=request.headers.get("host")?.match(/^127\.0\.0\.1:[0-9]{2,5}$/) &&
    request.headers.get("x-sfdc-command")==="1" &&
    process.env.SFDC_LOCAL_COMMAND_ENABLED==="1" &&
    (!request.headers.get("origin") ||
     request.headers.get("origin")==="http://"+request.headers.get("host")) &&
    !["cross-site","same-site"].includes(request.headers.get("sec-fetch-site"));
  if(!ok)return reply({status:"BLOCK",code:"LOCAL_ONLY"},403);
  // Do not confuse a CDP tab with a logged-in, operational Salesforce view.
  let views={lead_view:"BLOCK",opportunity_view:"BLOCK",quote_view:"BLOCK"};
  try{
    const python=process.env.SFDC_LOCAL_PYTHON||"python";
    const script=join(process.cwd(),"scripts","sfdc_live_ui_health.py");
    const {stdout}=await promisify(execFile)(python,[script],{
      timeout:60000,maxBuffer:12000,windowsHide:true,
      env:{...process.env,PYTHONIOENCODING:"utf-8",PYTHONDONTWRITEBYTECODE:"1"},
    });
    const result=JSON.parse(stdout);
    for(const k of ["lead_view","opportunity_view","quote_view"]){
      views[k]=result?.[k]==="PASS"?"PASS":"BLOCK";
    }
  }catch{
    // Missing/expired Salesforce session is BLOCK, never an implicit PASS.
  }
  const dataDir=join(homedir(),".sfdc_desktop");
  const contacts=await fileExists(join(dataDir,"account_contact_all_scope_PRIVATE.json"));
  const quote=await fileExists(join(dataDir,"all_quotation_inventory_20261103_PRIVATE.json"));
  const browserReady=Object.values(views).every(v=>v==="PASS");
  return reply({status:"HEALTH_CHECK",
    contact_lookup:contacts?"SNAPSHOT_READY":"BLOCK",
    opportunity_quote_history:quote?"SNAPSHOT_READY":"BLOCK",
    salesforce_browser:browserReady?"PASS":"BLOCK",
    ...views,
    lead_convert:views.lead_view==="PASS"?"UI_READY_SAVE_UNVERIFIED":"BLOCK",
    opportunity_create:views.opportunity_view==="PASS"?"UI_READY_SAVE_UNVERIFIED":"BLOCK",
    quote_create:"PRODUCT_SAVE_UNVERIFIED",
    live_salesforce_object_verified:false,
    save_readback_verified:false,
    operation_running:inProgress
  });
}
