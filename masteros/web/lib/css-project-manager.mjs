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
    if (row.quote_candidate_name &&
        (row.quote_name || row.quote_candidate_state !== "UNVERIFIED_APPROVAL_DEDUP" ||
         row.quote_candidate_count !== 1))
      throw new Error("UNVERIFIED_CANDIDATE_PROMOTED");
    if (row.legacy_completion_conflict === true && row.bucket === "PAYMENT")
      throw new Error("STALE_CSS_FINANCE_TRANSITION");
    if (row.progress_conflict === true &&
        (row.progress_percent !== 100 || row.progress_display_percent != null ||
         row.bucket === "PAYMENT"))
      throw new Error("FALSE_CURRENT_COMPLETION_PROGRESS");
    if (row.invoice_evidence_state && ![
      "EXACT_X_INVOICE_MIRROR", "X_SUBJECT_INVOICE_NOTICE",
      "AMEA_OWNER_INVOICE_REVIEW", "NO_EXTRA_INVOICE_EVIDENCE"
    ].includes(row.invoice_evidence_state))
      throw new Error("UNKNOWN_INVOICE_EVIDENCE_STATE");
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
