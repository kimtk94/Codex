import { execFile } from "node:child_process";
import { join } from "node:path";
import { promisify } from "node:util";
import { authorizeCssPcRead, summarizeProjects } from "../../../../lib/css-projects-local.mjs";

export const runtime="nodejs";
export const dynamic="force-dynamic";
const execute=promisify(execFile);
const headers={
  "Content-Type":"application/json; charset=utf-8",
  "Cache-Control":"private, no-store, max-age=0",
  "X-Content-Type-Options":"nosniff",
  "Vary":"Origin, Host, Sec-Fetch-Site",
};
const send=(body,status=200)=>new Response(JSON.stringify(body),{status,headers});

export async function GET(request){
  const auth=authorizeCssPcRead({
    enabled:process.env.CSS_LOCAL_PROJECTS_ENABLED==="1",
    method:request.method,
    host:request.headers.get("host"),
    origin:request.headers.get("origin"),
    fetchSite:request.headers.get("sec-fetch-site"),
    header:request.headers.get("x-css-local-projects"),
  });
  if(!auth.ok) return send({status:"BLOCK",reason:auth.code},auth.status);
  try {
    const script=join(process.cwd(),"scripts","css_projects_local.py");
    const python=process.env.CSS_LOCAL_PYTHON || "python";
    const {stdout}=await execute(python,[script],{
      timeout:45000,maxBuffer:2_000_000,windowsHide:true,
      env:{...process.env,PYTHONIOENCODING:"utf-8",PYTHONDONTWRITEBYTECODE:"1"},
    });
    const payload=JSON.parse(stdout);
    const summary=summarizeProjects(payload);
    if(payload.status==="SOURCE_UNAVAILABLE")
      return send({status:"SOURCE_UNAVAILABLE",reason:payload.error_type||"SOURCE_READ_FAILED",records:[]},503);
    return send({...payload,project_rows:summary.rows,stage_counts:summary.stageCounts,
      displayed_count:summary.recordCount});
  } catch {
    // Hide local filesystem paths, Python stderr, customer and authentication details.
    return send({status:"SOURCE_UNAVAILABLE",reason:"LOCAL_READBACK_FAILED",records:[]},503);
  }
}
