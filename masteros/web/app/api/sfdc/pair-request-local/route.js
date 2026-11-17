import {mkdir,writeFile} from "node:fs/promises";
import {join} from "node:path";
import {authorizeCommand} from "../../../../lib/sfdc-commands.mjs";
import {validatePairRequest} from "../../../../lib/sfdc-pair-request-queue.mjs";

export const runtime="nodejs";
export const dynamic="force-dynamic";
const headers={"Content-Type":"application/json; charset=utf-8",
 "Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"};
const respond=(value,status=200)=>new Response(JSON.stringify(value),{status,headers});
const blocked=(code)=>respond({status:"BLOCK",code,salesforce_write:false},403);

export async function POST(request){
 const auth=authorizeCommand({
   enabled:process.env.SFDC_LOCAL_COMMAND_ENABLED==="1",
   method:request.method,host:request.headers.get("host"),
   origin:request.headers.get("origin"),
   fetchSite:request.headers.get("sec-fetch-site"),
   header:request.headers.get("x-sfdc-command"),
   contentType:request.headers.get("content-type")
 });
 if(!auth.ok)return blocked(auth.code);
 if(Number(request.headers.get("content-length")||0)>35000)
   return respond({status:"BLOCK",code:"REQUEST_TOO_LARGE"},413);
 let input;
 try{
   const raw=await request.text();
   if(raw.length>35000)throw Error("OVERSIZED");
   input=JSON.parse(raw);
 }catch{return respond({status:"BLOCK",code:"INVALID_REQUEST_JSON"},400)}
 const validation=validatePairRequest(input);
 if(!validation.ok)return respond({status:"BLOCK",code:validation.code},422);
 // Do not write to the Feishu/SFDC remote queue: the operator has not
 // approved a real CRM transaction. Local staged requests only.
 const home=process.env.LOCALAPPDATA;
 if(!home||typeof home!=="string"||home.length>400)
   return respond({status:"BLOCK",code:"LOCAL_QUEUE_UNAVAILABLE"},503);
 const directory=join(home,"SFDC_Oppo_Quote_Approval_Requests");
 const filepath=join(directory,validation.requestId+".json");
 try{
   await mkdir(directory,{recursive:true});
   const entry={...validation,receivedAtUtc:new Date().toISOString(),
     requestType:"OPPO_QUOTE_PAIRED_CREATE",
     state:"AWAITING_OPERATOR_APPROVAL",
     approved:false,requestedWrite:false};
   await writeFile(filepath,JSON.stringify(entry,null,2),{
     encoding:"utf8",flag:"wx",mode:0o600
   });
   return respond({status:validation.status,requestId:validation.requestId,
     approvalRequired:true,savePermitted:false,salesforceWrite:false,
     preflight:validation.preflight,missing:validation.missing,
     location:"PRIVATE_OPERATOR_PC_QUEUE",created:true});
 }catch(error){
   if(error?.code==="EEXIST")
     return respond({status:validation.status,requestId:validation.requestId,
       approvalRequired:true,savePermitted:false,salesforceWrite:false,
       preflight:validation.preflight,missing:validation.missing,
       location:"PRIVATE_OPERATOR_PC_QUEUE",created:false,alreadyQueued:true});
   return respond({status:"BLOCK",code:"LOCAL_REQUEST_STORAGE_FAILED",
     salesforceWrite:false},503);
 }
}
