/** Browser-only Contact candidate selection from an authorized private JSON export.
 * No fetch, no storage, no Salesforce writes; local evidence is NOT live verification.
 */
const contactId = /^003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;
const accountId = /^001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;
const opportunityId = /^006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;
const excluded = new Set(["kaist", "한국과학기술원", "한남대", "한남대학교", "hannam university"]);
export const normalizeContactLabel = value =>
  String(value ?? "").normalize("NFKC").toLocaleLowerCase().trim().replace(/\s+/g, " ");

export function parseLocalContacts(text) {
  if (typeof text !== "string" || text.length > 2_000_000) throw Error("로컬 JSON은 2MB 이하여야 합니다.");
  const rows = JSON.parse(text);
  if (!Array.isArray(rows) || rows.length > 5000) throw Error("Contact 배열은 최대 5000건까지 지원합니다.");
  return rows.filter(row => row && typeof row === "object" && !Array.isArray(row) &&
    typeof row.name === "string" && typeof row.institution === "string" &&
    contactId.test(row.contact_id) && accountId.test(row.account_id) &&
    typeof row.contact_email === "string" &&
    /^[^\s@]{1,64}@[^\s@]{1,190}$/.test(row.contact_email) &&
    Array.isArray(row.opportunity_ids) && row.opportunity_ids.length > 0 &&
    row.opportunity_ids.every(id => typeof id === "string" && opportunityId.test(id)) &&
    !excluded.has(normalizeContactLabel(row.institution))
  ).map(row => ({
    name: row.name, institution: row.institution,
    contact_id: row.contact_id, account_id: row.account_id,
    contact_email: row.contact_email, opportunity_ids: [...row.opportunity_ids],
  }));
}
export function lookupLocalContacts(name, rows) {
  const needle = normalizeContactLabel(name);
  if (!needle || !Array.isArray(rows)) return [];
  const unique = new Map();
  for (const row of rows) {
    if (normalizeContactLabel(row.name) === needle) {
      unique.set(row.contact_id + "|" + row.account_id, row);
    }
  }
  return [...unique.values()].sort((a,b) =>
    normalizeContactLabel(a.institution).localeCompare(normalizeContactLabel(b.institution), "ko") ||
    a.contact_id.localeCompare(b.contact_id)
  );
}
