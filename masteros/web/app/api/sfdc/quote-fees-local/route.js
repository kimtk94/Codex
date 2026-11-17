/** Authenticated localhost SFDC Quote Fee GET-only evidence, not a Quote writer. */
import {spawn} from "node:child_process";
import {join} from "node:path";
import {authorizeCommand} from "../../../../lib/sfdc-commands.mjs";

export const runtime="nodejs";
export const dynamic="force-dynamic";
const HEADERS={"Content-Type":"application/json; charset=utf-8",
  "Cache-Control":"private, no-store,max-age=0",
  "X-Content-Type-Options":"nosniff","Vary":"Origin,Host,Sec-Fetch-Site"};
const reply=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:HEADERS});
const fail=(code,status=422)=>reply({status:"HOLD",code,salesforce_write:false,
  save_permitted:false},status);
let inFlight=null;

function readOnlySource(quoteId){
  return new Promise((resolve,reject)=>{
    const child=spawn(process.env.SFDC_LOCAL_PYTHON||"python",
      [join(process.cwd(),"scripts","sfdc_quote_fee_source.py")],{
        cwd:process.cwd(),shell:false,windowsHide:true,
        env:{...process.env,PYTHONIOENCODING:"utf-8",PYTHONDONTWRITEBYTECODE:"1"},
        stdio:["pipe","pipe","ignore"]});
    let finished=false,output="";
    const timer=setTimeout(()=>{
      child.kill();if(!finished){finished=true;reject(Error("FEE_SOURCE_TIMEOUT"))}
    },30000);
    child.stdout.setEncoding("utf8");
    child.stdout.on("data",chunk=>{output+=chunk;if(output.length>25000)child.kill()});
    child.on("error",()=>{
      clearTimeout(timer);if(!finished){finished=true;reject(Error("FEE_WORKER_FAILED"))}
    });
    child.on("close",()=>{
      clearTimeout(timer);if(finished)return;
      finished=true;
      try{
        const data=JSON.parse(output);
        if(!["PASS","HOLD"].includes(data?.status)||
           data.salesforce_write!==false||data.save_permitted!==false||
           (data.status==="PASS"&&(
             data.source!=="LIVE_SALESFORCE_READ_ONLY"||
             data.nativeQuoteId!==quoteId||!Array.isArray(data.feeLines)||
             data.feeLines.length>100||
             data.feeCount!==data.feeLines.length||
             !Number.isSafeInteger(data.totalFeeKrw))))
          throw Error("INVALID_FEE_SOURCE_REPLY");
        resolve(data);
      }catch{reject(Error("INVALID_FEE_SOURCE_REPLY"));}
    });
    child.stdin.end(JSON.stringify({sourceQuoteId:quoteId}));
  });
}
export async function POST(request){
  const gate=authorizeCommand({
    enabled:process.env.SFDC_LOCAL_COMMAND_ENABLED==="1",
    method:request.method,host:request.headers.get("host"),
    origin:request.headers.get("origin"),fetchSite:request.headers.get("sec-fetch-site"),
    header:request.headers.get("x-sfdc-command"),
    contentType:request.headers.get("content-type")
  });
  if(!gate.ok)return fail(gate.code,gate.status);
  if(Number(request.headers.get("content-length")||0)>180)
    return fail("FEE_REQUEST_TOO_LARGE",413);
  let input;
  try{
    const raw=await request.text();
    if(raw.length>180)throw Error("TOO_LARGE");
    input=JSON.parse(raw);
    if(!input||Array.isArray(input)||Object.keys(input).length!==2||
       input.mode!=="READ_SOURCE_QUOTE_FEES"||
       !/^a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/.test(input.sourceQuoteId))
      throw Error("INVALID_INPUT");
  }catch{return fail("FEE_REQUEST_INVALID",400)}
  // React StrictMode and repeated UI selection may issue the same
  // authenticated read in parallel. Share its single GET-only source proof.
  // Never mix two different source Quote IDs within one pending read.
  if(inFlight&&inFlight.quoteId!==input.sourceQuoteId)
    return fail("FEE_READ_OTHER_QUOTE_BUSY",409);
  if(!inFlight)inFlight={
    quoteId:input.sourceQuoteId,
    promise:readOnlySource(input.sourceQuoteId)
  };
  const current=inFlight;
  try{
    const evidence=await current.promise;
    return reply(evidence,evidence.status==="PASS"?200:422);
  }catch{return fail("FEE_SFDC_SOURCE_UNAVAILABLE",503)}
  finally{if(inFlight===current)inFlight=null}
}
