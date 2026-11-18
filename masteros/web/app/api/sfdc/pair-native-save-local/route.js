/** Explicit, authenticated laptop-only Salesforce native Save button transport.
 *
 * Never infers approval from an old Quote's price or pending queue state.
 * All personal customer records stay in %LOCALAPPDATA%; GitHub has only code.
 * PRECHECK and COMMIT must both pass fresh Python native+price+identity guards.
 */
import {spawn} from "node:child_process";
import {join} from "node:path";
import {authorizeCommand} from "../../../../lib/sfdc-commands.mjs";
import {isQueueRequestId} from "../../../../lib/sfdc-local-save-review.mjs";

export const runtime="nodejs";
export const dynamic="force-dynamic";
const headers={"Content-Type":"application/json; charset=utf-8",
 "Cache-Control":"private, no-store, max-age=0",
 "X-Content-Type-Options":"nosniff","Vary":"Origin,Host,Sec-Fetch-Site"};
const respond=(body,status=200)=>new Response(JSON.stringify(body),{status,headers});
const block=(code,status=403)=>respond({status:"BLOCK",code,save_clicked:false,
 salesforce_write:false,savePermitted:false},status);
const TOKEN=/^[a-f0-9]{48}$/;
const DIGEST=/^SFDC-REVIEW-[a-f0-9]{24}$/;
let working=false;

function validate(x){
 if(!x||typeof x!=="object"||Array.isArray(x)||
   Object.keys(x).some(k=>!["mode","stage","requestId","approvalDigest","nonce","confirmation"].includes(k))||
   !["PRECHECK","COMMIT"].includes(x.mode)||
   !["OPPORTUNITY","QUOTATION"].includes(x.stage)||
   !isQueueRequestId(x.requestId))return "INVALID_NATIVE_SAVE_REQUEST";
 if(x.mode==="PRECHECK"){
   if(x.nonce!==undefined||x.approvalDigest!==undefined||x.confirmation!==undefined)
     return "PRECHECK_CANNOT_CONTAIN_SAVE_APPROVAL";
 }else if(typeof x.nonce!=="string"||!TOKEN.test(x.nonce)||
   typeof x.approvalDigest!=="string"||!DIGEST.test(x.approvalDigest)||
   x.confirmation!=="SAVE "+x.approvalDigest.slice(-8))
   return "EXACT_PER_RECORD_SAVE_APPROVAL_REQUIRED";
 return null;
}
function execute(message){
 return new Promise((resolve,reject)=>{
   const child=spawn(process.env.SFDC_LOCAL_PYTHON||"python",
    [join(process.cwd(),"scripts","sfdc_native_approved_save.py")],{
      cwd:process.cwd(),shell:false,windowsHide:true,
      env:{...process.env,PYTHONDONTWRITEBYTECODE:"1",PYTHONIOENCODING:"utf-8"},
      stdio:["pipe","pipe","ignore"]
    });
   let output="",settled=false;
   // If a process is interrupted after clicking, the worker journal
   // fails closed. Never retry a timed-out COMMIT automatically.
   const timer=setTimeout(()=>{child.kill();
    if(!settled){settled=true;reject(Error("NATIVE_SAVE_TIMEOUT_RECONCILE"))}},155000);
   child.stdout.setEncoding("utf8");
   child.stdout.on("data",chunk=>{
     output+=chunk;
     if(output.length>11000)child.kill();
   });
   child.on("error",()=>{clearTimeout(timer);
    if(!settled){settled=true;reject(Error("NATIVE_WORKER_START_FAILED"))}});
   child.on("close",()=>{
     clearTimeout(timer);
     if(settled)return;settled=true;
     try{
       const result=JSON.parse(output);
       if(!result||typeof result!=="object"||
         typeof result.status!=="string"||
         !["HOLD_NATIVE_SAVE","READY_FOR_EXACT_RECORD_SAVE_CLICK",
           "NATIVE_SAVE_CREATED_AND_READBACK",
           "UNKNOWN_AFTER_CLICK_RECONCILE_REQUIRED"].includes(result.status))
         throw Error("NATIVE_WORKER_UNEXPECTED_RESPONSE");
       if(result.status==="READY_FOR_EXACT_RECORD_SAVE_CLICK"&&
         (result.salesforce_write!==false||result.save_clicked!==false||
          typeof result.nonce!=="string"||!TOKEN.test(result.nonce)))
         throw Error("UNSAFE_PRECHECK_RESULT");
       if(result.status==="NATIVE_SAVE_CREATED_AND_READBACK"&&
         (result.salesforce_write!==true||result.save_clicked!==true||
          result.crm_writes!==1||
          !/^https:\/\/novogene\.lightning\.force\.com\/lightning\/r\//.test(result.nativeRecordUrl||"")))
         throw Error("INVALID_SAVE_READBACK");
       resolve(result);
     }catch{reject(Error("INVALID_NATIVE_WORKER_OUTPUT"))}
   });
   child.stdin.on("error",()=>{});
   child.stdin.end(JSON.stringify(message));
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
 if(!gate.ok)return block(gate.code,gate.status);
 if(Number(request.headers.get("content-length")||0)>600)return block("REQUEST_TOO_LARGE",413);
 let input;
 try{
   const raw=await request.text();
   if(raw.length>600)throw Error("TOO_BIG");
   input=JSON.parse(raw);
 }catch{return block("NATIVE_SAVE_REQUEST_JSON_INVALID",400)}
 const invalid=validate(input);
 if(invalid)return block(invalid,400);
 if(working)return block("ANOTHER_NATIVE_SAVE_CHECK_OR_COMMIT_RUNNING",409);
 working=true;
 try{
   const result=await execute(input);
   // A failed precheck is actionable HOLD, not a creation.
   return respond({...result,savePermitted:result.status==="READY_FOR_EXACT_RECORD_SAVE_CLICK",
     operatorApprovalRequired:result.status==="READY_FOR_EXACT_RECORD_SAVE_CLICK"});
 }catch{
   // Ambiguous timeout can mean Save was clicked; never report success.
   return respond({status:"UNKNOWN_WORKER_STATE_CHECK_LOCAL_JOURNAL",
     savePermitted:false,save_clicked:"UNKNOWN",salesforce_write:"UNKNOWN",
     automaticRetryAllowed:false},503);
 }finally{working=false}
}
