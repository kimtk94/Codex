/**
 * No-Save Salesforce Opportunity + Research-AMEA Quotation command preview.
 * This library does not contact Salesforce, issue an API request, or persist PII.
 * The operations team must independently verify Contact, Account, duplicates,
 * pricing and the current Quotation dropdown options before any CRM write.
 */
export const MODES = Object.freeze(["PE250", "PE150", "PE100", "SE100", "SE50"]);
export const DEFAULT_REQUEST = Object.freeze({
  contact_email: "",
  service: "PMP",
  sequencing_mode: "PE250",
  sample_count: 5,
  depth_per_sample: 1,
  depth_unit: "M reads",
});
export function unitForMode(mode) {
  if (!MODES.includes(mode)) throw new Error("Unsupported sequencing mode");
  return mode === "PE250" ? "M reads" : "Gb";
}
export function validateDraft(input) {
  const errors = [];
  if (typeof input !== "object" || !input || Array.isArray(input)) {
    return { ok: false, errors: ["요청서 형식이 올바르지 않습니다."] };
  }
  const keys = [
    "contact_email", "service", "sequencing_mode",
    "sample_count", "depth_per_sample", "depth_unit"
  ];
  if (Object.keys(input).sort().join("|") !== [...keys].sort().join("|")) {
    errors.push("허용되지 않은 필드가 포함되었거나 필수 필드가 누락되었습니다.");
  }
  if (input.service !== "PMP") errors.push("현재 PMP 단일 서비스만 지원합니다.");
  if (!MODES.includes(input.sequencing_mode)) errors.push("지원되지 않는 시퀀싱 모드입니다.");
  const email = input.contact_email;
  if (typeof email !== "string" || email.trim() !== email ||
      !/^[^\s@]{1,64}@[^\s@]{1,190}$/.test(email)) {
    errors.push("유효한 고객 이메일을 입력하세요.");
  }
  if (!Number.isInteger(input.sample_count) || input.sample_count < 1 || input.sample_count > 500) {
    errors.push("샘플 수는 1~500 사이의 정수여야 합니다.");
  }
  if (typeof input.depth_per_sample !== "number" || !Number.isFinite(input.depth_per_sample)
      || input.depth_per_sample <= 0 || input.depth_per_sample > 100000) {
    errors.push("샘플당 목표 데이터량은 0보다 큰 숫자여야 합니다.");
  }
  if (MODES.includes(input.sequencing_mode) &&
      input.depth_unit !== unitForMode(input.sequencing_mode)) {
    errors.push("시퀀싱 모드와 데이터 단위가 일치하지 않습니다.");
  }
  if (errors.length) return { ok: false, errors };
  return {
    ok: true,
    errors: [],
    draft: {
      version: "oppo-quote-pmp-web-draft-v1",
      status: "HOLD_CONTACT_ACCOUNT_QUOTE_REVIEW",
      request: Object.fromEntries(keys.map(key => [key, input[key]])),
      summary: {
        nominal_total_depth: input.sample_count * input.depth_per_sample,
        depth_unit: input.depth_unit,
        reads_basis: "UNSPECIFIED_WHETHER_READS_OR_READ_PAIRS",
      },
      required_checks: [
        "exact_contact_email_identity",
        "account_record_id_and_contact_lookup",
        "existing_opportunity_and_quotation_duplicates",
        "approved_opportunity_name_amount_stage_close_date",
        "current_business_entity_promotion_type_valid_thru",
        "verified_price_and_quote_lines",
        "post_creation_native_006_parent_and_a0P_quote_links",
      ],
      salesforce_save_allowed: false,
      opportunity_created: false,
      quotation_created: false,
    },
  };
}
export function formatDraft(input) {
  const res = validateDraft(input);
  if (!res.ok) throw new Error(res.errors.join(" / "));
  return JSON.stringify(res.draft, null, 2);
}
