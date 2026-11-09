import {spawn} from "node:child_process";
import {join} from "node:path";
import {authorizeCommand} from "../../../../lib/sfdc-commands.mjs";
import {validRecordPickerRequest} from "../../../../lib/sfdc-record-picker.mjs";

export const runtime="nodejs";
export const dynamic="force-dynamic";
let running=false;
const headers={"Content-Type":"application/json; charset=utf-8",
  "Cache-Control":"no-store, private, max-age=0",
  "X-Content-Type-Options":"nosniff",
  "Vary":"Origin, Host, Sec-Fetch-Site"};
const send=(payload,status=200)=>new Response(JSON.stringify(payload),{status,headers});

function launch(input){
  return new Promise((resolve,reject)=>{
    const python=process.env.SFDC_LOCAL_PYTHON||"python";
    const child=spawn(python,[join(process.cwd(),"scripts","sfdc_record_catalog.py")],{
      cwd:process.cwd(),shell:false,windowsHide:true,
      env:{...process.env,PYTHONIOENCODING:"utf-8",PYTHONDONTWRITEBYTECODE:"1"},
      stdio:["pipe","pipe","ignore"]
    });
    let done=false,body="";
    const timer=setTimeout(()=>{
      child.kill();
      if(!done){done=true;reject(Error("SFDC_LIST_TIMEOUT"))}
    },85000);
    child.stdout.setEncoding("utf8");
    child.stdout.on("data",part=>{body+=part; if(body.length>100000)child.kill()});
    child.on("error",()=>{clearTimeout(timer);if(!done){done=true;reject(Error("SFDC_SUBPROCESS_FAILED"));}});
    child.on("close",()=>{
      clearTimeout(timer);if(done)return;
      done=true;
      try{
        const output=JSON.parse(body);
        if(!["PASS","BLOCK"].includes(output?.status))throw Error("OUTPUT_INVALID");
        if(output.records&&(!Array.isArray(output.records)||output.records.length>30))
          throw Error("RESULT_SIZE_INVALID");
        resolve(output);
      }catch{reject(Error("SFDC_RESULT_INVALID"));}
    });
    child.stdin.end(JSON.stringify(input));
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
  if(!gate.ok)return send({status:"BLOCK",code:gate.code},gate.status);
  if(running)return send({status:"BLOCK",code:"PICKER_BUSY"},409);
  if(Number(request.headers.get("content-length")||0)>2500)
    return send({status:"BLOCK",code:"BODY_TOO_LARGE"},413);
  let data;
  try{
    const raw=await request.text();
    if(raw.length>2500)throw Error("BODY_TOO_LARGE");
    data=JSON.parse(raw);
  }catch{return send({status:"BLOCK",code:"INVALID_JSON"},400)}
  const check=validRecordPickerRequest(data);
  if(!check.ok)return send({status:"BLOCK",code:check.code},400);
  running=true;
  try{
    const output=await launch(data);
    return send(output,output.status==="PASS"?200:422);
  }catch{
    return send({status:"BLOCK",code:"SFDC_SOURCE_UNAVAILABLE"},503);
  }finally{running=false}
}
