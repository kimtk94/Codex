/** Allow read-only private Contact lookup ONLY from explicitly enabled loopback.
 * Reject cross-origin browsers, DNS rebinding hosts, and other HTTP methods.
 * No Contact data, token, or URL is included in diagnostics.
 */
export function authorizePcLocalLookup({
  enabled, method, host, origin, fetchSite, localHeader, name,
}) {
  if (enabled !== true) return {ok:false, code:"LOCAL_LOOKUP_DISABLED", status:404};
  if (method !== "GET" || !/^127\.0\.0\.1:[0-9]{2,5}$/.test(host ?? "")) {
    return {ok:false, code:"NOT_LOCAL_LOOPBACK", status:403};
  }
  if (origin && origin !== "http://" + host) {
    return {ok:false, code:"ORIGIN_MISMATCH", status:403};
  }
  if (fetchSite && !["same-origin", "none"].includes(fetchSite)) {
    return {ok:false, code:"CROSS_SITE_FORBIDDEN", status:403};
  }
  if (localHeader !== "1") {
    return {ok:false, code:"USER_INITIATED_HEADER_REQUIRED", status:403};
  }
  if (typeof name !== "string" || !/^[\uac00-\ud7a3]{2,6}$/.test(name.normalize("NFKC").trim())) {
    return {ok:false, code:"EXACT_KOREAN_NAME_REQUIRED", status:400};
  }
  return {ok:true, name:name.normalize("NFKC").trim()};
}
