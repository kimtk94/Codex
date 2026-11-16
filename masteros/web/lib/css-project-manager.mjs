/** Project-management snapshot validation. Read-only; original source never certified here. */
export function validateProjectManager(payload) {
  const states = new Set(["PASS_MIRROR_ONLY","PARTIAL_MIRROR","STALE"]);
  if (!payload || !states.has(payload.status) || !Array.isArray(payload.project_rows) ||
      payload.project_rows.length < 1 || payload.project_rows.length > 1500)
    throw new Error("INVALID_PROJECT_MANAGER_SNAPSHOT");
  const ids = new Set();
  for (const row of payload.project_rows) {
    if (!row || !row.project_id || typeof row.project_id !== "string" ||
        ids.has(row.project_id) || !["ACTIVE","PAYMENT"].includes(row.bucket) ||
        !["APPROVED_AMEA_MIRROR","MULTIPLE_QUOTE_REVIEW","QUOTE_UNLINKED"].includes(row.quote_match_state))
      throw new Error("INVALID_PROJECT_MANAGER_ROW");
    if (row.quote_match_state !== "APPROVED_AMEA_MIRROR" && row.quote_name)
      throw new Error("UNVERIFIED_QUOTE_NAME");
    if (row.receipt_state !== "결제 증빙 미확인")
      throw new Error("FALSE_PAYMENT_CERTIFICATION");
    ids.add(row.project_id);
  }
  if (payload.original_feishu_verified !== false ||
      payload.payment_receipt_verified !== false ||
      payload.counts?.total !== ids.size ||
      payload.counts?.active + payload.counts?.payment !== ids.size ||
      payload.counts?.archive !== 0)
    throw new Error("MISLEADING_SOURCE_OR_LIFECYCLE_COUNTS");
  return payload;
}
