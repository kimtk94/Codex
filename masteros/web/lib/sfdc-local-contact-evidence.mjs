/**
 * Privacy-preserving, local-only Salesforce Contact readback preview.
 *
 * The file is supplied explicitly by the operator from an authorized desktop.
 * Never upload the contents to a backend or GitHub, persist to browser storage,
 * or treat file metadata as server-verifiable Salesforce authorization.
 * Every create/save remains blocked pending a fresh authenticated SFDC recheck.
 */
import { auditContactCandidates, validateKoreanNameQuery } from "./sfdc-contact-first-command.mjs";

const MAX_CHARS = 256 * 1024;
const MAX_AGE_MS = 2 * 60 * 60 * 1000;
const FUTURE_TOLERANCE_MS = 2 * 60 * 1000;

export function inspectLocalContactEvidence(rawText, koreanName, now = Date.now()) {
  const checked = validateKoreanNameQuery(koreanName);
  if (!checked.ok) return { ok: false, status: "INVALID_KOREAN_NAME" };
  if (typeof rawText !== "string" || !rawText || rawText.length > MAX_CHARS) {
    return { ok: false, status: "LOCAL_FILE_EMPTY_OR_TOO_LARGE" };
  }
  let doc;
  try { doc = JSON.parse(rawText); }
  catch { return { ok: false, status: "INVALID_LOCAL_JSON" }; }
  if (!doc || Array.isArray(doc) || typeof doc !== "object" ||
      doc.version !== "sfdc-oppo-contact-readback-v1" ||
      doc.source !== "SFDC_LIGHTNING_READ_ONLY" ||
      doc.scope !== "OPPORTUNITY_LINKED_CONTACTS" ||
      doc.salesforce_write_performed !== false) {
    return { ok: false, status: "UNTRUSTED_LOCAL_EXPORT_SCHEMA" };
  }
  if (doc.query !== checked.query) {
    return { ok: false, status: "SEARCH_NAME_MISMATCH" };
  }
  if (!Number.isFinite(now) || typeof doc.generated_at !== "string" ||
      !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?(?:Z|[+-]\d\d:\d\d)$/.test(doc.generated_at)) {
    return { ok: false, status: "MISSING_SOURCE_TIMESTAMP" };
  }
  const ms = Date.parse(doc.generated_at);
  if (!Number.isFinite(ms) || ms > now + FUTURE_TOLERANCE_MS ||
      now - ms > MAX_AGE_MS) {
    return { ok: false, status: "STALE_OR_FUTURE_LOCAL_EVIDENCE" };
  }
  if (!Number.isInteger(doc.unresolved_matches) || doc.unresolved_matches !== 0 ||
      !Array.isArray(doc.candidates) || doc.candidates.length > 30) {
    return { ok: false, status: "INCOMPLETE_LOCAL_SEARCH_SCOPE" };
  }
  const review = auditContactCandidates(koreanName, doc.candidates);
  if (!review.ok) return { ok: false, status: review.status };
  // Even a valid local file is NOT a server-side account/contact proof.
  return {
    ok: true,
    status: "LOCAL_PREVIEW_ONLY_SERVER_RECHECK_REQUIRED",
    candidates: review.candidates,
    exact_match_count: review.exact_match_count,
    requires_institution_choice: review.requires_institution_choice,
    exported_at: doc.generated_at,
    salesforce_save_allowed: false,
  };
}
