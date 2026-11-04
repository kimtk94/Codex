/** Explicit opt-in for an authenticated workstation's read-only Salesforce
 * preflight. Cannot run on Vercel, remote addresses, or cross-site requests.
 */
export function authorizePcReadOnlyReview({
  enabled, platform, method, host, origin, fetchSite, localHeader, contentType
}) {
  if (enabled !== true || platform !== "win32") {
    return { ok:false, code:"LOCAL_REVIEW_DISABLED", status:404 };
  }
  if (method !== "POST" || !/^127\.0\.0\.1:[0-9]{2,5}$/.test(host ?? "")) {
    return { ok:false, code:"NON_LOOPBACK_REVIEW_FORBIDDEN", status:403 };
  }
  if (origin !== "http://" + host || fetchSite !== "same-origin" || localHeader !== "1") {
    return { ok:false, code:"CROSS_ORIGIN_REVIEW_FORBIDDEN", status:403 };
  }
  if (!/^application\/json(?:\s*;\s*charset=utf-8)?$/i.test(contentType || "")) {
    return { ok:false, code:"JSON_REVIEW_REQUIRED", status:415 };
  }
  return {ok:true};
}
