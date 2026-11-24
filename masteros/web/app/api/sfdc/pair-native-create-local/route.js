/** Operator-laptop-only staged, explicit Opportunity + Quotation Save.
 *
 * Reads the immutable local pending queue. PRECHECK is completely read-only;
 * COMMIT requires a one-time random approval nonce and typed exact digest.
 * The durable "claimed" file is created BEFORE any possible Salesforce click.
 * Any partial/unknown execution is blocked from automatic replay.
 */
import {readFile,lstat,mkdir,writeFile,readdir} from "node:fs/promises";
import {createHash,randomBytes,timingSafeEqual} from "node:crypto";
import {join} from "node:path";
import {spawn} from "node:child_process";
import {authorizeCommand} from "../../../../lib/sfdc-commands.mjs";

export const runtime="nodejs";
export const dynamic="force-dynamic";
const ID=/^OPPOQUOTE-[0-9a-f]{24}$/;
const NONCE=/^[0-9a-f]{48}$/;
const DIGEST=/^PAIR-SAVE-[0-9a-f]{24}$/;
const responseHeaders={"Content-Type":"application/json; charset=utf-8",
 "Cache-Control":"private, no-store,max-age=0",
 "X-Content-Type-Options":"nosniff"};
const respond=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:responseHeaders});
const hold=(code,status=422,extra={})=>respond({status:"HOLD",code,
  salesforceWrite:false,automaticRetryAllowed:false,...extra},status);
