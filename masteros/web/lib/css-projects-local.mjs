/** Explicitly enabled read-only API on 127.0.0.1. No remote or cross-site requests. */
export function authorizeCssPcRead({enabled,method,host,origin,fetchSite,header}) {
  if (enabled !== true) return {ok:false,status:404,code:"LOCAL_CSS_DISABLED"};
  if (method !== "GET" || !/^127\.0\.0\.1:[0-9]{2,5}$/.test(host??""))
    return {ok:false,status:403,code:"LOOPBACK_ONLY"};
  if (origin && origin!=="http://"+host)
    return {ok:false,status:403,code:"ORIGIN_MISMATCH"};
  if (fetchSite && !["same-origin","none"].includes(fetchSite))
    return {ok:false,status:403,code:"CROSS_SITE_DENIED"};
  if (header!=="1") return {ok:false,status:403,code:"EXPLICIT_HEADER_REQUIRED"};
  return {ok:true,status:200};
}
export function summarizeProjects(payload) {
  if (!payload || typeof payload!=="object" ||
      !["PASS_MIRROR_ONLY","SINK_LAG","STALE","SOURCE_UNAVAILABLE"].includes(payload.status) ||
      !Array.isArray(payload.project_rows) || payload.project_rows.length>1500)
    throw new Error("INVALID_CSS_SNAPSHOT");
  const records=payload.project_rows;
  const ids=new Set();
  for (const row of records) {
    if (!row || typeof row.project_id!=="string" || !row.project_id ||
        ids.has(row.project_id)) throw new Error("INVALID_PROJECT_ID");
    ids.add(row.project_id);
  }
  const stageCounts={};
  for(const r of records) {
    const key=typeof r.stage==="string" && r.stage.trim() ? r.stage.trim() : "UNKNOWN";
    stageCounts[key]=(stageCounts[key]||0)+1;
  }
  return {stageCounts,recordCount:records.length,rows:records};
}
