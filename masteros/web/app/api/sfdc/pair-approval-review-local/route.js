import {lstat,readdir,readFile} from "node:fs/promises";
import {join} from "node:path";
import {spawn} from "node:child_process";
import {authorizeCommand} from "../../../../lib/sfdc-commands.mjs";
import {isQueueRequestId,reviewQueueRecord} from "../../../../lib/sfdc-local-save-review.mjs";

export const runtime="nodejs";
export const dynamic="force-dynamic";
const responseHeaders={"Content-Type":"application/json; charset=utf-8",
 "Cache-Control":"private, no-store, max-age=0",
 "X-Content-Type-Options":"nosniff",
 "Vary":"Origin,Host,Sec-Fetch-Site"};
const respond=(x,status=200)=>new Response(JSON.stringify(x),{status,headers:responseHeaders});
const deny=(code,http=403)=>respond({status:"BLOCK",code,salesforceWrite:false,savePermitted:false},http);
let rehearsalBusy=false;
function directory(){
 const home=process.env.LOCALAPPDATA;
 if(!home||home.length>400)return null;
 return join(home,"SFDC_Oppo_Quote_Approval_Requests");
}
async function record(dir,id){
 if(!isQueueRequestId(id))return {status:"HOLD",code:"INVALID_REQUEST_ID"};
 const filepath=join(dir,id+".json");
 try{
  const stat=await lstat(filepath);
  if(!stat.isFile()||stat.isSymbolicLink()||stat.size<120||stat.size>50000)
   return {status:"HOLD",code:"QUEUE_FILE_UNSAFE"};
  const entry=JSON.parse(await readFile(filepath,"utf8"));
  return reviewQueueRecord(entry,id);
 }catch{return {status:"HOLD",code:"QUEUE_REQUEST_NOT_FOUND"}}
}
async function nativeSourceAuditForQueueId(id){
 const home=process.env.LOCALAPPDATA;
 if(!home||!isQueueRequestId(id))return {status:"NOT_RUN"};
 const folder=join(home,"SFDC_Native_Save_Approvals",id);
 try{
  const stat=await lstat(folder);
  if(!stat.isDirectory()||stat.isSymbolicLink())return {status:"HOLD_PRIVATE_AUDIT_FOLDER_UNSAFE"};
  const names=(await readdir(folder)).filter(
   x=>/^native_source_reconcile_\d{8}_\d{2}\.json$/.test(x)
  ).sort().reverse();
  if(!names.length)return {status:"NOT_RUN"};
  const path=join(folder,names[0]),file=await lstat(path);
  if(!file.isFile()||file.isSymbolicLink()||file.size<100||file.size>75000)
   return {status:"HOLD_NATIVE_SOURCE_AUDIT_FILE_INVALID"};
  const obj=JSON.parse(await readFile(path,"utf8"));
  if(obj.approval_request_id!==id||obj.save_permitted!==false||
     obj.crm_writes!==0||!["HOLD_NATIVE_QUOTE_SOURCE",
        "NATIVE_SOURCE_LINES_VERIFIED_NOT_SAVE_APPROVED"].includes(obj.status)||
     !Array.isArray(obj.reason_codes)||obj.reason_codes.length>25||
     !Array.isArray(obj.source_processes))
    return {status:"HOLD_NATIVE_SOURCE_AUDIT_PROVENANCE"};
  return {
    status:obj.status,
    reasonCodes:obj.reason_codes.filter(
      x=>typeof x==="string"&&/^[A-Z0-9_]{5,90}$/.test(x)),
    processRows:obj.source_processes.length,
    verifiedAtUtc:typeof obj.checked_at_utc==="string"?obj.checked_at_utc:null,
    savePermitted:false
  };
 }catch{return {status:"NOT_RUN"}}
}
function prepareUnsavedOpportunity(review){
 return new Promise((resolve,reject)=>{
  const child=spawn(process.env.SFDC_LOCAL_PYTHON||"python",
   [join(process.cwd(),"scripts","sfdc_prepare_unsaved_opportunity.py")],{
    cwd:process.cwd(),shell:false,windowsHide:true,
    env:{...process.env,PYTHONDONTWRITEBYTECODE:"1",PYTHONIOENCODING:"utf-8"},
    stdio:["pipe","pipe","ignore"]
   });
  let output="",settled=false;
  const timer=setTimeout(()=>{child.kill();if(!settled){settled=true;reject(Error("UNSAVED_FORM_TIMEOUT"))}},110000);
  child.stdout.setEncoding("utf8");
  child.stdout.on("data",chunk=>{output+=chunk;if(output.length>8000)child.kill()});
  child.on("error",()=>{clearTimeout(timer);if(!settled){settled=true;reject(Error("UNSAVED_WORKER_START_FAILED"))}});
  child.on("close",()=>{
   clearTimeout(timer);if(settled)return;settled=true;
   try{
    const x=JSON.parse(output);
    if(!["UNSAVED_OPPORTUNITY_FORM_READY","HOLD_FORM_PARTIAL"].includes(x.status)||
      x.salesforce_write!==false||x.save_clicked!==false||x.crm_writes!==0||
      !x.fields||typeof x.fields!=="object")
     throw Error("INVALID_UNSAVED_WORKER_RESPONSE");
    resolve(x);
   }catch{reject(Error("UNSAVED_WORKER_RESPONSE_INVALID"))}
  });
  child.stdin.on("error",()=>{});
  child.stdin.end(JSON.stringify({
   name:review.name,closeDate:review.closeDateKst,
   description:review.description
  }));
 });
}