let busy=false;
function root(){
 const home=process.env.LOCALAPPDATA;
 if(!home||home.length>400)return null;
 return join(home,"SFDC_Oppo_Quote_Approval_Requests");
}
async function readSafe(path){
 const stat=await lstat(path);
 if(!stat.isFile()||stat.isSymbolicLink()||stat.size<100||stat.size>60000)
   throw Error("QUEUE_FILE_UNSAFE");
 return JSON.parse(await readFile(path,"utf8"));
}
function hash(canonical){
 return "OPPOQUOTE-"+createHash("sha256").update(JSON.stringify(canonical)).digest("hex").slice(0,24);
}
async function getQueue(dir,id){
 if(!ID.test(id))throw Error("INVALID_REQUEST_ID");
 const x=await readSafe(join(dir,id+".json"));
 if(x.requestId!==id||hash(x.canonical)!==id||
    x.state!=="AWAITING_OPERATOR_APPROVAL"||
    x.approved!==false||x.requestedWrite!==false||
    x.status!=="PENDING_APPROVAL"||x.preflight!=="PREVIEW_READY"||
    x.canonical?.review?.verifiedNativeRateForUnchangedAmount!==true||
    x.canonical?.review?.priceChangeRequiresApproval!==false||
    x.canonical?.proposed?.accountMode!=="KEEP"||
    x.canonical?.proposed?.quoteFeeMode!=="EXCLUDE")
   throw Error("QUEUED_REQUEST_NOT_NATIVELY_VERIFIED");
 return x;
}
function worker(canonical,mode,id,dir,approvedPlanDigest=null){
 return new Promise((resolve,reject)=>{
  const py=process.env.SFDC_LOCAL_PYTHON||"python";
  const sub=spawn(py,[join(process.cwd(),"scripts","sfdc_paired_native_create.py")],{
    cwd:process.cwd(),shell:false,windowsHide:true,
    env:{...process.env,PYTHONIOENCODING:"utf-8",PYTHONDONTWRITEBYTECODE:"1",
         SFDC_PAIR_CACHE_ENABLED:"0"},
    stdio:["pipe","pipe","ignore"]
  });
  let out="",done=false;
  const timer=setTimeout(()=>{sub.kill();if(!done){done=true;
    reject(Error("PAIRED_SAVE_EXECUTION_TIMEOUT"))}},mode==="SAVE"?340000:240000);
  sub.stdout.setEncoding("utf8");
  sub.stdout.on("data",s=>{out+=s;if(out.length>15000)sub.kill()});
  sub.on("error",()=>{clearTimeout(timer);if(!done){done=true;reject(Error("PAIRED_WORKER_UNAVAILABLE"))}});
  sub.on("close",()=>{
   clearTimeout(timer);if(done)return;done=true;
   try{
    const r=JSON.parse(out);
    if(!["PREFLIGHT_PASS","PAIR_CREATED_VERIFIED","PARTIAL_RECONCILE_REQUIRED","BLOCK"].includes(r.status))
      throw Error("WORKER_STATUS_INVALID");
    if(mode==="PREFLIGHT"&&r.salesforceWrite!==false)
      throw Error("PREFLIGHT_MUST_NOT_WRITE");
    resolve(r);
   }catch{reject(Error("PAIRED_WORKER_RESPONSE_UNVERIFIED"))}
  });
  sub.stdin.on("error",()=>{});
  sub.stdin.end(JSON.stringify({mode:mode==="SAVE"?"SAVE":"PREFLIGHT",
    canonical,requestId:id,journalPath:join(dir,id+".journal.json"),
    expectedPlanDigest:approvedPlanDigest}));
 })
}
async function status(dir,id){
 let claimed=false,journal=null;
 try{await lstat(join(dir,id+".claim.json"));claimed=true}catch{}
 try{journal=await readSafe(join(dir,id+".journal.json"))}catch{}
 return {status:"STATUS",requestId:id,claimed,
    journalState:journal?.state||"NOT_STARTED",
    opportunityId:journal?.createdOpportunityId||null,
    quoteId:journal?.createdQuoteId||null,
    code:journal?.code||null,automaticRetryAllowed:false};
}
export async function POST(request){
 const auth=authorizeCommand({
  enabled:process.env.SFDC_LOCAL_COMMAND_ENABLED==="1",
  method:request.method,host:request.headers.get("host"),
  origin:request.headers.get("origin"),
  fetchSite:request.headers.get("sec-fetch-site"),
  header:request.headers.get("x-sfdc-command"),
  contentType:request.headers.get("content-type")
 });
 if(!auth.ok)return hold(auth.code,auth.status||403);
 if(Number(request.headers.get("content-length")||0)>800)return hold("REQUEST_TOO_LARGE",413);
 let input;
 try{
  const raw=await request.text();
  if(raw.length>800)throw Error("SIZE");
  input=JSON.parse(raw);
  if(!input||typeof input!=="object"||Array.isArray(input)||
      Object.keys(input).some(k=>!["mode","requestId","nonce","approvalDigest","confirmation","duplicateConfirmed"].includes(k))||
      !["PRECHECK","COMMIT","STATUS"].includes(input.mode)||!ID.test(input.requestId))
    throw Error("INVALID");
 }catch{return hold("PAIRED_SAVE_REQUEST_INVALID",400)}
 const dir=root();
 if(!dir)return hold("PRIVATE_LAPTOP_QUEUE_NOT_AVAILABLE",503);
 if(input.mode==="STATUS")return respond(await status(dir,input.requestId));
 if(busy)return hold("PAIRED_SAVE_BUSY",409);
 busy=true;
 try{
  const queue=await getQueue(dir,input.requestId);
  const state=await status(dir,input.requestId);
  if(state.claimed||state.journalState!=="NOT_STARTED")
    return hold("EXISTING_WRITE_MUST_BE_RECONCILED",409,state);
  if(input.mode==="PRECHECK"){
    const check=await worker(queue.canonical,"PREFLIGHT",input.requestId,dir);
    if(check.status!=="PREFLIGHT_PASS")return hold(check.code||"SOURCE_PREFLIGHT_UNVERIFIED",422);
    if(!/^MATRIX-[0-9a-f]{24}$/.test(check.planDigest||""))
      return hold("SOURCE_PROCESS_MATRIX_DIGEST_MISSING",422);
    const digest="PAIR-SAVE-"+createHash("sha256")
      .update(JSON.stringify(queue.canonical)+"|"+JSON.stringify({
        net:check.expectedNetKrw,gross:check.expectedGrossKrw,
        samples:check.samples,gb:check.gbPerSample,
        cloud:check.cloudUnits,processes:check.processCount,
        exactProcessMatrix:check.planDigest
      })).digest("hex").slice(0,24);
    const nonce=randomBytes(24).toString("hex");
    const session={requestId:input.requestId,
      approvalDigest:digest,tokenHash:createHash("sha256").update(nonce).digest("hex"),
      createdAt:Date.now(),used:false,
      canonicalId:hash(queue.canonical),
      exactProcessMatrix:check.planDigest};
    const path=join(dir,input.requestId+".paired-session.json");
    await writeFile(path,JSON.stringify(session),{encoding:"utf8",mode:0o600});
    return respond({...check,status:"READY_FOR_OPERATOR_APPROVAL",
      requestId:input.requestId,approvalDigest:digest,nonce,
      typedConfirmation:"CREATE "+digest.slice(-8),
      approvalRequired:true,savePermitted:false,previewOnly:true,
      partialQuoteRisk:"QUOTE_HEADER_SAVED_BEFORE_PRODUCT_PRICE_VERIFICATION"});
  }
  if(process.env.SFDC_PAIR_NATIVE_SAVE_ENABLED!=="1")
    return hold("LAPTOP_NATIVE_WRITE_NOT_ENABLED",403);
  // A current Salesforce list-view search is not an exhaustive org-level
  // duplicate check. The operator must attest to an independent review of
  // Account/Contact/name duplicates for the exact new request.
  if(input.duplicateConfirmed!==true)
    return hold("EXPLICIT_DUPLICATE_REVIEW_REQUIRED",403);
  const session=await readSafe(join(dir,input.requestId+".paired-session.json"));
  const checkToken=NONCE.test(input.nonce||"")&&
    session.tokenHash===createHash("sha256").update(input.nonce).digest("hex");
  const tokenA=Buffer.from(session.tokenHash||"");
  const tokenB=Buffer.from(createHash("sha256").update(input.nonce||"").digest("hex"));
  const safeToken=checkToken&&tokenA.length===tokenB.length&&timingSafeEqual(tokenA,tokenB);
  if(!safeToken||session.used!==false||session.requestId!==input.requestId||
     session.canonicalId!==hash(queue.canonical)||
     !/^MATRIX-[0-9a-f]{24}$/.test(session.exactProcessMatrix||"")||
     !DIGEST.test(session.approvalDigest)||
     input.approvalDigest!==session.approvalDigest||
     input.confirmation!=="CREATE "+session.approvalDigest.slice(-8)||
     !Number.isFinite(session.createdAt)||Date.now()-session.createdAt>180000||
     Date.now()-session.createdAt<0)
    return hold("EXACT_RECORD_APPROVAL_EXPIRED_OR_INVALID",403);
  await writeFile(join(dir,input.requestId+".paired-session.json"),
    JSON.stringify({...session,used:true}),{encoding:"utf8",mode:0o600});
  // Exclusive cross-process replay barrier, written BEFORE launching any
  // browser code that can click Salesforce Save. Do not clear after a partial.
  await writeFile(join(dir,input.requestId+".claim.json"),
    JSON.stringify({requestId:input.requestId,
      approvedDigest:session.approvalDigest,startedAtUtc:new Date().toISOString(),
      state:"EXECUTION_CLAIMED_NO_AUTOMATIC_RETRY"}),{
       flag:"wx",encoding:"utf8",mode:0o600});
  const outcome=await worker(queue.canonical,"SAVE",input.requestId,dir,
    session.exactProcessMatrix);
  return respond({...outcome,requestId:input.requestId,
    claimRetained:true,automaticRetryAllowed:false});
 }catch(e){
  const code=String(e?.message||"");
  return hold(code==="EEXIST"?"SAVE_ALREADY_CLAIMED_NO_RETRY":
    code==="PAIRED_SAVE_EXECUTION_TIMEOUT"?"UNKNOWN_AFTER_SAVE_ATTEMPT_RECONCILE":
    "PAIRED_SAVE_UNAVAILABLE",503);
 }finally{busy=false}
}
