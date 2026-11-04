import { readFile, stat } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { authorizePcLocalLookup } from "../../../../lib/sfdc-local-pc-gate.mjs";
import { parseLocalContacts, lookupLocalContacts } from "../../../../lib/sfdc-contact-local.mjs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = {
  "Cache-Control": "no-store, max-age=0",
  "X-Content-Type-Options": "nosniff",
  "Vary": "Origin, Sec-Fetch-Site, Host",
};

function reply(body, status=200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {...headers,"Content-Type":"application/json; charset=utf-8"},
  });
}

/** No CRM connection. Only reads the authenticated workstation's existing
 * private vetted snapshot after a same-origin user action on loopback.
 * Disabled on Vercel and on other hosts unless intentionally configured.
 */
export async function GET(request) {
  const url = new URL(request.url);
  const permission = authorizePcLocalLookup({
    enabled: process.env.SFDC_LOCAL_CONTACT_LOOKUP_ENABLED === "1",
    method: request.method,
    host: request.headers.get("host"),
    origin: request.headers.get("origin"),
    fetchSite: request.headers.get("sec-fetch-site"),
    localHeader: request.headers.get("x-sfdc-local-preview"),
    name: url.searchParams.get("name"),
  });
  if (!permission.ok) {
    return reply({status:"HOLD",code:permission.code},permission.status);
  }
  try {
    const source=join(homedir(),".sfdc_desktop","web_contact_aliases_PRIVATE.json");
    const metadata=await stat(source);
    if (!metadata.isFile() || metadata.size>2_000_000) {
      return reply({status:"HOLD",code:"PRIVATE_CONTACT_SOURCE_INVALID"},503);
    }
    const contacts=parseLocalContacts(await readFile(source,"utf8"));
    const selected=lookupLocalContacts(permission.name,contacts);
    return reply({
      status:"LOCAL_VERIFIED_SNAPSHOT_NOT_LIVE_SALESFORCE",
      name:permission.name,
      candidates:selected,
      count:selected.length,
      salesforce_save_allowed:false,
    });
  } catch {
    // Never expose local file paths, customer details, or auth material in errors.
    return reply({status:"HOLD",code:"PRIVATE_CONTACT_SOURCE_UNAVAILABLE"},503);
  }
}
