import { spawn } from "node:child_process";
import { mkdtemp, writeFile, rm, stat } from "node:fs/promises";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { authorizePcReadOnlyReview } from "../../../../lib/sfdc-local-review-gate.mjs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

let reviewActive = false;
const headers = {
  "Cache-Control":"no-store, max-age=0",
  "X-Content-Type-Options":"nosniff",
  "Vary":"Origin, Sec-Fetch-Site, Host",
};
const reply=(body,status=200)=>new Response(JSON.stringify(body),{
  status,
  headers:{...headers,"Content-Type":"application/json; charset=utf-8"},
});

function runPrivateReview(script, packetFile) {
  return new Promise(resolveResult=>{
    let child;
    let buffer="";
    let finalized=false;
    const finish=out=>{
      if(finalized)return;
      finalized=true;
      clearTimeout(timer);
      resolveResult(out);
    };
    try {
      child=spawn("py",["-3.12",script,"--packet",packetFile,"--live-readonly"],{
        cwd:resolve(process.cwd(),"..",".."),
        shell:false,
        windowsHide:true,
        stdio:["ignore","pipe","ignore"],
      });
    } catch {
      resolveResult({ok:false,code:"LOCAL_PYTHON_LAUNCH_FAILED"});
      return;
    }
    const timer=setTimeout(()=>{
      child.kill();
      finish({ok:false,code:"LOCAL_READBACK_TIMEOUT"});
    },100000);
    child.stdout.on("data",data=>{
      if(buffer.length>8192){
        child.kill();
        finish({ok:false,code:"LOCAL_READBACK_TOO_LARGE"});
        return;
      }
      buffer+=String(data);
    });
    child.on("error",()=>finish({ok:false,code:"LOCAL_PYTHON_UNAVAILABLE"}));
    child.on("close",code=>{
      if(code!==0){
        finish({ok:false,code:"LOCAL_IDENTITY_REVIEW_HOLD"});
        return;
      }
      try {
        const parsed=JSON.parse(buffer.trim());
        const live=parsed?.live_readback;
        const matched=parsed?.matched_private_roster===true
          && parsed?.save_allowed===false
          && live?.save_allowed===false;
        finish({
          ok:matched,
          code:matched ? "READ_ONLY_REVIEW_COMPLETE":"LOCAL_REVIEW_HOLD",
          local_roster_matched:parsed.matched_private_roster===true,
          live_identity_verified:matched && live?.live_identity_verified===true,
          live_status:typeof live?.status==="string" ? live.status:"HOLD_UNVERIFIED",
          save_allowed:false,
          price_verified:false,
          quote_duplicate_check_complete:false,
        });
      } catch {
        finish({ok:false,code:"LOCAL_REVIEW_RESPONSE_INVALID"});
      }
    });
  });
}

/** A POST does not write Salesforce. It transfers a strict, no-save JSON
 * request only to a local Python validator, which reads the authorized Chrome.
 * It is disabled by default and never available on hosted Vercel deployments.
 */
export async function POST(request) {
  const permitted=authorizePcReadOnlyReview({
    enabled:process.env.SFDC_LOCAL_CONTACT_LOOKUP_ENABLED==="1",
    platform:process.platform,
    method:request.method,
    host:request.headers.get("host"),
    origin:request.headers.get("origin"),
    fetchSite:request.headers.get("sec-fetch-site"),
    localHeader:request.headers.get("x-sfdc-local-preview"),
    contentType:request.headers.get("content-type"),
  });
  if(!permitted.ok)return reply({status:"HOLD",code:permitted.code},permitted.status);
  if(reviewActive)return reply({status:"HOLD",code:"LOCAL_REVIEW_ALREADY_RUNNING"},409);
  const lengthHeader=request.headers.get("content-length");
  if(lengthHeader && (!/^\d+$/.test(lengthHeader) || Number(lengthHeader)>250000))
    return reply({status:"HOLD",code:"REVIEW_PACKET_TOO_LARGE"},413);
  reviewActive=true;
  let tmp;
  try {
    const raw=await request.text();
    if(Buffer.byteLength(raw,"utf8")>250000)
      return reply({status:"HOLD",code:"REVIEW_PACKET_TOO_LARGE"},413);
    let packet;
    try {packet=JSON.parse(raw)} catch {
      return reply({status:"HOLD",code:"REVIEW_PACKET_JSON_INVALID"},400);
    }
    if(!packet || typeof packet!=="object" || Array.isArray(packet))
      return reply({status:"HOLD",code:"REVIEW_PACKET_SCHEMA_INVALID"},400);
    const root=join(homedir(),".sfdc_desktop");
    const directory=await stat(root);
    if(!directory.isDirectory())
      return reply({status:"HOLD",code:"LOCAL_PRIVATE_ROSTER_UNAVAILABLE"},503);
    const script=resolve(process.cwd(),"..","..","automation","sfdc_desktop",
      "validate_web_contact_review_packet.py");
    await stat(script);
    tmp=await mkdtemp(join(root,"web_review_"));
    const packetFile=join(tmp,"review.json");
    await writeFile(packetFile,JSON.stringify(packet),"utf8");
    const result=await runPrivateReview(script,packetFile);
    if(!result.ok)return reply({status:"HOLD",code:result.code},409);
    return reply({
      status:result.live_identity_verified?"LIVE_CONTACT_IDENTITY_CONFIRMED_NO_SAVE":"HOLD_LIVE_IDENTITY",
      live_identity_verified:result.live_identity_verified,
      local_roster_matched:result.local_roster_matched,
      save_allowed:false,
      price_verified:false,
      quote_duplicate_check_complete:false,
    },result.live_identity_verified?200:409);
  } catch {
    // Never return customer data, local paths or internal exception details.
    return reply({status:"HOLD",code:"LOCAL_REVIEW_UNAVAILABLE"},503);
  } finally {
    if(tmp)await rm(tmp,{recursive:true,force:true}).catch(()=>{});
    reviewActive=false;
  }
}
