/** A browser-local, identity-bound handoff for desktop read-only preflight.
 * This never proves fresh Salesforce authorization and never permits Save.
 * No API, network, storage, or secret usage.
 */
import { validateDraft } from "./sfdc-oppo-quote.mjs";
import { parseLocalContacts } from "./sfdc-contact-local.mjs";

export const CONTACT_REVIEW_VERSION = "oppo-quote-contact-review-v1";

export function buildContactReviewPacket(request, selected) {
  const result = validateDraft(request);
  if (!result.ok) throw new Error(result.errors[0]);
  if (!selected || typeof selected !== "object") {
    throw new Error("고객을 비공개 목록에서 먼저 선택하세요.");
  }
  const matching = parseLocalContacts(JSON.stringify([selected]));
  if (matching.length !== 1) throw new Error("고객의 Salesforce ID와 Opportunity 관계를 확인하세요.");
  const contact = matching[0];
  if (!/^[\uac00-\ud7a3]{2,6}$/.test(contact.name)) {
    throw new Error("검증된 한글 고객 이름만 허용됩니다.");
  }
  if (request.contact_email !== contact.contact_email) {
    throw new Error("선택한 Contact 이메일과 요청 이메일이 다릅니다.");
  }
  return {
    version: CONTACT_REVIEW_VERSION,
    source: "authorized_private_browser_json",
    status: "HOLD_FRESH_SALESFORCE_IDENTITY_AND_PRICING",
    selected_contact: {
      name: contact.name,
      institution: contact.institution,
      contact_id: contact.contact_id,
      account_id: contact.account_id,
      contact_email: contact.contact_email,
      opportunity_ids: [...contact.opportunity_ids],
    },
    draft: result.draft,
    gate: {
      contact_identity_live_verified: false,
      account_identity_live_verified: false,
      opportunity_duplicate_check_complete: false,
      quote_price_and_product_verified: false,
      salesforce_save_allowed: false,
    },
  };
}