function formRehearsal(){
 return new Promise((resolve,reject)=>{
  const py=process.env.SFDC_LOCAL_PYTHON||"python";
  const child=spawn(py,[join(process.cwd(),"scripts","sfdc_save_form_rehearsal.py")],{
   cwd:process.cwd(),shell:false,windowsHide:true,
   env:{...process.env,PYTHONDONTWRITEBYTECODE:"1",PYTHONIOENCODING:"utf-8"},
   stdio:["ignore","pipe","ignore"]
  });
  let output="",settled=false;
  const timer=setTimeout(()=>{child.kill();if(!settled){settled=true;reject(Error("FORM_REHEARSAL_TIMEOUT"))}},125000);
  child.stdout.setEncoding("utf8");
  child.stdout.on("data",s=>{output+=s;if(output.length>14000)child.kill()});
  child.on("error",()=>{clearTimeout(timer);if(!settled){settled=true;reject(Error("WORKER_LAUNCH_FAILED"))}});
  child.on("close",()=>{
   clearTimeout(timer);if(settled)return;settled=true;
   try{
    const data=JSON.parse(output);
    if(data.salesforce_write!==false||data.save_clicked!==false||
      !["PASS_FORM_INSPECTION","HOLD_FORM_INSPECTION"].includes(data.status)||
      !Array.isArray(data.forms)||data.forms.length!==2)
      throw Error("UNSAFE_REHEARSAL_RESULT");
    resolve(data);
   }catch{reject(Error("FORM_REHEARSAL_RESPONSE_INVALID"))}
  });
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
 if(!gate.ok)return deny(gate.code,gate.status);
 if(Number(request.headers.get("content-length")||0)>320)return deny("REQUEST_TOO_LARGE",413);
 let input;
 try{
  const text=await request.text();
  if(text.length>320)throw Error("OVERSIZE");
  input=JSON.parse(text);
  if(!input||Array.isArray(input)||
    Object.keys(input).some(k=>!["mode","requestId"].includes(k))||
    !["LIST","DETAIL","FORM_REHEARSAL","OPPO_UNSAVED_PREPARE"].includes(input.mode))
   throw Error("BAD_MODE");
  if(["DETAIL","OPPO_UNSAVED_PREPARE"].includes(input.mode)&&
    !isQueueRequestId(input.requestId))throw Error("BAD_ID");
  if(!["DETAIL","OPPO_UNSAVED_PREPARE"].includes(input.mode)&&
    input.requestId!==undefined)throw Error("UNEXPECTED_ID");
 }catch{return deny("SAVE_REVIEW_REQUEST_INVALID",400)}
 const dir=directory();
 if(!dir)return deny("PRIVATE_OPERATOR_QUEUE_UNAVAILABLE",503);
 if(input.mode==="LIST"){
  try{
   const stat=await lstat(dir);
   if(!stat.isDirectory()||stat.isSymbolicLink())return deny("QUEUE_UNSAFE",503);
   const names=(await readdir(dir)).filter(x=>/^OPPOQUOTE-[a-f0-9]{24}\.json$/.test(x));
   const subset=names.slice(-100);
   const result=(await Promise.all(subset.map(x=>record(dir,x.slice(0,-5)))))
     .filter(x=>x.status==="QUEUE_REVIEW_READY_SFDC_NATIVE_RECHECK_REQUIRED")
     .sort((a,b)=>(b.createdAtUtc||"").localeCompare(a.createdAtUtc||""));
   return respond({status:"PASS",items:result.map(x=>({
    requestId:x.requestId,createdAtUtc:x.createdAtUtc,name:x.name,
    productCount:x.productCount,queueStatus:x.queueStatus,
    accountName:x.account.name,contactName:x.contact.name,
    pendingChecks:x.requiredChecks.filter(y=>!y.passed).length,
    savePermitted:false})),
    total:result.length,scope:"PRIVATE_OPERATOR_PC_QUEUE",
    salesforceWrite:false,savePermitted:false});
  }catch(e){
   if(e?.code==="ENOENT")return respond({status:"PASS",items:[],total:0,
    scope:"PRIVATE_OPERATOR_PC_QUEUE",salesforceWrite:false,savePermitted:false});
   return deny("QUEUE_READ_FAILED",503);
  }
 }
 if(input.mode==="DETAIL"){
  const view=await record(dir,input.requestId);
  return view.status==="QUEUE_REVIEW_READY_SFDC_NATIVE_RECHECK_REQUIRED"?
   respond({...view,sourceAudit:await nativeSourceAuditForQueueId(input.requestId)}):
   deny(view.code||"QUEUE_INVALID",404);
 }
 if(input.mode==="OPPO_UNSAVED_PREPARE"){
  if(rehearsalBusy)return deny("LOCAL_SFDC_FORM_BUSY",409);
  const view=await record(dir,input.requestId);
  if(view.status!=="QUEUE_REVIEW_READY_SFDC_NATIVE_RECHECK_REQUIRED"||
     !["PENDING_APPROVAL","NEEDS_REVIEW"].includes(view.queueStatus)||
     !view.name||!view.closeDateKst||!view.description)
    return deny("REVIEW_QUEUE_NOT_READY_FOR_UNSAVED_FORM",422);
  rehearsalBusy=true;
  try{
   const result=await prepareUnsavedOpportunity(view);
   return respond({...result,approvalRequestId:view.requestId,
     savePermitted:false,operatorSaveRequired:true});
  }catch{return deny("UNSAVED_OPPO_FORM_PREPARE_FAILED",503)}
  finally{rehearsalBusy=false}
 }
 if(rehearsalBusy)return deny("FORM_REHEARSAL_BUSY",409);
 rehearsalBusy=true;
 try{
  const result=await formRehearsal();
  return respond({...result,savePermitted:false,crmWrites:0});
 }catch{return deny("LOCAL_SFDC_FORM_REHEARSAL_UNAVAILABLE",503)}
 finally{rehearsalBusy=false}
}
