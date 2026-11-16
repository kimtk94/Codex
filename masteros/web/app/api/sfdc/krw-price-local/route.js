import {lstat,readFile} from "node:fs/promises";
import {join} from "node:path";
import {authorizeCommand} from "../../../../lib/sfdc-commands.mjs";
import {parseKrwEvidence} from "../../../../lib/sfdc-2026-krw-price-preview.mjs";

export const runtime="nodejs";
export const dynamic="force-dynamic";
const headers={
 "Content-Type":"application/json; charset=utf-8",
 "Cache-Control":"private, no-store, max-age=0",
 "X-Content-Type-Options":"nosniff",
 "Vary":"Origin,Host,Sec-Fetch-Site"
};
const send=(v,status=200)=>new Response(JSON.stringify(v),{status,headers});
const block=(code)=>({status:"BLOCK",code,local_only:true,salesforce_write:false});

export async function POST(request){
 const gate=authorizeCommand({
  enabled:process.env.SFDC_KRW_PRICE_LOCAL_READ_ENABLED==="1",
  method:request.method,
  host:request.headers.get("host"),origin:request.headers.get("origin"),
  fetchSite:request.headers.get("sec-fetch-site"),
  header:request.headers.get("x-sfdc-command"),
  contentType:request.headers.get("content-type")
 });
 if(!gate.ok)return send(block(gate.code),gate.status);
 if(Number(request.headers.get("content-length")||0)>100)
  return send(block("REQUEST_TOO_LARGE"),413);
 let req;
 try{
  const raw=await request.text();
  if(!raw||raw.length>100)throw Error("BAD_LENGTH");
  req=JSON.parse(raw);
  if(!req||Array.isArray(req)||Object.keys(req).length!==1||
     req.mode!=="READ_LOCAL_PRIVATE_2026_KRW")
    throw Error("BAD_MODE");
 }catch{return send(block("INVALID_LOCAL_PRICE_REQUEST"),400)}
 const home=process.env.LOCALAPPDATA;
 if(!home||typeof home!=="string")return send(block("PRIVATE_KRW_INDEX_UNAVAILABLE"),503);
 const file=join(home,"SFDC_KRW_Price","2026_krw_process_prices_verified_local.json");
 try{
  const stat=await lstat(file);
  if(!stat.isFile()||stat.isSymbolicLink()||stat.size<100||stat.size>2*1024*1024)
    throw Error("SOURCE_FILE_UNSAFE");
  const raw=await readFile(file,"utf8");
  if(raw.length>2*1024*1024)throw Error("SOURCE_TOO_LARGE");
  const checked=parseKrwEvidence(raw);
  const original=JSON.parse(raw);
  if(!checked.records.length||checked.records.length!==original.records.length)
    throw Error("PRICE_LINES_REJECTED");
  return send({status:"PASS",local_only:true,salesforce_write:false,
   evidence:original,verified_process_rows:checked.records.length,
   verified_quote_count:new Set(checked.records.map(x=>x.quote_id)).size});
 }catch{
  return send(block("PRIVATE_KRW_INDEX_STALE_OR_INVALID"),503);
 }
}
