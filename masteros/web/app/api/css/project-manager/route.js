import {execFile} from "node:child_process";
import {join} from "node:path";
import {promisify} from "node:util";
import {authorizeCssPcRead} from "../../../../lib/css-projects-local.mjs";
import {validateProjectManager} from "../../../../lib/css-project-manager.mjs";

export const runtime="nodejs";
export const dynamic="force-dynamic";
const run=promisify(execFile);
const headers={
  "Content-Type":"application/json; charset=utf-8",
  "Cache-Control":"private, no-store, max-age=0",
  "X-Content-Type-Options":"nosniff",
  "Vary":"Origin, Host, Sec-Fetch-Site",
};
const send=(value,status=200)=>new Response(JSON.stringify(value),{status,headers});

export async function GET(request) {
  const access=authorizeCssPcRead({
    enabled:process.env.CSS_LOCAL_PROJECTS_ENABLED==="1",
    method:request.method,
    host:request.headers.get("host"),
    origin:request.headers.get("origin"),
    fetchSite:request.headers.get("sec-fetch-site"),
    header:request.headers.get("x-css-local-projects"),
  });
  if(!access.ok)return send({status:"BLOCK",reason:access.code},access.status);
  try {
    const script=join(process.cwd(),"scripts","css_project_manager_local.py");
    const {stdout}=await run(process.env.CSS_LOCAL_PYTHON||"python",[script],{
      timeout:90000,maxBuffer:4_000_000,windowsHide:true,
      env:{...process.env,PYTHONIOENCODING:"utf-8",PYTHONDONTWRITEBYTECODE:"1"}
    });
    const payload=JSON.parse(stdout);
    if(payload.status==="SOURCE_UNAVAILABLE")
      return send({status:"SOURCE_UNAVAILABLE",reason:payload.error_type||"SOURCE_UNAVAILABLE"},503);
    return send(validateProjectManager(payload));
  }catch {
    return send({status:"SOURCE_UNAVAILABLE",reason:"LOCAL_PROJECT_READ_FAILED"},503);
  }
}
