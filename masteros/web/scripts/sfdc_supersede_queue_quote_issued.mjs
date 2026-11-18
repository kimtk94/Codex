/** Operator-laptop only: supersede ONE immutable Quote Draft request.
 *
 * The original request remains byte-identical. New request is NEEDS_REVIEW
 * with Quote Issued wording, no approval, no native Salesforce Save.
 * Run: node scripts/sfdc_supersede_queue_quote_issued.mjs OPPOQUOTE-<24 hex>
 */
import {readFile,writeFile,mkdir} from "node:fs/promises";
import {join} from "node:path";
import {supersedeQueueQuoteDraft} from "../lib/sfdc-queue-issued-supersession.mjs";

async function main(){
 const id=process.argv[2],home=process.env.LOCALAPPDATA;
 if(!home||!/^OPPOQUOTE-[a-f0-9]{24}$/.test(id||""))
   throw Error("LOCALAPPDATA_OR_REQUEST_ID_REQUIRED");
 const dir=join(home,"SFDC_Oppo_Quote_Approval_Requests");
 const oldFile=join(dir,id+".json");
 const oldText=await readFile(oldFile,"utf8");
 if(Buffer.byteLength(oldText)>75000)throw Error("SOURCE_QUEUE_TOO_LARGE");
 const old=JSON.parse(oldText);
 const next=supersedeQueueQuoteDraft(old,id);
 if(!next.ok)throw Error(next.code);
 await mkdir(dir,{recursive:true});
 const path=join(dir,next.requestId+".json");
 try{
  await writeFile(path,JSON.stringify(next.newQueue,null,2),{
   flag:"wx",encoding:"utf8",mode:0o600
  });
 }catch(e){
  if(e?.code!=="EEXIST")throw e;
  const existing=JSON.parse(await readFile(path,"utf8"));
  if(existing.requestId!==next.requestId||
    existing.supersedesRequestId!==id||
    JSON.stringify(existing.canonical)!==JSON.stringify(next.newQueue.canonical)||
    existing.approved!==false||existing.salesforceWrite!==false)
    throw Error("EXISTING_REISSUE_COLLISION");
 }
 // Verify source unchanged; caller must never mutate its immutable bytes.
 if(await readFile(oldFile,"utf8")!==oldText)
  throw Error("ORIGINAL_QUEUE_CHANGED_EXTERNALLY");
 console.log(JSON.stringify({status:"QUOTE_ISSUED_REQUEST_SUPERSEDED_NO_SAVE",
  requestId:next.requestId,sourceRequestId:id,
  quoteStatus:"NEEDS_REVIEW",originalPreserved:true,
  salesforceWrite:false,crmWrites:0}));
}
main().catch(e=>{
 console.error(e?.message||"LOCAL_REISSUE_FAILED");
 process.exitCode=1;
});
