/**
 * Contact search and identity-selection contract for a future authenticated
 * Salesforce-backed web command page. No network, browser storage or CRM writes.
 *
 * Search by Korean name, then REQUIRE institution selection for homonyms.
 * A repeated name inside the same Account is HOLD (name + institution is still
 * not enough). Every selected record requires server-side identity re-check.
 */
import { validateDraft } from "./sfdc-oppo-quote.mjs";

const CONTACT_ID = /^003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;
const ACCOUNT_ID = /^001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;
const EMAIL = /^[^\s@]{1,64}@[^\s@]{1,190}$/;

export function normalizeKoreanName(value) {
  if (typeof value !== "string") return "";
  return value.normalize("NFKC").trim().replace(/\s+/g, " ");
}
export function validateKoreanNameQuery(value) {
  const query = normalizeKoreanName(value);
  const letters = query.replaceAll(" ", "");
  if (!query || letters.length < 2 || letters.length > 20 ||
      !/^[가-힣]+(?: [가-힣]+)*$/.test(query)) {
    return { ok: false, error: "한글 이름 2~20자를 입력하세요. 이메일 검색은 사용하지 않습니다." };
  }
  return { ok: true, query, lookup_field: "Contact Korean Name" };
}

export function auditContactCandidates(searchName, candidates) {
  const q = validateKoreanNameQuery(searchName);
  if (!q.ok) return { ok: false, status: "INVALID_KOREAN_NAME", error: q.error };
  if (!Array.isArray(candidates)) {
    return { ok: false, status: "LOOKUP_NOT_CONNECTED", error: "인증된 Salesforce Contact 검색이 연결되지 않았습니다." };
  }
  const exactMatches = candidates.filter(x =>
    x && typeof x === "object" && !Array.isArray(x) &&
    normalizeKoreanName(x.korean_name) === q.query
  );
  const items = exactMatches.filter(x =>
    CONTACT_ID.test(x.contact_id || "") && ACCOUNT_ID.test(x.account_id || "") &&
    typeof x.institution_name === "string" && x.institution_name.trim().length >= 2 &&
    typeof x.email === "string" && EMAIL.test(x.email)
  );
  if (items.length !== exactMatches.length) {
    return { ok:false, status:"INCOMPLETE_CONTACT_DATA" };
  }
  const ids = items.map(x => x.contact_id);
  if (new Set(ids).size !== ids.length) {
    return { ok: false, status: "DUPLICATE_CONTACT_ID", error: "중복 Contact ID가 검색 결과에 존재합니다." };
  }
  const accountCounts = new Map();
  for (const x of items) accountCounts.set(x.account_id, (accountCounts.get(x.account_id) || 0) + 1);
  return {
    ok: true,
    status: items.length ? "REVIEW_REQUIRED" : "NO_EXACT_MATCH",
    exact_match_count: items.length,
    requires_institution_choice: items.length > 1,
    has_duplicates_within_institution: [...accountCounts.values()].some(n => n > 1),
    candidates: items,
  };
}

export function selectExistingContact(searchName, candidates, chosenContactId, chosenAccountId) {
  const result = auditContactCandidates(searchName, candidates);
  if (!result.ok) return { ok: false, status: result.status };
  if (!result.exact_match_count) return { ok: false, status: "NO_EXACT_MATCH" };
  if (!CONTACT_ID.test(chosenContactId || "") || !ACCOUNT_ID.test(chosenAccountId || "")) {
    return { ok: false, status: "CONTACT_AND_INSTITUTION_NOT_SELECTED" };
  }
  const matches = result.candidates.filter(x =>
    x.contact_id === chosenContactId && x.account_id === chosenAccountId
  );
  if (matches.length !== 1) return { ok: false, status: "CONTACT_ACCOUNT_PAIR_MISMATCH" };
  const chosen = matches[0];
  if (result.candidates.filter(x => x.account_id === chosenAccountId).length !== 1) {
    return { ok: false, status: "SAME_NAME_SAME_INSTITUTION_AMBIGUOUS" };
  }
  return {
    ok: true,
    status: "CONTACT_SELECTION_PENDING_SERVER_RECHECK",
    contact_id: chosen.contact_id,
    account_id: chosen.account_id,
    korean_name: normalizeKoreanName(chosen.korean_name),
    institution_name: chosen.institution_name.trim(),
    email: chosen.email,
    requires_server_identity_recheck: true,
  };
}

export function createContactLinkedNoSaveCommand(baseRequest, contactSelection) {
  if (!contactSelection?.ok || !contactSelection.requires_server_identity_recheck) {
    return { ok: false, error: "실제 기존 Contact와 소속 기관을 선택해야 합니다." };
  }
  const request = { ...baseRequest, contact_email: contactSelection.email };
  const checked = validateDraft(request);
  if (!checked.ok) return { ok: false, error: checked.errors.join(" / ") };
  return {
    ok: true,
    command: {
      version: "sfdc-contact-first-oppo-quote-dryrun-v1",
      state: "PENDING_AUTHENTICATED_CONTACT_RECHECK",
      contact: {
        contact_id: contactSelection.contact_id,
        account_id: contactSelection.account_id,
        korean_name: contactSelection.korean_name,
        institution_name: contactSelection.institution_name,
      },
      request: checked.draft.request,
      summary: checked.draft.summary,
      next_actions: [
        "independently_verify_contact_and_account_id",
        "check_existing_opportunity_and_quote_duplicate",
        "review_single_product_price_and_process",
        "prepare_opportunity_and_quote_forms_without_save",
      ],
      save_clicked: false,
      salesforce_save_allowed: false,
      opportunity_created: false,
      quotation_created: false,
      // Copy in a trusted private environment only, not a GitHub workflow input.
      send_customer_email: false,
    },
  };
}
