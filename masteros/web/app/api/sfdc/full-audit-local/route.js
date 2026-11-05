import { readFile,stat } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { authorizeAuditRead,projectPrivateAudit } from "../../../../lib/sfdc-local-audit.mjs";

export const runtime="nodejs";
export const dynamic="force-dynamic";
const headers={
  "Cache-Control":"no-store, max-age=0",
  "X-Content-Type-Options":"nosniff",
  "Vary":"Origin, Sec-Fetch-Site, Host",
};
const reply=(payload,status=200)=>new Response(JSON.stringify(payload),{
  status,headers:{...headers,"Content-Type":"application/json; charset=utf-8"},
});

async function privateObject(directory,name) {
  const file=join(directory,name);
  const info=await stat(file);
  if(!info.isFile() || info.size>5_000_000)throw new Error("PRIVATE_AUDIT_UNAVAILABLE");
  return JSON.parse(await readFile(file,"utf8"));
}

/** Strictly read-only workstation metrics.
 * There is no Salesforce API, no CRM write, no customer identifier in result.
 * The environment gate is disabled on all hosted Vercel deployments.
 */
export async function GET(request) {
  const permission=authorizeAuditRead({
    enabled:process.env.SFDC_LOCAL_CONTACT_LOOKUP_ENABLED==="1",
    platform:process.platform,
    method:request.method,
    host:request.headers.get("host"),
    origin:request.headers.get("origin"),
    fetchSite:request.headers.get("sec-fetch-site"),
    header:request.headers.get("x-sfdc-local-preview"),
  });
  if(!permission.ok)return reply({status:"HOLD",code:permission.code},permission.status);
  try {
    const privateRoot=join(homedir(),".sfdc_desktop");
    const [full,opportunities,shortlist,nativeRows,aliases,progress]=await Promise.all([
      privateObject(privateRoot,"full_oppo_quote_snapshot_reconciliation_PRIVATE.json"),
      privateObject(privateRoot,"all_opportunity_contact_reconciliation_PRIVATE.json"),
      privateObject(privateRoot,"one_to_one_oppo_quote_learning_shortlist_PRIVATE.json"),
      privateObject(privateRoot,"one_to_one_quote_native_parent_verified_PRIVATE.json"),
      privateObject(privateRoot,"web_contact_aliases_PRIVATE.json"),
      privateObject(privateRoot,"expanded_contact_cohort_progress_PRIVATE.json"),
    ]);
    const metrics=projectPrivateAudit(full,opportunities,shortlist,nativeRows,aliases,progress);
    return reply({status:"LOCAL_AGGREGATE_ONLY_NO_SAVE",metrics});
  } catch {
    return reply({status:"HOLD",code:"LOCAL_PRIVATE_AUDIT_NOT_READY"},503);
  }
}
